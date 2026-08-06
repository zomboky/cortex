"""Resolution deterministe (sans LLM) des [[wikilinks]] : garantit zero lien mort
dans le vault livre. Correspondance exacte -> inchange. Quasi-correspondance
(casse/ponctuation) -> reecrite vers le titre canonique. Aucune correspondance ->
lien mort, converti en texte simple (la phrase est conservee, les crochets retires)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .notes import Note

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


@dataclass(frozen=True)
class LinkFix:
    note_title: str
    original_target: str
    resolution: str  # "exact" | "rewritten" | "stripped"
    resolved_target: str | None


def _normalize(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


def _resolve_one(match: re.Match, note_title: str, valid_titles: set[str], normalized: dict[str, str], fixes: list[LinkFix]) -> str:
    target = match.group(1).strip()
    alias = match.group(2)
    display = alias.strip() if alias else target

    if target in valid_titles:
        fixes.append(LinkFix(note_title, target, "exact", target))
        return match.group(0)

    canonical = normalized.get(_normalize(target))
    if canonical:
        fixes.append(LinkFix(note_title, target, "rewritten", canonical))
        return f"[[{canonical}|{display}]]" if alias else f"[[{canonical}]]"

    fixes.append(LinkFix(note_title, target, "stripped", None))
    return display


def resolve_links(notes: list[Note]) -> list[LinkFix]:
    """Repare les [[wikilinks]] de chaque note, en place. Retourne le journal des corrections."""
    valid_titles = {n.title for n in notes}
    normalized_to_canonical = {_normalize(t): t for t in valid_titles}
    fixes: list[LinkFix] = []

    for note in notes:
        def _replace(match: re.Match, _note: Note = note) -> str:
            return _resolve_one(match, _note.title, valid_titles, normalized_to_canonical, fixes)

        note.body = WIKILINK_PATTERN.sub(_replace, note.body)

    return fixes
