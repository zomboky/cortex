from __future__ import annotations

import pytest

from cortex.config import CortexConfig
from cortex.providers.registry import MissingAPIKeyError, get_triage_provider, get_vault_provider


class _FakeClient:
    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs


def test_anthropic_without_api_key_raises_missing_api_key_error() -> None:
    config = CortexConfig(provider="anthropic", api_key=None)
    with pytest.raises(MissingAPIKeyError):
        get_triage_provider(config)


def test_anthropic_with_api_key_builds_provider(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    config = CortexConfig(provider="anthropic", api_key="sk-test")

    provider = get_triage_provider(config)

    assert provider.model == config.triage_model


def test_vault_provider_uses_vault_model(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    config = CortexConfig(provider="anthropic", api_key="sk-test")

    provider = get_vault_provider(config)

    assert provider.model == config.vault_model


def test_openai_compatible_without_api_key_does_not_raise(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeClient)
    config = CortexConfig(provider="openai-compatible", api_key=None, base_url="http://x/v1", triage_model="llama3.1")

    provider = get_triage_provider(config)

    assert provider.model == "llama3.1"


def test_unknown_provider_raises_plain_value_error_not_missing_key() -> None:
    config = CortexConfig(provider="mystery", api_key="sk-test")
    with pytest.raises(ValueError):
        get_triage_provider(config)


def test_triage_provider_gets_triage_effort(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    config = CortexConfig(provider="anthropic", api_key="sk-test", triage_effort="low", vault_effort="xhigh")

    provider = get_triage_provider(config)

    assert provider.effort == "low"


def test_vault_provider_gets_vault_effort(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeClient)
    config = CortexConfig(provider="anthropic", api_key="sk-test", triage_effort="low", vault_effort="xhigh")

    provider = get_vault_provider(config)

    assert provider.effort == "xhigh"
