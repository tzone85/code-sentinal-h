"""Unit tests for config/schema.py — Pydantic configuration models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codesentinel.config.schema import (
    AdditionalContext,
    AzureDevOpsReporterConfig,
    BuiltinPatternsConfig,
    CodeSentinelConfig,
    GitHubReporterConfig,
    GitLabReporterConfig,
    JsonReporterConfig,
    LLMConfig,
    PatternsConfig,
    RemotePatternSource,
    ReportersConfig,
    ReviewConfig,
    SarifReporterConfig,
    TerminalReporterConfig,
)

# --------------------------------------------------------------------------- #
# LLMConfig
# --------------------------------------------------------------------------- #


class TestLLMConfig:
    def test_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.provider == "claude"
        assert cfg.model == "claude-sonnet-4-20250514"
        assert cfg.max_tokens == 4096
        assert cfg.temperature == 0.2
        assert cfg.max_concurrent_requests == 3

    def test_custom_values(self) -> None:
        cfg = LLMConfig(
            provider="openai",
            model="gpt-4o",
            max_tokens=8192,
            temperature=0.5,
            max_concurrent_requests=5,
        )
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.max_tokens == 8192

    def test_provider_dicts(self) -> None:
        cfg = LLMConfig(
            claude={"api_key_env": "MY_KEY"},
            openai={"api_key_env": "OAI_KEY", "base_url": "https://custom.api"},
            ollama={"base_url": "http://localhost:11434", "model": "codellama"},
        )
        assert cfg.claude == {"api_key_env": "MY_KEY"}
        assert cfg.openai["base_url"] == "https://custom.api"
        assert cfg.ollama["model"] == "codellama"

    def test_frozen(self) -> None:
        cfg = LLMConfig()
        with pytest.raises(ValidationError):
            cfg.provider = "openai"  # type: ignore[misc]

    def test_invalid_temperature_too_high(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(temperature=2.5)

    def test_invalid_temperature_negative(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(temperature=-0.1)

    def test_invalid_max_tokens_zero(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(max_tokens=0)

    def test_invalid_provider(self) -> None:
        with pytest.raises(ValidationError):
            LLMConfig(provider="invalid_provider")


# --------------------------------------------------------------------------- #
# PatternsConfig
# --------------------------------------------------------------------------- #


class TestBuiltinPatternsConfig:
    def test_defaults(self) -> None:
        cfg = BuiltinPatternsConfig()
        assert cfg.enabled is True
        assert cfg.include == ()
        assert cfg.exclude == ()

    def test_custom_include_exclude(self) -> None:
        cfg = BuiltinPatternsConfig(
            include=("python/*", "general/*"),
            exclude=("java/*",),
        )
        assert cfg.include == ("python/*", "general/*")
        assert cfg.exclude == ("java/*",)

    def test_frozen(self) -> None:
        cfg = BuiltinPatternsConfig()
        with pytest.raises(ValidationError):
            cfg.enabled = False  # type: ignore[misc]


class TestRemotePatternSource:
    def test_required_fields(self) -> None:
        src = RemotePatternSource(repo="org/patterns", path="patterns/")
        assert src.repo == "org/patterns"
        assert src.path == "patterns/"
        assert src.ref == "main"
        assert src.cache_ttl == 3600

    def test_custom_values(self) -> None:
        src = RemotePatternSource(
            repo="org/custom",
            path="custom/",
            ref="v2",
            cache_ttl=7200,
        )
        assert src.ref == "v2"
        assert src.cache_ttl == 7200


class TestPatternsConfig:
    def test_defaults(self) -> None:
        cfg = PatternsConfig()
        assert cfg.builtin.enabled is True
        assert cfg.remote == ()
        assert cfg.local == ()

    def test_with_remote_sources(self) -> None:
        cfg = PatternsConfig(
            remote=(RemotePatternSource(repo="org/patterns", path="p/"),),
        )
        assert len(cfg.remote) == 1
        assert cfg.remote[0].repo == "org/patterns"

    def test_with_local_paths(self) -> None:
        cfg = PatternsConfig(local=(".codesentinel/patterns/",))
        assert cfg.local == (".codesentinel/patterns/",)


# --------------------------------------------------------------------------- #
# ReviewConfig
# --------------------------------------------------------------------------- #


class TestAdditionalContext:
    def test_creation(self) -> None:
        ctx = AdditionalContext(path="docs/arch.md", description="Architecture doc")
        assert ctx.path == "docs/arch.md"
        assert ctx.description == "Architecture doc"


class TestReviewConfig:
    def test_defaults(self) -> None:
        cfg = ReviewConfig()
        assert cfg.min_severity == "medium"
        assert cfg.max_findings == 15
        assert cfg.min_confidence == 0.7
        assert cfg.mode == "coaching"
        assert isinstance(cfg.focus, tuple)
        assert isinstance(cfg.ignore, tuple)
        assert len(cfg.ignore) > 0  # default ignore globs should be set

    def test_custom_values(self) -> None:
        cfg = ReviewConfig(
            min_severity="high",
            max_findings=5,
            min_confidence=0.9,
            mode="strict",
            focus=("security", "performance"),
        )
        assert cfg.min_severity == "high"
        assert cfg.mode == "strict"
        assert cfg.focus == ("security", "performance")

    def test_default_ignore_globs(self) -> None:
        cfg = ReviewConfig()
        ignore = cfg.ignore
        # Standard globs that should be ignored by default
        assert "*.lock" in ignore
        assert "*.min.js" in ignore

    def test_additional_context(self) -> None:
        cfg = ReviewConfig(
            additional_context=(AdditionalContext(path="docs/arch.md", description="Arch"),),
        )
        assert len(cfg.additional_context) == 1

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValidationError):
            ReviewConfig(mode="invalid_mode")

    def test_invalid_min_severity(self) -> None:
        with pytest.raises(ValidationError):
            ReviewConfig(min_severity="extreme")

    def test_invalid_confidence_too_high(self) -> None:
        with pytest.raises(ValidationError):
            ReviewConfig(min_confidence=1.5)

    def test_invalid_confidence_negative(self) -> None:
        with pytest.raises(ValidationError):
            ReviewConfig(min_confidence=-0.1)

    def test_frozen(self) -> None:
        cfg = ReviewConfig()
        with pytest.raises(ValidationError):
            cfg.mode = "strict"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# ReportersConfig
# --------------------------------------------------------------------------- #


class TestTerminalReporterConfig:
    def test_defaults(self) -> None:
        cfg = TerminalReporterConfig()
        assert cfg.enabled is True
        assert cfg.color is True
        assert cfg.verbose is False


class TestGitHubReporterConfig:
    def test_defaults(self) -> None:
        cfg = GitHubReporterConfig()
        assert cfg.enabled is False
        assert cfg.post_review is True
        assert cfg.comment_style == "both"

    def test_custom(self) -> None:
        cfg = GitHubReporterConfig(
            enabled=True,
            request_changes_on="high",
            comment_style="inline",
        )
        assert cfg.enabled is True
        assert cfg.request_changes_on == "high"
        assert cfg.comment_style == "inline"


class TestGitLabReporterConfig:
    def test_defaults(self) -> None:
        cfg = GitLabReporterConfig()
        assert cfg.enabled is False


class TestAzureDevOpsReporterConfig:
    def test_defaults(self) -> None:
        cfg = AzureDevOpsReporterConfig()
        assert cfg.enabled is False


class TestJsonReporterConfig:
    def test_defaults(self) -> None:
        cfg = JsonReporterConfig()
        assert cfg.enabled is False
        assert cfg.output_path == "codesentinel-report.json"


class TestSarifReporterConfig:
    def test_defaults(self) -> None:
        cfg = SarifReporterConfig()
        assert cfg.enabled is False
        assert cfg.output_path == "codesentinel-report.sarif"


class TestReportersConfig:
    def test_defaults(self) -> None:
        cfg = ReportersConfig()
        assert cfg.terminal.enabled is True
        assert cfg.github.enabled is False
        assert cfg.gitlab.enabled is False
        assert cfg.azure_devops.enabled is False
        assert cfg.json_reporter.enabled is False
        assert cfg.sarif.enabled is False


# --------------------------------------------------------------------------- #
# CodeSentinelConfig (top-level)
# --------------------------------------------------------------------------- #


class TestCodeSentinelConfig:
    def test_defaults(self) -> None:
        cfg = CodeSentinelConfig()
        assert cfg.version == "1.0"
        assert isinstance(cfg.llm, LLMConfig)
        assert isinstance(cfg.patterns, PatternsConfig)
        assert isinstance(cfg.review, ReviewConfig)
        assert isinstance(cfg.reporters, ReportersConfig)

    def test_custom_nested(self) -> None:
        cfg = CodeSentinelConfig(
            llm=LLMConfig(provider="openai", model="gpt-4o"),
            review=ReviewConfig(mode="strict", max_findings=5),
        )
        assert cfg.llm.provider == "openai"
        assert cfg.review.mode == "strict"

    def test_frozen(self) -> None:
        cfg = CodeSentinelConfig()
        with pytest.raises(ValidationError):
            cfg.version = "2.0"  # type: ignore[misc]

    def test_serialization_roundtrip(self) -> None:
        cfg = CodeSentinelConfig()
        data = cfg.model_dump()
        restored = CodeSentinelConfig(**data)
        assert restored == cfg

    def test_from_partial_dict(self) -> None:
        """Config should be constructable from a partial dict (rest uses defaults)."""
        data = {"llm": {"provider": "openai", "model": "gpt-4o"}}
        cfg = CodeSentinelConfig(**data)
        assert cfg.llm.provider == "openai"
        assert cfg.llm.max_tokens == 4096  # default preserved
        assert cfg.review.mode == "coaching"  # default preserved
