from __future__ import annotations

from typer.testing import CliRunner

from cortex.cli import _expand_exclude_argv, app

runner = CliRunner()


def test_version_flag_exits_zero_and_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "cortex" in result.stdout


def test_help_exits_zero() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0


def test_build_help_lists_expected_options() -> None:
    result = runner.invoke(app, ["build", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.stdout
    assert "--provider" in result.stdout
    assert "--dry-run" in result.stdout


def test_config_show_makes_no_network_call(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CORTEX_API_KEY", raising=False)
    monkeypatch.setenv("CORTEX_PROVIDER", "anthropic")

    result = runner.invoke(app, ["config", "show"])

    assert result.exit_code == 0
    assert "provider" in result.stdout
    assert "absente" in result.stdout


def test_config_init_writes_starter_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("cortex.cli.write_starter_config", lambda: tmp_path / "config.toml")

    result = runner.invoke(app, ["config", "init"])

    assert result.exit_code == 0
    assert "config.toml" in result.stdout


def test_openai_compatible_without_model_fails_cleanly() -> None:
    result = runner.invoke(app, ["config", "show", "--provider", "openai-compatible"])
    assert result.exit_code == 1


def test_triage_without_api_key_degrades_gracefully_instead_of_crashing(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CORTEX_API_KEY", raising=False)
    (tmp_path / "note.md").write_text("A perfectly normal note.", encoding="utf-8")

    result = runner.invoke(app, ["triage", str(tmp_path)])

    assert result.exit_code == 0
    assert "note.md" in result.stdout


def test_expand_exclude_argv_splits_space_separated_values() -> None:
    argv = ["cortex", "build", ".", "--exclude", ".gitignore", "dataset.csv", "instructions", "instructions.md"]

    assert _expand_exclude_argv(argv) == [
        "cortex", "build", ".",
        "--exclude", ".gitignore",
        "--exclude", "dataset.csv",
        "--exclude", "instructions",
        "--exclude", "instructions.md",
    ]


def test_expand_exclude_argv_stops_at_next_flag() -> None:
    argv = ["build", ".", "--exclude", "data", "*.csv", "--dry-run"]

    assert _expand_exclude_argv(argv) == [
        "build", ".", "--exclude", "data", "--exclude", "*.csv", "--dry-run",
    ]


def test_expand_exclude_argv_leaves_repeated_flag_form_unchanged() -> None:
    argv = ["build", ".", "--exclude", "data", "--exclude", "*.csv"]

    assert _expand_exclude_argv(argv) == argv


def test_expand_exclude_argv_handles_trailing_exclude_with_no_values() -> None:
    argv = ["build", ".", "--exclude"]

    assert _expand_exclude_argv(argv) == argv

