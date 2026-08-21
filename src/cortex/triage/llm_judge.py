"""Passe LLM par lot pour les fichiers juges 'ambigus' par l'heuristique."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..providers.base import LLMProvider

EXCERPT_HEAD_BYTES = 2048
EXCERPT_TAIL_BYTES = 1024

SYSTEM_PROMPT = (
    "Tu es un assistant de tri de fichiers pour une base de connaissances. Pour chaque "
    "fichier presente (chemin + extrait), decide s'il contient un contenu suffisamment "
    "significatif (texte lisible, documentation, notes, code, donnees structurees "
    "comprehensibles) pour meriter d'etre integre a la base, ou si c'est du bruit "
    "(donnees encodees, exports illisibles, artefacts generes sans valeur informative). "
    'Reponds UNIQUEMENT avec un objet JSON : '
    '{"verdicts": [{"path": "<chemin exact fourni>", "decision": "keep"|"drop", "reason": "<une phrase>"}]}. '
    "Un verdict par fichier presente, dans le meme ordre, sans texte hors du JSON."
)


@dataclass(frozen=True)
class JudgeVerdict:
    path: str
    decision: str  # "keep" | "drop"
    reason: str


def _build_excerpt(path: Path) -> str:
    data = path.read_bytes()
    if len(data) <= EXCERPT_HEAD_BYTES + EXCERPT_TAIL_BYTES:
        chunk = data
    else:
        chunk = data[:EXCERPT_HEAD_BYTES] + b"\n...[tronque]...\n" + data[-EXCERPT_TAIL_BYTES:]
    return chunk.decode("utf-8", errors="replace")


def build_batch_prompt(paths: list[Path]) -> str:
    sections = [f"### Fichier: {p}\n```\n{_build_excerpt(p)}\n```" for p in paths]
    return "\n\n".join(sections)


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def parse_verdicts(raw: str, paths: list[Path]) -> list[JudgeVerdict]:
    """Parse la reponse JSON du LLM. Toute entree manquante ou invalide est
    conservee (keep) par defaut -- ne jamais ecarter silencieusement sur un echec LLM."""
    verdicts_raw: list = []
    try:
        data = _extract_json(raw)
        verdicts_raw = data.get("verdicts", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, ValueError):
        verdicts_raw = []

    by_path: dict[str, JudgeVerdict] = {}
    for v in verdicts_raw:
        if not isinstance(v, dict) or "path" not in v:
            continue
        decision = v.get("decision", "keep")
        if decision not in ("keep", "drop"):
            decision = "keep"
        by_path[str(v["path"])] = JudgeVerdict(path=str(v["path"]), decision=decision, reason=str(v.get("reason", "")))

    results = []
    for p in paths:
        key = str(p)
        results.append(
            by_path.get(key)
            or JudgeVerdict(path=key, decision="keep", reason="verdict LLM manquant ou invalide -- conserve par defaut")
        )
    return results


def judge_batch(provider: LLMProvider, paths: list[Path]) -> list[JudgeVerdict]:
    if not paths:
        return []
    prompt = build_batch_prompt(paths)
    # Genereux (pas juste "assez pour du JSON court") : certains providers (ex. Qwen3 en
    # local via openai-compatible) emettent un raisonnement interne qui compte contre ce
    # meme budget avant le JSON final -- un plafond trop bas tronque la reponse et fait
    # tomber tout le lot sur le defaut "keep" (voir parse_verdicts), pas juste ce fichier.
    raw = provider.complete(prompt, system=SYSTEM_PROMPT, max_tokens=8192)
    return parse_verdicts(raw, paths)
