"""Auto-detection et application des mises a jour de cortex depuis GitHub.

Cortex n'est pas publie sur PyPI : toute installation (uv tool / pipx / pip --user /
`pip install -e` en dev) pointe directement vers `git+https://github.com/zomboky/cortex.git`
(branche main, voir install.sh/install.ps1). Il n'y a donc pas de notion de "release"
au sens PyPI/semver : chaque nouveau commit pousse sur main EST la nouvelle version.
La detection compare donc le commit installe localement au HEAD distant de main.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

REPO_SLUG = "zomboky/cortex"
REPO_GIT_URL = f"https://github.com/{REPO_SLUG}.git"
COMMITS_API_URL = f"https://api.github.com/repos/{REPO_SLUG}/commits/main"
CHECK_INTERVAL_SECONDS = 24 * 3600
REQUEST_TIMEOUT_SECONDS = 3


def _cache_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / "cortex" / "update_check.json"
    return Path.home() / ".cache" / "cortex" / "update_check.json"


@dataclass
class InstalledInfo:
    commit: str | None
    editable_repo: Path | None  # non-None seulement pour une install `pip install -e`


def get_installed_info() -> InstalledInfo:
    """Determine le commit git dont provient l'installation courante, via les
    metadonnees PEP 610 (`direct_url.json`) que pip ecrit pour toute install depuis
    une URL git. Pour une install editable, ces metadonnees n'ont pas de commit (juste
    un chemin local) : on lit alors le HEAD du depot local directement."""
    try:
        import importlib.metadata as metadata

        dist = metadata.distribution("cortex")
        raw = dist.read_text("direct_url.json")
    except Exception:
        return InstalledInfo(None, None)
    if not raw:
        return InstalledInfo(None, None)
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return InstalledInfo(None, None)

    if info.get("dir_info", {}).get("editable"):
        parsed = urlparse(info.get("url", ""))
        if parsed.scheme != "file":
            return InstalledInfo(None, None)
        raw_path = unquote(parsed.path)
        if os.name == "nt" and raw_path.startswith("/"):
            raw_path = raw_path[1:]
        repo_path = Path(raw_path)
        commit = None
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                commit = result.stdout.strip()
        except OSError:
            pass
        return InstalledInfo(commit, repo_path)

    vcs_info = info.get("vcs_info", {})
    return InstalledInfo(vcs_info.get("commit_id"), None)


def fetch_latest_commit() -> str | None:
    """SHA du dernier commit sur main, ou None si indisponible (hors ligne, API down,
    etc.). Ne leve jamais : une verification de mise a jour ne doit jamais faire
    planter une commande cortex normale."""
    try:
        req = Request(COMMITS_API_URL, headers={"Accept": "application/vnd.github+json"})
        with urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        sha = data.get("sha")
        return sha if isinstance(sha, str) else None
    except Exception:
        return None


def _load_cache() -> dict:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_cache(data: dict) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    except OSError:
        pass


def check_for_update(*, force: bool = False) -> str | None:
    """Retourne le SHA distant si une mise a jour est disponible, sinon None.

    Utilise un cache sur disque (24h) pour eviter un appel reseau a chaque invocation
    de `cortex`, sauf si force=True. Desactivable via CORTEX_SKIP_UPDATE_CHECK=1."""
    if os.environ.get("CORTEX_SKIP_UPDATE_CHECK"):
        return None

    installed = get_installed_info()
    if installed.commit is None:
        return None  # impossible de determiner la version installee -- pas de comparaison possible

    cache = _load_cache()
    now = time.time()
    if not force and cache.get("checked_at", 0) + CHECK_INTERVAL_SECONDS > now and cache.get("latest_sha"):
        latest = cache["latest_sha"]
    else:
        latest = fetch_latest_commit()
        if latest is not None:
            _save_cache({"checked_at": now, "latest_sha": latest})

    if latest and latest != installed.commit:
        return latest
    return None


def _detect_installer() -> str:
    if shutil.which("uv"):
        return "uv"
    if shutil.which("pipx"):
        return "pipx"
    return "pip"


def apply_update(installed: InstalledInfo) -> tuple[bool, str]:
    """Applique la mise a jour. Retourne (succes, message)."""
    if installed.editable_repo is not None:
        repo = installed.editable_repo
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, timeout=15,
        )
        if status.returncode != 0:
            return False, f"impossible de verifier l'etat git de {repo}"
        if status.stdout.strip():
            return False, (
                f"{repo} a des modifications locales non commitees -- mise a jour "
                "automatique ignoree (commit/stash puis `git pull` toi-meme)."
            )
        result = subprocess.run(
            ["git", "-C", str(repo), "pull", "--ff-only"],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return False, f"`git pull --ff-only` a echoue : {result.stderr.strip()}"
        return True, (result.stdout.strip() or "depot local mis a jour")

    installer = _detect_installer()
    git_url = f"git+{REPO_GIT_URL}"
    if installer == "uv":
        cmd = ["uv", "tool", "install", "--force", git_url]
    elif installer == "pipx":
        cmd = ["pipx", "install", "--force", git_url]
    else:
        cmd = ["pip", "install", "--user", "--upgrade", "--force-reinstall", git_url]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except OSError as exc:
        return False, f"impossible de lancer {installer} : {exc}"
    if result.returncode != 0:
        return False, f"`{' '.join(cmd)}` a echoue : {result.stderr.strip()[-500:]}"
    return True, f"mis a jour via {installer}"
