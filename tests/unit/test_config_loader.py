"""Unit tests for configuration loading and merging.

Config module (config/loader.py) is not yet implemented — these tests
validate config-related behavior already present in the codebase:
engine config handling, defaults, and env var resolution patterns.

When STORY-CS-013 adds config/loader.py, these tests should be extended
to cover the full config loading pipeline.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import Severity
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.patterns.schema import Pattern, PatternMetadata, PatternSpec

CONFIGS_DIR = Path(__file__).parent.parent / "fixtures" / "configs"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_pattern() -> Pattern:
    return Pattern(
        metadata=PatternMetadata(name="test-pat", category="general", severity=Severity.HIGH),
        spec=PatternSpec(description="test"),
    )


# --------------------------------------------------------------------------- #
# Config fixture files — structure validation
# --------------------------------------------------------------------------- #


class TestConfigFixtures:
    def test_minimal_config_is_valid_yaml(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "minimal_config.yaml").read_text())
        assert isinstance(data, dict)
        assert "llm" in data

    def test_full_config_has_all_sections(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "full_config.yaml").read_text())
        assert "llm" in data
        assert "patterns" in data
        assert "review" in data
        assert "reporters" in data

    def test_full_config_llm_section(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "full_config.yaml").read_text())
        llm = data["llm"]
        assert llm["provider"] == "claude"
        assert llm["max_tokens"] == 4096
        assert llm["temperature"] == 0.2

    def test_full_config_review_defaults(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "full_config.yaml").read_text())
        review = data["review"]
        assert review["min_severity"] == "medium"
        assert review["max_findings"] == 15
        assert review["min_confidence"] == 0.7
        assert review["mode"] == "coaching"

    def test_full_config_patterns_section(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "full_config.yaml").read_text())
        patterns = data["patterns"]
        assert patterns["builtin"]["enabled"] is True
        assert len(patterns["remote"]) == 1
        assert patterns["remote"][0]["repo"] == "org/shared-patterns"

    def test_invalid_config_is_parseable_yaml(self) -> None:
        data = yaml.safe_load((CONFIGS_DIR / "invalid_config.yaml").read_text())
        assert isinstance(data, dict)
        assert data["llm"]["max_tokens"] == -1


# --------------------------------------------------------------------------- #
# Engine config handling — default values
# --------------------------------------------------------------------------- #


class TestEngineConfigDefaults:
    """Test that the engine handles missing config keys with correct defaults."""

    def test_empty_config_uses_defaults(self) -> None:
        """Engine must not crash on empty config dict."""
        from unittest.mock import AsyncMock

        engine = ReviewEngine(
            config={},
            llm_provider=AsyncMock(),
            scm_provider=None,
            pattern_registry=PatternRegistry([_make_pattern()]),
            reporters=[],
        )
        # PostProcessor is initialized with defaults
        assert engine._post_processor.min_severity == Severity.MEDIUM
        assert engine._post_processor.min_confidence == 0.7
        assert engine._post_processor.max_findings == 15

    def test_partial_config_fills_defaults(self) -> None:
        from unittest.mock import AsyncMock

        engine = ReviewEngine(
            config={"min_severity": "high"},
            llm_provider=AsyncMock(),
            scm_provider=None,
            pattern_registry=PatternRegistry([_make_pattern()]),
            reporters=[],
        )
        assert engine._post_processor.min_severity == Severity.HIGH
        assert engine._post_processor.min_confidence == 0.7  # default

    def test_all_config_values_respected(self) -> None:
        from unittest.mock import AsyncMock

        engine = ReviewEngine(
            config={
                "min_severity": "low",
                "min_confidence": 0.5,
                "max_findings": 25,
                "mode": "strict",
                "fail_on": "high",
            },
            llm_provider=AsyncMock(),
            scm_provider=None,
            pattern_registry=PatternRegistry([_make_pattern()]),
            reporters=[],
        )
        assert engine._post_processor.min_severity == Severity.LOW
        assert engine._post_processor.min_confidence == 0.5
        assert engine._post_processor.max_findings == 25


# --------------------------------------------------------------------------- #
# Config merging patterns — simulated
# --------------------------------------------------------------------------- #


class TestConfigMerging:
    """Test dictionary merging behavior used by config loading."""

    def test_later_values_override_earlier(self) -> None:
        """Simulates: defaults < user config < repo config priority."""
        defaults = {"min_severity": "medium", "max_findings": 15, "mode": "coaching"}
        user = {"min_severity": "low"}
        repo = {"min_severity": "high", "max_findings": 10}

        merged = {**defaults, **user, **repo}
        assert merged["min_severity"] == "high"  # repo wins
        assert merged["max_findings"] == 10  # repo wins
        assert merged["mode"] == "coaching"  # default preserved

    def test_nested_merge_pattern(self) -> None:
        """Test deep merge pattern for nested config sections."""
        defaults = {
            "llm": {"provider": "claude", "model": "sonnet", "temperature": 0.2},
            "review": {"min_severity": "medium"},
        }
        override = {
            "llm": {"model": "opus"},
        }
        merged = {
            "llm": {**defaults["llm"], **override.get("llm", {})},
            "review": {**defaults["review"], **override.get("review", {})},
        }
        assert merged["llm"]["provider"] == "claude"  # preserved
        assert merged["llm"]["model"] == "opus"  # overridden
        assert merged["review"]["min_severity"] == "medium"  # preserved

    def test_empty_override_keeps_defaults(self) -> None:
        defaults = {"min_severity": "medium", "max_findings": 15}
        override: dict[str, object] = {}
        merged = {**defaults, **override}
        assert merged == defaults
