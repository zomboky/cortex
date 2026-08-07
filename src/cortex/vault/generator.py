"""Generation des notes via LLM en deux passes :
Passe A (par fichier) : brouillon avec resume + sujets candidats, pas encore de liens.
Passe B (par lot, sur titres+resumes seulement) : propose des phrases de liaison en
prose citant explicitement d'autres notes via [[Titre]] -- ecrites comme une reference
explicite plutot qu'une liste de crochets, pour maximiser les chances que l'extracteur
semantique de Graphify les classe EXTRACTED plutot que INFERRED."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..providers.base import LLMProvider
from .notes import Note

_LIENS_SECTION = re.compile(r"\n\n## Liens\n.*\Z", re.DOTALL)

NOTE_SYSTEM_PROMPT = (
    "Tu es un assistant qui transforme un fichier source en une note de style "
    "'deuxieme cerveau' (methode Zettelkasten/PARA) destinee a un vault Obsidian. "
    "Reponds UNIQUEMENT avec un objet JSON de la forme "
    '{"title": "...", "tags": ["...", "..."], "summary": "...", "body": "...", '
    '"candidate_topics": ["...", "..."]}. '
    "title: titre court et parlant, sans extension de fichier. "
    "tags: 2 a 5 mots-cles en minuscule. "
    "summary: un paragraphe de resume. "
    "body: le contenu curé et nettoye en markdown, structure avec des sous-titres ##, "
    "sans repeter le resume. "
    "candidate_topics: 3 a 8 entites/concepts cles abordes, pour relier cette note a "
    "d'autres notes plus tard."
)

LINKING_SYSTEM_PROMPT = (
    "Tu relies entre elles des notes d'un vault Obsidian. On te donne une liste de notes "
    "(titre, resume, sujets candidats). Pour chaque relation semantique reelle entre deux "
    "notes (pas une vague similarite thematique), propose UNE phrase en francais qui "
    "mentionne l'autre note comme une reference explicite via [[Titre exact de l'autre "
    "note]], par exemple : \"Cette approche prolonge le constat pose dans [[Budget Infra "
    "2024]].\" "
    'Reponds UNIQUEMENT avec un objet JSON : {"links": [{"note": "<titre note source>", '
    '"sentence": "<phrase avec [[Titre cible exact]] dedans>"}]}. '
    "N'invente jamais un titre absent de la liste fournie. Une note peut n'avoir aucune, "
    "une, ou plusieurs phrases de liaison."
)


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text.strip())
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def generate_draft(provider: LLMProvider, source_path: Path, content: str) -> Note:
    prompt = f"Fichier source : {source_path}\n\n```\n{content}\n```"
    raw = provider.complete(prompt, system=NOTE_SYSTEM_PROMPT, max_tokens=4096)
    data = _parse_json(raw)
    return Note(
        title=str(data.get("title") or source_path.stem).strip() or source_path.stem,
        source_path=str(source_path),
        tags=[str(t).lower().strip() for t in data.get("tags", []) if str(t).strip()],
        summary=str(data.get("summary", "")).strip(),
        body=str(data.get("body", "")).strip() or content,
        candidate_topics=[str(t).strip() for t in data.get("candidate_topics", []) if str(t).strip()],
    )


def propose_links(provider: LLMProvider, notes: list[Note]) -> dict[str, list[str]]:
    """Retourne {titre_note: [phrases de liaison a inserer]}."""
    if len(notes) < 2:
        return {}

    catalog = [
        {"title": n.title, "summary": n.summary, "candidate_topics": n.candidate_topics} for n in notes
    ]
    prompt = "Notes du vault :\n" + json.dumps(catalog, ensure_ascii=False, indent=2)
    raw = provider.complete(prompt, system=LINKING_SYSTEM_PROMPT, max_tokens=4096)
    data = _parse_json(raw)
    links_raw = data.get("links", []) if isinstance(data, dict) else []

    valid_titles = {n.title for n in notes}
    result: dict[str, list[str]] = {}
    for item in links_raw:
        if not isinstance(item, dict):
            continue
        note_title = str(item.get("note", ""))
        sentence = str(item.get("sentence", "")).strip()
        if note_title in valid_titles and sentence:
            result.setdefault(note_title, []).append(sentence)
    return result


def apply_links(notes: list[Note], links_by_title: dict[str, list[str]]) -> None:
    """Insere les phrases de liaison proposees sous une section '## Liens' de chaque
    note, en place. Idempotent : une section '## Liens' preexistante (note reutilisee
    telle quelle depuis le cache d'un build precedent) est remplacee, jamais dupliquee."""
    for note in notes:
        sentences = links_by_title.get(note.title)
        base_body = _LIENS_SECTION.sub("", note.body.rstrip())
        if not sentences:
            note.body = base_body
            continue
        links_section = "\n".join(f"- {s}" for s in sentences)
        note.body = f"{base_body}\n\n## Liens\n{links_section}\n"
