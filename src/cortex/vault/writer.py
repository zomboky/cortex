from __future__ import annotations

import re
from pathlib import Path

import yaml

from .notes import Note

_ILLEGAL_CHARS = re.compile(r'[\\/:*?"<>|]')
_WHITESPACE = re.compile(r"\s+")


def sanitize_filename(title: str) -> str:
    cleaned = _ILLEGAL_CHARS.sub("", title).strip()
    cleaned = _WHITESPACE.sub(" ", cleaned)
    return cleaned or "Note sans titre"


def render_note(note: Note) -> str:
    frontmatter = {
        "title": note.title,
        "tags": note.tags,
        "source_path": note.source_path,
        "created": note.created,
    }
    fm_yaml = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).strip()
    parts = [f"---\n{fm_yaml}\n---\n", f"# {note.title}\n"]
    if note.summary:
        parts.append(f"## Resume\n{note.summary}\n")
    parts.append(note.body.strip() + "\n")
    return "\n".join(parts)


class VaultWriter:
    """Ecrit les notes sur disque au fil de l'eau (une note peut etre reecrite plusieurs
    fois -- p.ex. brouillon puis version finale avec liens -- sans changer de nom de
    fichier ni recompter les doublons de titre)."""

    def __init__(self, vault_dir: Path) -> None:
        self.vault_dir = vault_dir
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self._counts: dict[str, int] = {}
        self._paths: dict[int, Path] = {}

    def write(self, note: Note) -> Path:
        path = self._paths.get(id(note))
        if path is None:
            base = sanitize_filename(note.title)
            self._counts[base] = self._counts.get(base, 0) + 1
            n = self._counts[base]
            name = base if n == 1 else f"{base} ({n})"
            path = self.vault_dir / f"{name}.md"
            self._paths[id(note)] = path
        path.write_text(render_note(note), encoding="utf-8")
        return path


def write_vault(notes: list[Note], vault_dir: Path) -> list[Path]:
    """Ecrit chaque note sur disque avec des noms de fichiers uniques et lisibles.
    Retourne les chemins ecrits, dans le meme ordre que `notes` (des titres
    dupliques sont possibles, donc pas de cle dict sur le titre)."""
    writer = VaultWriter(vault_dir)
    return [writer.write(note) for note in notes]
