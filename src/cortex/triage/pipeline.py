"""Orchestration : heuristique -> lot -> LLM -> decision finale."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..cache import ProjectCache, hash_file
from ..providers.base import LLMProvider
from . import heuristics
from .heuristics import Verdict
from .llm_judge import judge_batch

DEFAULT_BATCH_SIZE = 15


def _matches_exclude(path: Path, root: Path, patterns: list[str]) -> str | None:
    """Retourne le motif qui exclut `path`, ou None. Un motif matche si : nom exact
    d'un composant du chemin relatif (ex. "data", "google-earth-engine-api-key" --
    exclut tout le sous-arbre), ou glob sur le chemin relatif complet ou sur le nom
    du fichier seul (ex. "*.csv", "secrets/*.json")."""
    rel = path.relative_to(root)
    rel_str = rel.as_posix()
    parts = rel.parts
    for pattern in patterns:
        if pattern in parts:
            return pattern
        if fnmatch.fnmatch(rel_str, pattern) or fnmatch.fnmatch(path.name, pattern):
            return pattern
    return None


@dataclass(frozen=True)
class TriageDecision:
    path: Path
    decision: Literal["keep", "drop"]
    reason: str
    source: Literal["heuristic", "llm"]

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "decision": self.decision,
            "reason": self.reason,
            "source": self.source,
        }


def iter_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def run(
    root: Path,
    provider: LLMProvider | None,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    cache: ProjectCache | None = None,
    exclude: list[str] | None = None,
) -> list[TriageDecision]:
    """`cache`, si fourni, evite de rappeler le LLM pour un fichier ambigu deja juge
    lors d'un run precedent et dont le contenu n'a pas change depuis (meme hash).
    `exclude`, si fourni, ecarte un fichier avant meme l'heuristique -- ni triage LLM
    ni lecture de contenu -- des que son chemin relatif matche un des motifs (nom de
    composant exact ou glob, voir `_matches_exclude`)."""
    decisions: list[TriageDecision] = []
    ambiguous: list[Path] = []
    exclude = exclude or []

    for f in iter_files(root):
        excluded_by = _matches_exclude(f, root, exclude) if exclude else None
        if excluded_by is not None:
            decisions.append(
                TriageDecision(path=f, decision="drop", reason=f"exclu via --exclude ({excluded_by!r})", source="heuristic")
            )
            continue

        result = heuristics.classify_file(f)
        if result.verdict != Verdict.AMBIGUOUS:
            decisions.append(
                TriageDecision(
                    path=f,
                    decision="keep" if result.verdict == Verdict.KEEP else "drop",
                    reason=result.reason,
                    source="heuristic",
                )
            )
            continue

        cached = cache.cached_triage_decision(f) if cache else None
        if cached is not None:
            decisions.append(
                TriageDecision(f, cached["decision"], f"{cached['reason']} (cache : fichier inchange)", "llm")
            )
        else:
            ambiguous.append(f)

    if not ambiguous:
        return decisions

    if provider is None:
        for f in ambiguous:
            decisions.append(
                TriageDecision(f, "keep", "aucun provider LLM configure -- conserve par defaut", "heuristic")
            )
        return decisions

    for i in range(0, len(ambiguous), batch_size):
        batch = ambiguous[i : i + batch_size]
        verdicts_by_path = {v.path: v for v in judge_batch(provider, batch)}
        for f in batch:
            verdict = verdicts_by_path.get(str(f))
            if verdict is None:
                decision = TriageDecision(f, "keep", "verdict LLM absent -- conserve par defaut", "llm")
            else:
                decision = TriageDecision(f, verdict.decision, verdict.reason, "llm")
            decisions.append(decision)
            if cache is not None:
                cache.record_triage_decision(
                    f, hash_file(f), decision=decision.decision, reason=decision.reason, source=decision.source
                )

    return decisions
