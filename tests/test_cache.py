from __future__ import annotations

from pathlib import Path

from cortex.cache import ProjectCache, composition_hash, hash_file


def test_hash_file_changes_with_content(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text("v1", encoding="utf-8")
    h1 = hash_file(f)
    f.write_text("v2", encoding="utf-8")
    h2 = hash_file(f)
    assert h1 != h2


def test_composition_hash_ignores_order() -> None:
    a = [("x", "hx"), ("y", "hy")]
    b = [("y", "hy"), ("x", "hx")]
    assert composition_hash(a) == composition_hash(b)


def test_composition_hash_changes_with_content() -> None:
    a = [("x", "hx")]
    b = [("x", "hx2")]
    assert composition_hash(a) != composition_hash(b)


def test_cached_triage_decision_none_when_absent(tmp_path: Path) -> None:
    cache = ProjectCache.load(tmp_path / "out")
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    assert cache.cached_triage_decision(f) is None


def test_cached_triage_decision_invalidated_by_content_change(tmp_path: Path) -> None:
    cache = ProjectCache.load(tmp_path / "out")
    f = tmp_path / "a.txt"
    f.write_text("hello", encoding="utf-8")
    cache.record_triage_decision(f, hash_file(f), decision="keep", reason="ok", source="llm")
    assert cache.cached_triage_decision(f) is not None

    f.write_text("hello, modifie", encoding="utf-8")
    assert cache.cached_triage_decision(f) is None


def test_cached_note_none_when_note_file_missing(tmp_path: Path) -> None:
    cache = ProjectCache.load(tmp_path / "out")
    src = tmp_path / "a.txt"
    src.write_text("contenu", encoding="utf-8")
    note_path = tmp_path / "does-not-exist.md"

    class _N:
        title, tags, summary, body, candidate_topics, created = "T", [], "s", "b", [], "2026-01-01"

    file_hash = hash_file(src)
    cache.record_note(src, file_hash, note_path, _N())
    assert cache.cached_note(src, file_hash) is None  # note_path n'existe pas sur disque


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    cache = ProjectCache.load(output_dir)
    src = tmp_path / "a.txt"
    src.write_text("contenu", encoding="utf-8")
    note_path = output_dir / "vault" / "A.md"
    note_path.parent.mkdir(parents=True)
    note_path.write_text("# A", encoding="utf-8")

    class _N:
        title, tags, summary, body, candidate_topics, created = "A", ["t"], "s", "b", ["topic"], "2026-01-01"

    file_hash = hash_file(src)
    cache.record_note(src, file_hash, note_path, _N())
    cache.record_triage_decision(src, file_hash, decision="keep", reason="r", source="llm")
    cache.graphify["vault_hash"] = "abc123"
    cache.save()

    assert (output_dir / ".cortex" / "vault-cache.json").is_file()
    assert (output_dir / ".cortex" / "triage-cache.json").is_file()
    assert (output_dir / ".cortex" / "graphify-cache.json").is_file()

    reloaded = ProjectCache.load(output_dir)
    assert reloaded.cached_note(src, file_hash) is not None
    assert reloaded.cached_triage_decision(src) is not None
    assert reloaded.graphify["vault_hash"] == "abc123"
