from __future__ import annotations

from pathlib import Path

import yaml

from cortex.vault.notes import Note
from cortex.vault.writer import render_note, sanitize_filename, write_vault


def test_sanitize_filename_strips_illegal_characters() -> None:
    assert sanitize_filename('Title: "special" / <chars> | test?') == "Title special chars test"


def test_sanitize_filename_collapses_whitespace() -> None:
    assert sanitize_filename("Title   with    spaces") == "Title with spaces"


def test_sanitize_filename_empty_falls_back_to_placeholder() -> None:
    assert sanitize_filename("///???") == "Note sans titre"


def test_sanitize_filename_keeps_unicode() -> None:
    assert sanitize_filename("Réflexions à propos de l'été") == "Réflexions à propos de l'été"


def test_render_note_includes_frontmatter_and_body() -> None:
    note = Note(
        title="My Note",
        source_path="src/a.md",
        tags=["tag1", "tag2"],
        summary="A summary.",
        body="Content.",
        created="2026-08-06",
    )
    rendered = render_note(note)
    assert rendered.startswith("---\n")
    fm_text = rendered.split("---\n")[1]
    fm = yaml.safe_load(fm_text)
    assert fm["title"] == "My Note"
    assert fm["tags"] == ["tag1", "tag2"]
    assert fm["source_path"] == "src/a.md"
    assert "Content." in rendered
    assert "A summary." in rendered


def test_render_note_without_summary_skips_summary_section() -> None:
    note = Note(title="No Summary", source_path="a.md", body="Body only.")
    rendered = render_note(note)
    assert "## Resume" not in rendered
    assert "Body only." in rendered


def test_write_vault_dedupes_colliding_filenames(tmp_path: Path) -> None:
    notes = [
        Note(title="Same Title", source_path="a.md", body="A"),
        Note(title="Same Title", source_path="b.md", body="B"),
    ]
    written = write_vault(notes, tmp_path)

    assert len(written) == 2
    assert len(set(written)) == 2
    assert (tmp_path / "Same Title.md").exists()
    assert (tmp_path / "Same Title (2).md").exists()


def test_write_vault_creates_output_directory(tmp_path: Path) -> None:
    vault_dir = tmp_path / "nested" / "vault"
    write_vault([Note(title="A", source_path="a.md", body="x")], vault_dir)
    assert vault_dir.is_dir()
    assert (vault_dir / "A.md").exists()
