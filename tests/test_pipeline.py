from __future__ import annotations

import json
from pathlib import Path

import pytest

import cortex.pipeline as pipeline_module
from cortex.config import CortexConfig
from cortex.providers.base import LLMProvider


class _FakeVaultProvider(LLMProvider):
    """File une reponse par appel attendu ; leve si sollicite plus que prevu, ce qui
    sert de preuve qu'aucun appel LLM superflu n'a eu lieu."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def complete(self, prompt: str, *, system=None, max_tokens: int = 4096) -> str:
        self.calls += 1
        if not self._responses:
            raise AssertionError("appel LLM inattendu -- aucun changement ne le justifiait")
        return self._responses.pop(0)


class _CrashingVaultProvider(LLMProvider):
    """Repond normalement pour les N premiers appels puis leve RuntimeError -- simule un
    crash en cours de route (ex. le provider claude-cli qui epuise ses retries apres
    avoir tape la limite d'usage Claude)."""

    def __init__(self, responses: list[str], crash_after: int) -> None:
        self._responses = list(responses)
        self._crash_after = crash_after
        self.calls = 0

    def complete(self, prompt: str, *, system=None, max_tokens: int = 4096) -> str:
        self.calls += 1
        if self.calls > self._crash_after:
            raise RuntimeError("claude CLI a echoue apres 4 tentatives : limite d'usage atteinte")
        return self._responses.pop(0)


def _draft_response(title: str) -> str:
    return json.dumps(
        {
            "title": title,
            "tags": ["tag"],
            "summary": f"resume de {title}",
            "body": f"corps de {title}",
            "candidate_topics": [title],
        }
    )


def _links_response() -> str:
    return json.dumps({"links": []})


def _patch_providers(monkeypatch, vault_provider: LLMProvider) -> None:
    monkeypatch.setattr(pipeline_module, "get_triage_provider", lambda config: None)
    monkeypatch.setattr(pipeline_module, "get_vault_provider", lambda config: vault_provider)


def _patch_graphify(monkeypatch) -> dict:
    calls = {"count": 0}

    def _fake_run_graphify(vault_dir: Path, extra_args=None):
        calls["count"] += 1
        (vault_dir / "graphify-out").mkdir(parents=True, exist_ok=True)
        return None

    monkeypatch.setattr(pipeline_module.graphify_bridge, "run_graphify", _fake_run_graphify)
    return calls


def _make_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.md").write_text("Contenu A", encoding="utf-8")
    (source / "b.md").write_text("Contenu B", encoding="utf-8")
    return source


def test_first_build_calls_llm_once_per_file_plus_linking(monkeypatch, tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out"
    provider = _FakeVaultProvider([_draft_response("A"), _draft_response("B"), _links_response()])
    _patch_providers(monkeypatch, provider)
    graphify_calls = _patch_graphify(monkeypatch)

    result = pipeline_module.build(source, output, CortexConfig())

    assert provider.calls == 3  # 2 brouillons + 1 passe de liens
    assert len(result.notes) == 2
    assert graphify_calls["count"] == 1
    assert (output / ".cortex" / "vault-cache.json").is_file()


def test_unchanged_rebuild_makes_zero_llm_calls_and_skips_graphify(monkeypatch, tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out"

    provider1 = _FakeVaultProvider([_draft_response("A"), _draft_response("B"), _links_response()])
    _patch_providers(monkeypatch, provider1)
    graphify_calls = _patch_graphify(monkeypatch)
    pipeline_module.build(source, output, CortexConfig())
    assert graphify_calls["count"] == 1

    provider2 = _FakeVaultProvider([])  # tout appel leve -- rien ne doit rappeler le LLM
    _patch_providers(monkeypatch, provider2)
    result2 = pipeline_module.build(source, output, CortexConfig())

    assert provider2.calls == 0
    assert len(result2.notes) == 2
    assert graphify_calls["count"] == 1  # pas relance, rien n'a change


def test_modifying_one_file_only_regenerates_that_note(monkeypatch, tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out"

    provider1 = _FakeVaultProvider([_draft_response("A"), _draft_response("B"), _links_response()])
    _patch_providers(monkeypatch, provider1)
    graphify_calls = _patch_graphify(monkeypatch)
    pipeline_module.build(source, output, CortexConfig())

    (source / "b.md").write_text("Contenu B modifie", encoding="utf-8")

    provider2 = _FakeVaultProvider([_draft_response("B v2"), _links_response()])
    _patch_providers(monkeypatch, provider2)
    result2 = pipeline_module.build(source, output, CortexConfig())

    assert provider2.calls == 2  # 1 seul brouillon (B) + la passe de liens
    titles = {n.title for n in result2.notes}
    assert titles == {"A", "B v2"}
    assert graphify_calls["count"] == 2  # le vault a change -> graphify relance


def test_crash_mid_build_persists_already_generated_notes_to_cache(monkeypatch, tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out"

    provider1 = _CrashingVaultProvider([_draft_response("A")], crash_after=1)
    _patch_providers(monkeypatch, provider1)
    _patch_graphify(monkeypatch)

    with pytest.raises(RuntimeError):
        pipeline_module.build(source, output, CortexConfig())

    # Meme si le build a plante avant la fin (ici en generant la note de b.md), la note
    # deja generee avec succes (a.md) doit avoir ete persistee sur disque -- pas
    # seulement gardee en memoire jusqu'a la fin du build.
    cache_path = output / ".cortex" / "vault-cache.json"
    assert cache_path.is_file()
    cache_data = json.loads(cache_path.read_text(encoding="utf-8"))
    assert any(entry["title"] == "A" for entry in cache_data.values())

    # Relancer le build ne doit pas regenerer A (deja en cache), seulement B.
    provider2 = _FakeVaultProvider([_draft_response("B"), _links_response()])
    _patch_providers(monkeypatch, provider2)
    result2 = pipeline_module.build(source, output, CortexConfig())

    assert provider2.calls == 2  # 1 seul brouillon (B, pas A) + la passe de liens
    titles = {n.title for n in result2.notes}
    assert titles == {"A", "B"}


def test_new_file_added_triggers_regeneration_for_new_file_only(monkeypatch, tmp_path: Path) -> None:
    source = _make_source(tmp_path)
    output = tmp_path / "out"

    provider1 = _FakeVaultProvider([_draft_response("A"), _draft_response("B"), _links_response()])
    _patch_providers(monkeypatch, provider1)
    _patch_graphify(monkeypatch)
    pipeline_module.build(source, output, CortexConfig())

    (source / "c.md").write_text("Contenu C", encoding="utf-8")

    provider2 = _FakeVaultProvider([_draft_response("C"), _links_response()])
    _patch_providers(monkeypatch, provider2)
    result2 = pipeline_module.build(source, output, CortexConfig())

    assert provider2.calls == 2  # 1 seul brouillon (C) + la passe de liens
    titles = {n.title for n in result2.notes}
    assert titles == {"A", "B", "C"}
