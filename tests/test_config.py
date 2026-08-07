from __future__ import annotations

from pathlib import Path

import pytest

from cortex.config import DEFAULT_TRIAGE_MODEL, DEFAULT_VAULT_MODEL, resolve_config


def test_defaults_when_nothing_set(tmp_path: Path) -> None:
    config = resolve_config(env={}, config_path=tmp_path / "missing.toml")
    assert config.provider == "anthropic"
    assert config.triage_model == DEFAULT_TRIAGE_MODEL
    assert config.vault_model == DEFAULT_VAULT_MODEL
    assert config.api_key is None
    assert config.batch_size == 15


def test_env_var_overrides_default(tmp_path: Path) -> None:
    env = {
        "CORTEX_PROVIDER": "openai-compatible",
        "CORTEX_MODEL": "llama3.1",
        "CORTEX_BASE_URL": "http://localhost:11434/v1",
    }
    config = resolve_config(env=env, config_path=tmp_path / "missing.toml")
    assert config.provider == "openai-compatible"
    assert config.triage_model == "llama3.1"
    assert config.vault_model == "llama3.1"
    assert config.base_url == "http://localhost:11434/v1"


def test_cli_flag_overrides_env(tmp_path: Path) -> None:
    env = {"CORTEX_PROVIDER": "openai-compatible", "CORTEX_MODEL": "llama3.1", "CORTEX_BASE_URL": "http://x/v1"}
    config = resolve_config(provider="anthropic", env=env, config_path=tmp_path / "missing.toml")
    assert config.provider == "anthropic"


def test_config_file_used_when_no_env_or_flag(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[provider]\nname = "openai-compatible"\nmodel = "llama3.1:70b"\nbase_url = "http://x/v1"\n',
        encoding="utf-8",
    )
    config = resolve_config(env={}, config_path=config_path)
    assert config.provider == "openai-compatible"
    assert config.triage_model == "llama3.1:70b"
    assert config.base_url == "http://x/v1"


def test_env_overrides_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[provider]\nname = "openai-compatible"\nmodel = "x"\n', encoding="utf-8")
    config = resolve_config(env={"CORTEX_PROVIDER": "anthropic"}, config_path=config_path)
    assert config.provider == "anthropic"


def test_api_key_falls_back_to_anthropic_api_key(tmp_path: Path) -> None:
    config = resolve_config(env={"ANTHROPIC_API_KEY": "sk-abc"}, config_path=tmp_path / "missing.toml")
    assert config.api_key == "sk-abc"


def test_cortex_api_key_takes_priority_over_anthropic_api_key(tmp_path: Path) -> None:
    env = {"CORTEX_API_KEY": "sk-cortex", "ANTHROPIC_API_KEY": "sk-anthropic"}
    config = resolve_config(env=env, config_path=tmp_path / "missing.toml")
    assert config.api_key == "sk-cortex"


def test_openai_compatible_requires_explicit_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_config(env={"CORTEX_PROVIDER": "openai-compatible"}, config_path=tmp_path / "missing.toml")


def test_openai_compatible_with_explicit_model_succeeds(tmp_path: Path) -> None:
    env = {"CORTEX_PROVIDER": "openai-compatible", "CORTEX_MODEL": "llama3.1:70b"}
    config = resolve_config(env=env, config_path=tmp_path / "missing.toml")
    assert config.triage_model == "llama3.1:70b"
    assert config.vault_model == "llama3.1:70b"


def test_effort_defaults_to_none(tmp_path: Path) -> None:
    config = resolve_config(env={}, config_path=tmp_path / "missing.toml")
    assert config.triage_effort is None
    assert config.vault_effort is None


def test_global_effort_applies_to_both_stages(tmp_path: Path) -> None:
    config = resolve_config(effort="medium", env={}, config_path=tmp_path / "missing.toml")
    assert config.triage_effort == "medium"
    assert config.vault_effort == "medium"


def test_stage_effort_overrides_global_effort(tmp_path: Path) -> None:
    config = resolve_config(
        effort="medium", triage_effort="low", vault_effort="xhigh", env={}, config_path=tmp_path / "missing.toml"
    )
    assert config.triage_effort == "low"
    assert config.vault_effort == "xhigh"


def test_effort_env_vars(tmp_path: Path) -> None:
    env = {"CORTEX_TRIAGE_EFFORT": "low", "CORTEX_VAULT_EFFORT": "max"}
    config = resolve_config(env=env, config_path=tmp_path / "missing.toml")
    assert config.triage_effort == "low"
    assert config.vault_effort == "max"


def test_invalid_effort_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        resolve_config(effort="ludicrous", env={}, config_path=tmp_path / "missing.toml")
