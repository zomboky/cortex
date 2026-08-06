from __future__ import annotations

from cortex.providers.openai_compatible import OpenAICompatibleProvider


class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeCompletion:
    def __init__(self, content: str) -> None:
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeCompletion("reponse ollama")


class _FakeChat:
    def __init__(self) -> None:
        self.completions = _FakeCompletions()


class _FakeOpenAIClient:
    def __init__(self, **kwargs) -> None:
        self.init_kwargs = kwargs
        self.chat = _FakeChat()


def test_base_url_and_api_key_are_passed_to_client(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAIClient)

    provider = OpenAICompatibleProvider(api_key="k", base_url="http://localhost:11434/v1", model="llama3.1:70b")

    assert provider._client.init_kwargs["base_url"] == "http://localhost:11434/v1"
    assert provider._client.init_kwargs["api_key"] == "k"


def test_missing_api_key_uses_placeholder_for_local_ollama(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAIClient)

    provider = OpenAICompatibleProvider(api_key=None, base_url="http://localhost:11434/v1", model="llama3.1:70b")

    assert provider._client.init_kwargs["api_key"] == "not-needed"


def test_complete_sends_system_and_user_messages(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAIClient)

    provider = OpenAICompatibleProvider(api_key="k", base_url="http://x/v1", model="llama3.1:70b")
    result = provider.complete("Salut", system="Systeme")

    assert result == "reponse ollama"
    call = provider._client.chat.completions.calls[0]
    assert call["model"] == "llama3.1:70b"
    assert call["messages"] == [{"role": "system", "content": "Systeme"}, {"role": "user", "content": "Salut"}]


def test_complete_without_system_only_sends_user_message(monkeypatch) -> None:
    import openai

    monkeypatch.setattr(openai, "OpenAI", _FakeOpenAIClient)

    provider = OpenAICompatibleProvider(api_key="k", base_url="http://x/v1", model="llama3.1:70b")
    provider.complete("Salut")

    call = provider._client.chat.completions.calls[0]
    assert call["messages"] == [{"role": "user", "content": "Salut"}]
