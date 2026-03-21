"""Unit tests for config/defaults.py — default configuration values."""

from __future__ import annotations

from codesentinel.config.defaults import default_config
from codesentinel.config.schema import CodeSentinelConfig


class TestDefaultConfig:
    def test_returns_code_sentinel_config(self) -> None:
        cfg = default_config()
        assert isinstance(cfg, CodeSentinelConfig)

    def test_llm_defaults(self) -> None:
        cfg = default_config()
        assert cfg.llm.provider == "claude"
        assert cfg.llm.model == "claude-sonnet-4-20250514"
        assert cfg.llm.max_tokens == 4096
        assert cfg.llm.temperature == 0.2
        assert cfg.llm.max_concurrent_requests == 3

    def test_review_defaults(self) -> None:
        cfg = default_config()
        assert cfg.review.min_severity == "medium"
        assert cfg.review.max_findings == 15
        assert cfg.review.min_confidence == 0.7
        assert cfg.review.mode == "coaching"

    def test_review_default_ignore_globs(self) -> None:
        cfg = default_config()
        globs = cfg.review.ignore
        assert "*.lock" in globs
        assert "*.min.js" in globs

    def test_patterns_defaults(self) -> None:
        cfg = default_config()
        assert cfg.patterns.builtin.enabled is True
        assert cfg.patterns.remote == ()
        assert cfg.patterns.local == ()

    def test_reporters_defaults(self) -> None:
        cfg = default_config()
        assert cfg.reporters.terminal.enabled is True
        assert cfg.reporters.github.enabled is False
        assert cfg.reporters.json_reporter.enabled is False
        assert cfg.reporters.sarif.enabled is False

    def test_version(self) -> None:
        cfg = default_config()
        assert cfg.version == "1.0"

    def test_immutable(self) -> None:
        """Calling default_config twice returns equal but independent objects."""
        a = default_config()
        b = default_config()
        assert a == b
