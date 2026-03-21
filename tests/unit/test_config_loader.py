"""Unit tests for config/loader.py — configuration loading and merging."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from codesentinel.config.loader import load_config, merge_dicts
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
