from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cortex import update as update_module
from cortex.update import InstalledInfo, apply_update, check_for_update


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "a.txt").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def test_check_for_update_returns_none_when_installed_commit_unknown(monkeypatch) -> None:
    monkeypatch.delenv("CORTEX_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(update_module, "get_installed_info", lambda: InstalledInfo(None, None))
    assert check_for_update() is None


def test_check_for_update_returns_sha_when_remote_ahead(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CORTEX_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(update_module, "_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(update_module, "get_installed_info", lambda: InstalledInfo("old-sha", None))
    monkeypatch.setattr(update_module, "fetch_latest_commit", lambda: "new-sha")

    assert check_for_update() == "new-sha"


def test_check_for_update_returns_none_when_up_to_date(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("CORTEX_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(update_module, "_cache_path", lambda: tmp_path / "cache.json")
    monkeypatch.setattr(update_module, "get_installed_info", lambda: InstalledInfo("same-sha", None))
    monkeypatch.setattr(update_module, "fetch_latest_commit", lambda: "same-sha")

    assert check_for_update() is None


def test_check_for_update_uses_cache_within_ttl(monkeypatch, tmp_path) -> None:
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps({"checked_at": update_module.time.time(), "latest_sha": "cached-sha"}), encoding="utf-8"
    )
    monkeypatch.delenv("CORTEX_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(update_module, "_cache_path", lambda: cache_path)
    monkeypatch.setattr(update_module, "get_installed_info", lambda: InstalledInfo("old-sha", None))

    def _boom() -> str:
        raise AssertionError("ne doit pas appeler le reseau si le cache est encore valide")

    monkeypatch.setattr(update_module, "fetch_latest_commit", _boom)

    assert check_for_update() == "cached-sha"


def test_check_for_update_respects_skip_env_var(monkeypatch) -> None:
    monkeypatch.setenv("CORTEX_SKIP_UPDATE_CHECK", "1")
    assert check_for_update() is None


def test_apply_update_skips_editable_repo_with_local_changes(tmp_path) -> None:
    _init_git_repo(tmp_path)
    (tmp_path / "a.txt").write_text("modifie", encoding="utf-8")

    ok, message = apply_update(InstalledInfo("whatever", tmp_path))

    assert ok is False
    assert "modifications locales" in message


def test_apply_update_pull_failure_is_reported_not_raised(tmp_path) -> None:
    _init_git_repo(tmp_path)  # pas de remote configure -> le pull doit echouer proprement

    ok, message = apply_update(InstalledInfo("whatever", tmp_path))

    assert ok is False
    assert message


def test_apply_update_uses_uv_when_available(monkeypatch) -> None:
    monkeypatch.setattr(update_module.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(update_module.subprocess, "run", _fake_run)

    ok, message = apply_update(InstalledInfo("whatever", None))

    assert ok is True
    assert captured["cmd"][:3] == ["uv", "tool", "install"]


def test_apply_update_falls_back_to_pip_when_no_uv_or_pipx(monkeypatch) -> None:
    monkeypatch.setattr(update_module.shutil, "which", lambda name: None)

    captured: dict = {}

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(update_module.subprocess, "run", _fake_run)

    ok, message = apply_update(InstalledInfo("whatever", None))

    assert ok is True
    assert captured["cmd"][0] == "pip"
