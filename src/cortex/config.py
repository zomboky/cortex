"""Resolution de la configuration : flag CLI > variable d'env > config.toml > defaut.

Cortex et Graphify ont des configurations LLM totalement independantes :
Graphify ne lit que GEMINI_API_KEY/GOOGLE_API_KEY, jamais les variables
CORTEX_*/ANTHROPIC_* definies ici.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_PROVIDER = "anthropic"
DEFAULT_TRIAGE_MODEL = "claude-haiku-4-5"
DEFAULT_VAULT_MODEL = "claude-sonnet-5"
DEFAULT_BATCH_SIZE = 15

# Niveaux d'effort de raisonnement Claude (parametre output_config.effort de l'API
# Messages Anthropic). Ignore par les providers claude-cli et openai-compatible --
# specifique a l'API Anthropic directe.
VALID_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class CortexConfig:
    provider: str = DEFAULT_PROVIDER
    api_key: str | None = None
    base_url: str | None = None
    triage_model: str | None = DEFAULT_TRIAGE_MODEL
    vault_model: str | None = DEFAULT_VAULT_MODEL
    triage_effort: str | None = None
    vault_effort: str | None = None
    batch_size: int = DEFAULT_BATCH_SIZE

    def has_api_key(self) -> bool:
        return bool(self.api_key)


def config_file_path() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "cortex" / "config.toml"
    return Path.home() / ".config" / "cortex" / "config.toml"


def _read_config_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _pick(cli_value: Any, env: dict[str, str], env_name: str, file_section: dict[str, Any], file_key: str, default: Any) -> Any:
    if cli_value is not None:
        return cli_value
    env_value = env.get(env_name)
    if env_value:
        return env_value
    file_value = file_section.get(file_key)
    if file_value is not None:
        return file_value
    return default


def resolve_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    triage_model: str | None = None,
    vault_model: str | None = None,
    effort: str | None = None,
    triage_effort: str | None = None,
    vault_effort: str | None = None,
    base_url: str | None = None,
    batch_size: int | None = None,
    env: dict[str, str] | None = None,
    config_path: Path | None = None,
) -> CortexConfig:
    """Resout la config finale. Priorite : args (flags CLI) > env > config.toml > defauts."""
    env = env if env is not None else dict(os.environ)
    path = config_path if config_path is not None else config_file_path()
    file_data = _read_config_file(path)
    provider_section = file_data.get("provider", {})
    if not isinstance(provider_section, dict):
        provider_section = {}

    resolved_provider = _pick(provider, env, "CORTEX_PROVIDER", provider_section, "name", DEFAULT_PROVIDER)

    resolved_api_key = _pick(None, env, "CORTEX_API_KEY", provider_section, "api_key", None)
    if not resolved_api_key and resolved_provider == "anthropic":
        resolved_api_key = env.get("ANTHROPIC_API_KEY")

    resolved_base_url = _pick(base_url, env, "CORTEX_BASE_URL", provider_section, "base_url", None)

    resolved_model = _pick(model, env, "CORTEX_MODEL", provider_section, "model", None)

    default_triage = DEFAULT_TRIAGE_MODEL if resolved_provider in ("anthropic", "claude-cli") else None
    default_vault = DEFAULT_VAULT_MODEL if resolved_provider in ("anthropic", "claude-cli") else None

    resolved_triage_model = _pick(
        triage_model, env, "CORTEX_TRIAGE_MODEL", provider_section, "triage_model",
        resolved_model or default_triage,
    )
    resolved_vault_model = _pick(
        vault_model, env, "CORTEX_VAULT_MODEL", provider_section, "vault_model",
        resolved_model or default_vault,
    )

    resolved_effort = _pick(effort, env, "CORTEX_EFFORT", provider_section, "effort", None)
    resolved_triage_effort = _pick(
        triage_effort, env, "CORTEX_TRIAGE_EFFORT", provider_section, "triage_effort", resolved_effort
    )
    resolved_vault_effort = _pick(
        vault_effort, env, "CORTEX_VAULT_EFFORT", provider_section, "vault_effort", resolved_effort
    )
    for label, value in (("triage_effort", resolved_triage_effort), ("vault_effort", resolved_vault_effort)):
        if value is not None and value not in VALID_EFFORT_LEVELS:
            raise ValueError(
                f"{label} invalide : {value!r}. Valeurs acceptees : {', '.join(VALID_EFFORT_LEVELS)}."
            )

    resolved_batch_size = int(_pick(batch_size, env, "CORTEX_BATCH_SIZE", provider_section, "batch_size", DEFAULT_BATCH_SIZE))

    if resolved_provider == "openai-compatible" and not resolved_triage_model:
        raise ValueError(
            "CORTEX_TRIAGE_MODEL (ou --triage-model / --model) est requis avec provider=openai-compatible : "
            "les noms de modeles ne sont pas standardises (Ollama, etc.), Cortex ne devine pas."
        )
    if resolved_provider == "openai-compatible" and not resolved_vault_model:
        raise ValueError(
            "CORTEX_VAULT_MODEL (ou --vault-model / --model) est requis avec provider=openai-compatible."
        )

    return CortexConfig(
        provider=resolved_provider,
        api_key=resolved_api_key,
        base_url=resolved_base_url,
        triage_model=resolved_triage_model,
        vault_model=resolved_vault_model,
        triage_effort=resolved_triage_effort,
        vault_effort=resolved_vault_effort,
        batch_size=resolved_batch_size,
    )


STARTER_CONFIG_TOML = """\
# Configuration de cortex. Voir aussi les variables d'environnement
# CORTEX_PROVIDER, CORTEX_API_KEY, CORTEX_BASE_URL, CORTEX_MODEL,
# CORTEX_TRIAGE_MODEL, CORTEX_VAULT_MODEL, CORTEX_EFFORT, CORTEX_TRIAGE_EFFORT,
# CORTEX_VAULT_EFFORT, CORTEX_BATCH_SIZE
# (les flags CLI et les variables d'env priment sur ce fichier).

[provider]
# name = "anthropic"              # ou "claude-cli" (abonnement Claude Code local, sans cle API) ou "openai-compatible"
# api_key = "sk-..."              # prefere une variable d'env plutot que ce fichier en clair ; inutile avec claude-cli
# base_url = "http://localhost:11434/v1"   # pour openai-compatible (Ollama local ou cloud)
# model = "llama3.1:70b"          # requis pour openai-compatible (pas de defaut devine)
# triage_model = "claude-haiku-4-5"
# vault_model = "claude-sonnet-5"
# effort = "medium"               # low | medium | high | xhigh | max -- effort des DEUX etapes, provider anthropic seulement
# triage_effort = "low"           # surcharge effort pour le triage seul
# vault_effort = "high"           # surcharge effort pour la generation du vault seule
# batch_size = 15
"""


def write_starter_config(path: Path | None = None) -> Path:
    target = path if path is not None else config_file_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(STARTER_CONFIG_TOML, encoding="utf-8")
    return target
