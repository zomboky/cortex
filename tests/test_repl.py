from __future__ import annotations

from types import SimpleNamespace

import pytest
from rich.console import Console

from cortex.config import CortexConfig
from cortex.repl import (
    SessionState,
    _dispatch_slash,
    _session_flags,
    dispatch_line,
    format_status_line,
    pick_effort,
    pick_model,
    pick_provider,
    render_banner,
)


def _console() -> Console:
    return Console(record=True, width=200)


def test_render_banner_contains_expected_segments() -> None:
    console = _console()
    console.print(render_banner())
    text = console.export_text()
    assert "2.0.0" in text
    assert "session interactive" in text


def test_render_banner_colors_c_and_x_violet_only() -> None:
    from cortex.repl import _VIOLET, render_banner

    group = render_banner()
    lines = [r for r in group.renderables if hasattr(r, "spans")]
    # first 9 lines are the wordmark rows; each has a violet C segment and violet X segment
    # but not the white O/R/T/E segment.
    violet_style = f"bold {_VIOLET}"
    for line in lines[:9]:
        styles = [span.style for span in line.spans]
        assert violet_style in styles
        assert "bold white" in styles


def test_format_status_line_reflects_config() -> None:
    config = CortexConfig(provider="claude-cli", triage_model="a", vault_model="b")
    text = format_status_line(config)
    assert "claude-cli" in text.plain


def test_session_flags_reflect_config() -> None:
    config = CortexConfig(
        provider="anthropic",
        triage_model="haiku",
        vault_model="sonnet",
        triage_effort="low",
        vault_effort="high",
        batch_size=20,
    )
    flags = _session_flags(config)
    assert flags == [
        "--provider", "anthropic",
        "--triage-model", "haiku",
        "--vault-model", "sonnet",
        "--triage-effort", "low",
        "--vault-effort", "high",
        "--batch-size", "20",
    ]


def test_dispatch_unknown_command_prints_message_and_does_not_raise() -> None:
    session = SessionState(config=CortexConfig())
    console = _console()
    dispatch_line("frobnicate", session, console)
    assert "Commande inconnue" in console.export_text()


def test_dispatch_line_build_threads_session_config(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_build(source, output_dir, config, **kwargs):
        captured["config"] = config
        return SimpleNamespace(triage_decisions=[], notes=[], vault_dir=output_dir, graphify_ran=False)

    monkeypatch.setattr("cortex.cli.pipeline_module.build", fake_build)
    session = SessionState(config=CortexConfig(provider="claude-cli"))
    console = _console()
    dispatch_line(f"build {tmp_path} --dry-run", session, console)
    assert captured["config"].provider == "claude-cli"


def test_dispatch_line_explicit_flag_overrides_session(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_build(source, output_dir, config, **kwargs):
        captured["config"] = config
        return SimpleNamespace(triage_decisions=[], notes=[], vault_dir=output_dir, graphify_ran=False)

    monkeypatch.setattr("cortex.cli.pipeline_module.build", fake_build)
    session = SessionState(config=CortexConfig(provider="claude-cli"))
    console = _console()
    dispatch_line(f"build {tmp_path} --dry-run --provider anthropic", session, console)
    assert captured["config"].provider == "anthropic"


def test_pick_provider_returns_selection(monkeypatch) -> None:
    import questionary

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(questionary, "select", lambda *a, **k: SimpleNamespace(ask=lambda: "claude-cli"))
    assert pick_provider("anthropic") == "claude-cli"


def test_pick_provider_returns_none_when_cancelled(monkeypatch) -> None:
    import questionary

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(questionary, "select", lambda *a, **k: SimpleNamespace(ask=lambda: None))
    assert pick_provider("anthropic") is None


def test_pick_provider_returns_none_when_not_interactive(monkeypatch) -> None:
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert pick_provider("anthropic") is None


def test_pick_model_returns_typed_value(monkeypatch) -> None:
    import questionary

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(questionary, "text", lambda *a, **k: SimpleNamespace(ask=lambda: "claude-opus-4-1"))
    assert pick_model("triage", None) == "claude-opus-4-1"


def test_pick_effort_returns_selection(monkeypatch) -> None:
    import questionary

    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setattr(questionary, "select", lambda *a, **k: SimpleNamespace(ask=lambda: "high"))
    assert pick_effort(None, "anthropic") == "high"


def test_provider_slash_command_updates_session_and_resets_model() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic", triage_model="haiku"))
    console = _console()
    _dispatch_slash("/provider claude-cli", session, console)
    assert session.config.provider == "claude-cli"


def test_provider_slash_command_rejects_unknown_provider() -> None:
    session = SessionState(config=CortexConfig())
    console = _console()
    _dispatch_slash("/provider not-a-provider", session, console)
    assert "Provider inconnu" in console.export_text()
    assert session.config.provider != "not-a-provider"


def test_model_slash_command_sets_both_by_default() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic"))
    console = _console()
    _dispatch_slash("/model claude-opus-4-1", session, console)
    assert session.config.triage_model == "claude-opus-4-1"
    assert session.config.vault_model == "claude-opus-4-1"


def test_model_slash_command_sets_single_target() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic", vault_model="sonnet"))
    console = _console()
    _dispatch_slash("/model triage claude-haiku-4-5", session, console)
    assert session.config.triage_model == "claude-haiku-4-5"
    assert session.config.vault_model == "sonnet"


def test_effort_slash_command_rejects_invalid_level() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic"))
    console = _console()
    _dispatch_slash("/effort not-a-level", session, console)
    assert "invalide" in console.export_text()


def test_effort_slash_command_sets_valid_level() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic"))
    console = _console()
    _dispatch_slash("/effort high", session, console)
    assert session.config.triage_effort == "high"
    assert session.config.vault_effort == "high"


def test_exclude_slash_command_accumulates() -> None:
    session = SessionState(config=CortexConfig())
    console = _console()
    _dispatch_slash("/exclude add a b c", session, console)
    assert session.exclude == ["a", "b", "c"]
    _dispatch_slash("/exclude remove b", session, console)
    assert session.exclude == ["a", "c"]
    _dispatch_slash("/exclude clear", session, console)
    assert session.exclude == []


def test_config_slash_command_prints_resolved_config() -> None:
    session = SessionState(config=CortexConfig(provider="anthropic"))
    console = _console()
    _dispatch_slash("/config", session, console)
    assert "provider" in console.export_text()


def test_repl_ctrl_c_does_not_exit(monkeypatch) -> None:
    from cortex.repl import run_repl

    lines = iter([KeyboardInterrupt(), "/exit"])

    def fake_read_line(console):
        item = next(lines)
        if isinstance(item, BaseException):
            raise item
        return item

    monkeypatch.setattr("cortex.repl._read_line", fake_read_line)
    run_repl(CortexConfig(), console=_console())


def test_repl_eof_exits_cleanly(monkeypatch) -> None:
    from cortex.repl import run_repl

    def fake_read_line(console):
        raise EOFError()

    monkeypatch.setattr("cortex.repl._read_line", fake_read_line)
    run_repl(CortexConfig(), console=_console())
