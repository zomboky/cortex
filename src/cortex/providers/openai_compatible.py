from __future__ import annotations

from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Couvre tout endpoint compatible /v1/chat/completions : Ollama local ou cloud,
    vLLM, LM Studio, etc. Aucun code specifique a un fournisseur -- juste un base_url configurable."""

    def __init__(self, api_key: str | None, base_url: str | None, model: str) -> None:
        import openai

        self._client = openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url)
        self.model = model

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
