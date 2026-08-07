from __future__ import annotations

import json
from pathlib import Path

from cortex.providers.base import LLMProvider
from cortex.triage.heuristics import AUTO_KEEP_SIZE_CEILING
from cortex.triage.pipeline import run


class _FakeProvider(LLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, system=None, max_tokens: int = 4096) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def _make_ambiguous_file(tmp_path: Path, name: str, size: int) -> Path:
    content = ("Une phrase de texte normal et varie sur un sujet quelconque. " * ((size // 62) + 1))[:size]
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    assert path.stat().st_size > AUTO_KEEP_SIZE_CEILING
    return path


def test_heuristic_only_files_never_call_llm(tmp_path: Path) -> None:
    (tmp_path / "note.md").write_text("Une note tout a fait normale.", encoding="utf-8")
    noisy_dir = tmp_path / "node_modules"
    noisy_dir.mkdir()
    (noisy_dir / "pkg.js").write_text("bruit", encoding="utf-8")

    provider = _FakeProvider([])
    decisions = run(tmp_path, provider)

    assert all(d.source == "heuristic" for d in decisions)
    by_name = {d.path.name: d.decision for d in decisions}
    assert by_name["note.md"] == "keep"
    assert by_name["pkg.js"] == "drop"
    assert provider.prompts == []


def test_ambiguous_files_get_llm_verdict(tmp_path: Path) -> None:
    big_file = _make_ambiguous_file(tmp_path, "big.txt", 300_000)

    response = json.dumps({"verdicts": [{"path": str(big_file), "decision": "drop", "reason": "pas utile"}]})
    provider = _FakeProvider([response])

    decisions = run(tmp_path, provider, batch_size=10)

    match = next(d for d in decisions if d.path == big_file)
    assert match.decision == "drop"
    assert match.source == "llm"
    assert match.reason == "pas utile"


def test_malformed_llm_response_defaults_to_keep(tmp_path: Path) -> None:
    big_file = _make_ambiguous_file(tmp_path, "big.txt", 300_000)

    provider = _FakeProvider(["ceci n'est pas du json"])
    decisions = run(tmp_path, provider, batch_size=10)

    match = next(d for d in decisions if d.path == big_file)
    assert match.decision == "keep"
    assert match.source == "llm"
    assert "manquant ou invalide" in match.reason


def test_no_provider_keeps_ambiguous_files_by_default(tmp_path: Path) -> None:
    big_file = _make_ambiguous_file(tmp_path, "big.txt", 300_000)

    decisions = run(tmp_path, None)

    match = next(d for d in decisions if d.path == big_file)
    assert match.decision == "keep"
    assert match.source == "heuristic"


def test_exclude_by_exact_path_component_drops_whole_subtree(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "big.csv").write_text("1,2,3", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Une note normale.", encoding="utf-8")

    provider = _FakeProvider([])
    decisions = run(tmp_path, provider, exclude=["data"])

    by_name = {d.path.name: d for d in decisions}
    assert by_name["big.csv"].decision == "drop"
    assert "exclu via --exclude" in by_name["big.csv"].reason
    assert by_name["notes.md"].decision == "keep"
    assert provider.prompts == []


def test_exclude_by_glob_matches_filename(tmp_path: Path) -> None:
    (tmp_path / "report.csv").write_text("a,b,c", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Une note normale.", encoding="utf-8")

    decisions = run(tmp_path, None, exclude=["*.csv"])

    by_name = {d.path.name: d.decision for d in decisions}
    assert by_name["report.csv"] == "drop"
    assert by_name["notes.md"] == "keep"


def test_excluded_ambiguous_file_never_reaches_llm(tmp_path: Path) -> None:
    big_file = _make_ambiguous_file(tmp_path, "secret.json", 300_000)

    provider = _FakeProvider([])  # leve si jamais appele
    decisions = run(tmp_path, provider, batch_size=10, exclude=["secret.json"])

    match = next(d for d in decisions if d.path == big_file)
    assert match.decision == "drop"
    assert provider.prompts == []


def test_sample_corpus_noisy_json_is_dropped_by_heuristic_not_llm(sample_corpus: Path) -> None:
    provider = _FakeProvider([])  # aucune reponse dispo -> echoue si jamais appele
    decisions = run(sample_corpus, provider)

    noisy = next(d for d in decisions if d.path.name == "random_bytes.json")
    assert noisy.decision == "drop"
    assert noisy.source == "heuristic"

    log = next(d for d in decisions if d.path.name == "build_cache.log")
    assert log.decision == "drop"
    assert log.source == "heuristic"

    md = next(d for d in decisions if d.path.name == "meeting-2024-01.md")
    assert md.decision == "keep"
