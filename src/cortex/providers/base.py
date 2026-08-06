from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface minimale pour un backend LLM. complete_batch() a une implementation
    par defaut sequentielle ; un provider peut la surcharger (ex. parallelisme, Batches API)."""

    @abstractmethod
    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096) -> str: ...

    def complete_batch(
        self, prompts: list[str], *, system: str | None = None, max_tokens: int = 4096
    ) -> list[str]:
        return [self.complete(p, system=system, max_tokens=max_tokens) for p in prompts]
