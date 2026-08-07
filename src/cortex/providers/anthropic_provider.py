from __future__ import annotations

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, effort: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort

    def complete(self, prompt: str, *, system: str | None = None, max_tokens: int = 4096) -> str:
        kwargs: dict = {}
        if system:
            kwargs["system"] = system
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
