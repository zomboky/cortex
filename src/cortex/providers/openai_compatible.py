from __future__ import annotations

from .base import LLMProvider


class OpenAICompatibleProvider(LLMProvider):
    """Couvre tout endpoint compatible /v1/chat/completions : Ollama local ou cloud,
    vLLM, LM Studio, etc. Aucun code specifique a un fournisseur -- juste un base_url configurable."""

    def __init__(self, api_key: str | None, base_url: str | None, model: str, effort: str | None = None) -> None:
        # effort accepte pour une signature uniforme entre providers, mais ignore ici :
        # concept specifique a l'API Anthropic (output_config.effort), pas standardise
        # sur /v1/chat/completions.
        import openai

        # Timeout par defaut du SDK openai (600s) trop court pour un modele local
        # (ex. Qwen via llama.cpp) sous charge -- generation bien plus lente qu'une
        # API cloud, et un serveur partage avec d'autres requetes concurrentes peut
        # faire depasser 10 minutes une seule reponse. 1h de marge.
        self._client = openai.OpenAI(api_key=api_key or "not-needed", base_url=base_url, timeout=3600.0)
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
