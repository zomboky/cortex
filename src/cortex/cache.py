"""Cache disque des etapes couteuses en LLM (triage des fichiers ambigus, generation
des notes du vault), stocke dans `<output_dir>/.cortex/`.

Cle de cache = chemin du fichier source + hash sha256 de son contenu : un fichier
modifie depuis le dernier `cortex build`/`vault` a un hash different, donc traite
comme nouveau (retriage + regeneration). Un fichier inchange reutilise sa decision
de triage et sa note deja generee, sans rappeler le LLM.

Trois fichiers dans `.cortex/` :
- `triage-cache.json` : decisions de triage LLM (fichiers ambigus) par fichier source.
- `vault-cache.json`  : notes generees (titre/tags/resume/corps/topics) par fichier
  source -- c'est le cache "vault Obsidian".
- `graphify-cache.json` : hash de la composition du vault au dernier build reussi,
  pour savoir si graphify doit retourner dessus (evite de relancer son extraction
  semantique, elle aussi facturee en tokens LLM, quand rien n'a change).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

CACHE_DIRNAME = ".cortex"
TRIAGE_CACHE_FILENAME = "triage-cache.json"
VAULT_CACHE_FILENAME = "vault-cache.json"
GRAPHIFY_CACHE_FILENAME = "graphify-cache.json"


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def composition_hash(entries: list[tuple[str, str]]) -> str:
    """Hash stable d'un ensemble (chemin source, hash de contenu). Sert a detecter si
    la composition du vault (quels fichiers, avec quel contenu) a change depuis le
    dernier build -- peu importe l'ordre de parcours."""
    canonical = json.dumps(sorted(entries), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class ProjectCache:
    """Cache d'un projet cortex, un par dossier `--output`. Deux builds vers des
    `--output` differents ont chacun leur `.cortex/`, jamais partage entre eux."""

    cache_dir: Path
    triage: dict[str, dict] = field(default_factory=dict)
    vault: dict[str, dict] = field(default_factory=dict)
    graphify: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, output_dir: Path) -> "ProjectCache":
        cache_dir = output_dir / CACHE_DIRNAME
        return cls(
            cache_dir=cache_dir,
            triage=_load_json(cache_dir / TRIAGE_CACHE_FILENAME),
            vault=_load_json(cache_dir / VAULT_CACHE_FILENAME),
            graphify=_load_json(cache_dir / GRAPHIFY_CACHE_FILENAME),
        )

    def save(self) -> None:
        _save_json(self.cache_dir / TRIAGE_CACHE_FILENAME, self.triage)
        _save_json(self.cache_dir / VAULT_CACHE_FILENAME, self.vault)
        _save_json(self.cache_dir / GRAPHIFY_CACHE_FILENAME, self.graphify)

    # -- triage (fichiers ambigus juges par le LLM) --

    def cached_triage_decision(self, path: Path) -> dict | None:
        entry = self.triage.get(str(path))
        if entry is None:
            return None
        try:
            if entry.get("hash") != hash_file(path):
                return None
        except OSError:
            return None
        return entry

    def record_triage_decision(self, path: Path, file_hash: str, *, decision: str, reason: str, source: str) -> None:
        self.triage[str(path)] = {"hash": file_hash, "decision": decision, "reason": reason, "source": source}

    # -- vault (notes generees) --

    def cached_note(self, path: Path, file_hash: str) -> dict | None:
        entry = self.vault.get(str(path))
        if entry is None or entry.get("hash") != file_hash:
            return None
        note_path = entry.get("note_path")
        if not note_path or not Path(note_path).is_file():
            return None
        return entry

    def record_note(self, path: Path, file_hash: str, note_path: Path, note) -> None:
        self.vault[str(path)] = {
            "hash": file_hash,
            "note_path": str(note_path),
            "title": note.title,
            "tags": list(note.tags),
            "summary": note.summary,
            "body": note.body,
            "candidate_topics": list(note.candidate_topics),
            "created": note.created,
        }
