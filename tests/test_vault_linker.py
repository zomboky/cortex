from __future__ import annotations

from cortex.vault.linker import resolve_links
from cortex.vault.notes import Note


def test_exact_link_is_left_unchanged() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[Note B]] pour plus de details.")
    b = Note(title="Note B", source_path="b.md", body="Contenu B.")
    fixes = resolve_links([a, b])

    assert "[[Note B]]" in a.body
    assert any(f.resolution == "exact" for f in fixes)


def test_near_miss_case_is_rewritten_to_canonical_title() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[note b]] pour plus de details.")
    b = Note(title="Note B", source_path="b.md", body="Contenu B.")
    fixes = resolve_links([a, b])

    assert "[[Note B]]" in a.body
    assert "[[note b]]" not in a.body
    assert any(f.resolution == "rewritten" and f.resolved_target == "Note B" for f in fixes)


def test_near_miss_extra_whitespace_is_rewritten() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[Note   B]] pour plus.")
    b = Note(title="Note B", source_path="b.md", body="Contenu B.")
    resolve_links([a, b])

    assert "[[Note B]]" in a.body


def test_dangling_link_is_stripped_but_sentence_is_preserved() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[Note Inexistante]] pour plus de details.")
    fixes = resolve_links([a])

    assert "[[" not in a.body
    assert "]]" not in a.body
    assert "Voir Note Inexistante pour plus de details." in a.body
    assert any(f.resolution == "stripped" and f.resolved_target is None for f in fixes)


def test_aliased_link_preserves_display_text_when_rewritten() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[note b|ici]] pour plus.")
    b = Note(title="Note B", source_path="b.md", body="Contenu B.")
    resolve_links([a, b])

    assert "[[Note B|ici]]" in a.body


def test_aliased_dangling_link_keeps_only_display_text() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[Fantome|ici]] pour plus.")
    resolve_links([a])

    assert "[[" not in a.body
    assert "Voir ici pour plus." in a.body


def test_multiple_links_in_same_note_are_all_resolved() -> None:
    a = Note(title="Note A", source_path="a.md", body="Voir [[Note B]] et [[Note Fantome]].")
    b = Note(title="Note B", source_path="b.md", body="Contenu B.")
    resolve_links([a, b])

    assert "[[Note B]]" in a.body
    assert "[[Note Fantome]]" not in a.body
    assert "Note Fantome" in a.body
