from __future__ import annotations

from ..config import CortexConfig
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .claude_cli_provider import ClaudeCLIProvider
from .openai_compatible import OpenAICompatibleProvider


class MissingAPIKeyError(ValueError):
    """Cle API absente. Distincte de ValueError pour permettre au triage de degrader
    proprement (fichiers ambigus gardes par defaut) plutot que de planter, alors que
    la generation du vault, elle, a strictement besoin d'un LLM et doit echouer."""


def get_triage_provider(config: CortexConfig) -> LLMProvider:
    return _build(config, config.triage_model, config.triage_effort)


def get_vault_provider(config: CortexConfig) -> LLMProvider:
    return _build(config, config.vault_model, config.vault_effort)


def _build(config: CortexConfig, model: str | None, effort: str | None) -> LLMProvider:
    if not model:
        raise ValueError("Aucun modele resolu pour cette etape.")
    if config.provider == "anthropic":
        if not config.api_key:
            raise MissingAPIKeyError("Aucune cle API trouvee. Definis CORTEX_API_KEY ou ANTHROPIC_API_KEY.")
        return AnthropicProvider(api_key=config.api_key, model=model, effort=effort)
    if config.provider == "claude-cli":
        return ClaudeCLIProvider(model=model, effort=effort)
    if config.provider == "openai-compatible":
        return OpenAICompatibleProvider(api_key=config.api_key, base_url=config.base_url, model=model, effort=effort)
    raise ValueError(f"Provider inconnu : {config.provider}")
