"""Unit tests for config/loader.py — configuration loading and merging."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from codesentinel.config.loader import (
    _resolve_user_config_path,
    load_config,
    merge_dicts,
)
from codesentinel.config.schema import CodeSentinelConfig
from codesentinel.core.exceptions import ConfigError

# --------------------------------------------------------------------------- #
# merge_dicts (deep merge utility)
# --------------------------------------------------------------------------- #


class TestMergeDicts:
    def test_empty_base(self) -> None:
        result = merge_dicts({}, {"a": 1})
        assert result == {"a": 1}

    def test_empty_override(self) -> None:
        result = merge_dicts({"a": 1}, {})
        assert result == {"a": 1}

    def test_flat_override(self) -> None:
        result = merge_dicts({"a": 1, "b": 2}, {"b": 3})
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self) -> None:
        base = {"llm": {"provider": "claude", "temperature": 0.2}}
        override = {"llm": {"provider": "openai"}}
        result = merge_dicts(base, override)
        assert result == {"llm": {"provider": "openai", "temperature": 0.2}}

    def test_deeply_nested(self) -> None:
        base = {"a": {"b": {"c": 1, "d": 2}}}
        override = {"a": {"b": {"c": 99}}}
        result = merge_dicts(base, override)
        assert result == {"a": {"b": {"c": 99, "d": 2}}}

    def test_override_adds_new_keys(self) -> None:
        result = merge_dicts({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_does_not_mutate_inputs(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        result = merge_dicts(base, override)
        assert result == {"a": {"x": 1, "y": 2}}
        # originals untouched
        assert base == {"a": {"x": 1}}
        assert override == {"a": {"y": 2}}

    def test_non_dict_override_replaces(self) -> None:
        """When override value is not a dict, it replaces entirely."""
        result = merge_dicts({"a": {"nested": True}}, {"a": "replaced"})
        assert result == {"a": "replaced"}

    def test_both_empty(self) -> None:
        result = merge_dicts({}, {})
        assert result == {}

    def test_list_values_are_replaced_not_merged(self) -> None:
        """Lists in override should replace base lists entirely."""
        base = {"tags": ["a", "b"]}
        override = {"tags": ["c"]}
        result = merge_dicts(base, override)
        assert result == {"tags": ["c"]}

    def test_list_values_are_deep_copied(self) -> None:
        """Returned list should be independent of the input list."""
        original_list = ["a", "b"]
        base = {"tags": original_list}
        result = merge_dicts(base, {})
        result["tags"].append("c")
        assert original_list == ["a", "b"]

    def test_nested_dict_values_are_deep_copied(self) -> None:
        """Nested dicts in result should be independent of inputs."""
        base = {"a": {"b": {"deep": True}}}
        result = merge_dicts(base, {})
        result["a"]["b"]["deep"] = False
        assert base["a"]["b"]["deep"] is True


# --------------------------------------------------------------------------- #
# load_config
# --------------------------------------------------------------------------- #


class TestLoadConfigDefaults:
    def test_no_config_files_returns_defaults(self, tmp_path: Path) -> None:
        """No yaml files -> built-in defaults."""
        cfg = load_config(tmp_path / "nonexistent")
        assert isinstance(cfg, CodeSentinelConfig)
        assert cfg.llm.provider == "claude"
        assert cfg.review.mode == "coaching"

    def test_returns_frozen_config(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent")
        with pytest.raises(ValidationError):
            cfg.version = "2.0"  # type: ignore[misc]

    def test_all_llm_defaults(self, tmp_path: Path) -> None:
        """Verify every LLM config default value."""
        cfg = load_config(tmp_path / "nonexistent")
        assert cfg.llm.provider == "claude"
        assert cfg.llm.model == "claude-sonnet-4-20250514"
        assert cfg.llm.max_tokens == 4096
        assert cfg.llm.temperature == 0.2
        assert cfg.llm.max_concurrent_requests == 3

    def test_all_review_defaults(self, tmp_path: Path) -> None:
        """Verify every review config default value."""
        cfg = load_config(tmp_path / "nonexistent")
        assert cfg.review.min_severity == "medium"
        assert cfg.review.max_findings == 15
        assert cfg.review.min_confidence == 0.7
        assert cfg.review.mode == "coaching"
        assert cfg.review.focus == ()
        assert len(cfg.review.ignore) > 0  # has default ignore globs

    def test_all_reporter_defaults(self, tmp_path: Path) -> None:
        """Verify reporter defaults — terminal enabled, others disabled."""
        cfg = load_config(tmp_path / "nonexistent")
        assert cfg.reporters.terminal.enabled is True
        assert cfg.reporters.github.enabled is False
        assert cfg.reporters.gitlab.enabled is False
        assert cfg.reporters.sarif.enabled is False


class TestLoadConfigFromRepoFile:
    def test_repo_config_overrides_defaults(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"provider": "openai", "model": "gpt-4o"}}))
        cfg = load_config(repo_cfg)
        assert cfg.llm.provider == "openai"
        assert cfg.llm.model == "gpt-4o"
        # non-overridden defaults preserved
        assert cfg.llm.max_tokens == 4096
        assert cfg.review.mode == "coaching"

    def test_partial_review_config(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"review": {"mode": "strict"}}))
        cfg = load_config(repo_cfg)
        assert cfg.review.mode == "strict"
        assert cfg.review.max_findings == 15  # default

    def test_reporter_config(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"reporters": {"github": {"enabled": True}}}))
        cfg = load_config(repo_cfg)
        assert cfg.reporters.github.enabled is True
        assert cfg.reporters.terminal.enabled is True  # default


class TestLoadConfigMergePriority:
    def test_repo_overrides_user(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # User config
        user_dir = tmp_path / "user_config"
        user_dir.mkdir()
        user_cfg = user_dir / "config.yaml"
        user_cfg.write_text(
            yaml.dump(
                {
                    "llm": {"provider": "openai", "temperature": 0.8},
                    "review": {"mode": "strict"},
                }
            )
        )
        monkeypatch.setenv("CODESENTINEL_USER_CONFIG", str(user_cfg))

        # Repo config (higher priority)
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"provider": "claude"}}))

        cfg = load_config(repo_cfg)
        # repo wins for provider
        assert cfg.llm.provider == "claude"
        # user config wins for temperature (not overridden by repo)
        assert cfg.llm.temperature == 0.8
        # user config wins for mode (not overridden by repo)
        assert cfg.review.mode == "strict"

    def test_user_overrides_defaults(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        user_dir = tmp_path / "user_config"
        user_dir.mkdir()
        user_cfg = user_dir / "config.yaml"
        user_cfg.write_text(yaml.dump({"review": {"max_findings": 25}}))
        monkeypatch.setenv("CODESENTINEL_USER_CONFIG", str(user_cfg))

        # No repo config
        cfg = load_config(tmp_path / "no_such_file.yaml")
        assert cfg.review.max_findings == 25

    def test_three_tier_merge_all_layers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All three layers contribute: defaults, user, repo."""
        user_cfg = tmp_path / "user.yaml"
        user_cfg.write_text(yaml.dump({"llm": {"temperature": 0.9}}))
        monkeypatch.setenv("CODESENTINEL_USER_CONFIG", str(user_cfg))

        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"provider": "openai"}}))

        cfg = load_config(repo_cfg)
        assert cfg.llm.provider == "openai"  # repo
        assert cfg.llm.temperature == 0.9  # user
        assert cfg.llm.max_tokens == 4096  # default


# --------------------------------------------------------------------------- #
# Env-var resolution
# --------------------------------------------------------------------------- #


class TestEnvVarResolution:
    def test_default_user_config_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without env var, user config path resolves to default."""
        monkeypatch.delenv("CODESENTINEL_USER_CONFIG", raising=False)
        path = _resolve_user_config_path()
        assert path == Path.home() / ".config" / "codesentinel" / "config.yaml"

    def test_env_var_overrides_user_config_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        custom = tmp_path / "custom.yaml"
        monkeypatch.setenv("CODESENTINEL_USER_CONFIG", str(custom))
        path = _resolve_user_config_path()
        assert path == custom

    def test_env_var_pointing_to_nonexistent_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-existent user config is silently skipped."""
        monkeypatch.setenv("CODESENTINEL_USER_CONFIG", str(tmp_path / "nope.yaml"))
        cfg = load_config(tmp_path / "also_missing.yaml")
        assert cfg.llm.provider == "claude"  # all defaults


class TestLoadConfigErrorHandling:
    def test_invalid_field_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"provider": "invalid_provider"}}))
        with pytest.raises(ConfigError, match="provider"):
            load_config(repo_cfg)

    def test_invalid_yaml_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("{{invalid yaml:::}")
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_non_dict_yaml_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("- just\n- a\n- list")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(repo_cfg)

    def test_invalid_nested_value_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(
            yaml.dump({"review": {"min_confidence": 5.0}})  # > 1.0
        )
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_negative_max_tokens_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"max_tokens": -1}}))
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_temperature_above_range_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"llm": {"temperature": 3.0}}))
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_invalid_mode_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"review": {"mode": "nonexistent_mode"}}))
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_invalid_severity_raises_config_error(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"review": {"min_severity": "ultra"}}))
        with pytest.raises(ConfigError):
            load_config(repo_cfg)

    def test_os_error_reading_config_raises_config_error(
        self, tmp_path: Path
    ) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("version: '1.0'")
        with (
            patch.object(Path, "is_file", return_value=True),
            patch.object(Path, "read_text", side_effect=OSError("Permission denied")),
            pytest.raises(ConfigError, match="Cannot read"),
        ):
            load_config(repo_cfg)


class TestLoadConfigEdgeCases:
    def test_empty_yaml_file(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("")
        cfg = load_config(repo_cfg)
        # empty file -> all defaults
        assert cfg.llm.provider == "claude"

    def test_yaml_with_only_version(self, tmp_path: Path) -> None:
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"version": "2.0"}))
        cfg = load_config(repo_cfg)
        assert cfg.version == "2.0"
        assert cfg.llm.provider == "claude"

    def test_whitespace_only_yaml_file(self, tmp_path: Path) -> None:
        """File with only whitespace is treated as empty -> defaults."""
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("   \n\n  \t  \n")
        cfg = load_config(repo_cfg)
        assert cfg.llm.provider == "claude"

    def test_yaml_null_document(self, tmp_path: Path) -> None:
        """YAML that parses to None -> defaults."""
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("---\n~\n")
        cfg = load_config(repo_cfg)
        assert cfg.llm.provider == "claude"

    def test_extra_unknown_keys_are_ignored_or_rejected(self, tmp_path: Path) -> None:
        """Unknown top-level keys are handled by Pydantic (extra=forbid or ignore)."""
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text(yaml.dump({"unknown_section": {"foo": "bar"}}))
        # Pydantic strict mode: this may raise or ignore depending on config.
        # Just verify it doesn't crash silently — it should either work or raise.
        try:
            cfg = load_config(repo_cfg)
            assert isinstance(cfg, CodeSentinelConfig)
        except ConfigError:
            pass  # Expected if Pydantic forbids extras

    def test_integer_string_yaml_raises_config_error(self, tmp_path: Path) -> None:
        """YAML that is just a scalar (int) is not a mapping."""
        repo_cfg = tmp_path / ".codesentinel.yaml"
        repo_cfg.write_text("42")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(repo_cfg)
