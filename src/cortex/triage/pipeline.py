"""Orchestration : heuristique -> lot -> LLM -> decision finale."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ..providers.base import LLMProvider
from . import heuristics
from .heuristics import Verdict
from .llm_judge import judge_batch

DEFAULT_BATCH_SIZE = 15


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
) -> list[TriageDecision]:
    decisions: list[TriageDecision] = []
    ambiguous: list[Path] = []

    for f in iter_files(root):
        result = heuristics.classify_file(f)
        if result.verdict == Verdict.AMBIGUOUS:
            ambiguous.append(f)
        else:
            decisions.append(
                TriageDecision(
                    path=f,
                    decision="keep" if result.verdict == Verdict.KEEP else "drop",
                    reason=result.reason,
                    source="heuristic",
                )
            )

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
                decisions.append(TriageDecision(f, "keep", "verdict LLM absent -- conserve par defaut", "llm"))
            else:
                decisions.append(TriageDecision(f, verdict.decision, verdict.reason, "llm"))

    return decisions
