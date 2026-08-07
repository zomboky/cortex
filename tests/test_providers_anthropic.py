from __future__ import annotations

from cortex.providers.anthropic_provider import AnthropicProvider


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeMessage("reponse factice")


class _FakeAnthropicClient:
    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.messages = _FakeMessages()


def test_complete_calls_client_with_expected_params_and_returns_text(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)

    provider = AnthropicProvider(api_key="sk-test", model="claude-haiku-4-5")
    result = provider.complete("Bonjour", system="Tu es un assistant.", max_tokens=123)

    assert result == "reponse factice"
    call = provider._client.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5"
    assert call["max_tokens"] == 123
    assert call["system"] == "Tu es un assistant."
    assert call["messages"] == [{"role": "user", "content": "Bonjour"}]
    assert provider._client.init_kwargs["api_key"] == "sk-test"


def test_complete_without_system_omits_the_kwarg(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    provider.complete("Bonjour")

    call = provider._client.messages.calls[0]
    assert "system" not in call


def test_effort_is_passed_as_output_config(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5", effort="xhigh")
    provider.complete("Bonjour")

    call = provider._client.messages.calls[0]
    assert call["output_config"] == {"effort": "xhigh"}


def test_no_effort_omits_output_config(monkeypatch) -> None:
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", _FakeAnthropicClient)

    provider = AnthropicProvider(api_key="sk-test", model="claude-sonnet-5")
    provider.complete("Bonjour")

    call = provider._client.messages.calls[0]
    assert "output_config" not in call
