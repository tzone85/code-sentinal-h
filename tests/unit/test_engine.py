"""Unit tests for core/engine.py — ReviewEngine orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import Severity
from codesentinel.core.models import LLMResponse, ReviewTarget
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.patterns.schema import (
    Pattern,
    PatternMetadata,
    PatternSpec,
)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "diffs"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_pattern(name: str = "test-pattern", language: str | None = None) -> Pattern:
    return Pattern(
        metadata=PatternMetadata(name=name, category="general", language=language, severity=Severity.HIGH),
        spec=PatternSpec(description=f"Test pattern {name}"),
    )


def _make_llm_response(findings_json: str = "[]") -> LLMResponse:
    return LLMResponse(
        content=findings_json,
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )


def _finding_json(
    *,
    pattern: str = "test-pattern",
    severity: str = "high",
    confidence: float = 0.9,
    file: str = "src/main.py",
    line: int = 10,
) -> str:
    return (
        f'{{"pattern_name": "{pattern}", "severity": "{severity}", '
        f'"confidence": {confidence}, "file": "{file}", "line": {line}, '
        f'"title": "Issue found", "description": "desc", '
        f'"rationale": "reason", "remediation": "fix it"}}'
    )


def _default_config() -> dict[str, object]:
    return {
        "mode": "coaching",
        "min_severity": "medium",
        "min_confidence": 0.7,
        "max_findings": 15,
        "fail_on": "critical",
    }


def _build_engine(
    *,
    llm_response: LLMResponse | Exception | None = None,
    patterns: list[Pattern] | None = None,
    config: dict[str, object] | None = None,
    reporters: list[object] | None = None,
) -> ReviewEngine:
    """Build a ReviewEngine with mocked dependencies."""
    llm = AsyncMock()
    if isinstance(llm_response, Exception):
        llm.review.side_effect = llm_response
    else:
        llm.review.return_value = llm_response or _make_llm_response()
    llm.name = "mock-llm"

    registry = PatternRegistry(patterns or [_make_pattern()])

    return ReviewEngine(
        config=config or _default_config(),
        llm_provider=llm,
        scm_provider=None,
        pattern_registry=registry,
        reporters=reporters or [],
    )


# --------------------------------------------------------------------------- #
# Happy path: diff file → findings
# --------------------------------------------------------------------------- #


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_review_diff_file_returns_result(self) -> None:
        finding = _finding_json(file="src/com/example/domain/model/User.java")
        engine = _build_engine(
            llm_response=_make_llm_response(f"[{finding}]"),
            patterns=[_make_pattern("test-pattern", language="java")],
        )
        diff_path = str(FIXTURES_DIR / "java_clean_arch_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert result.target == target
        assert result.stats.files_reviewed > 0
        assert result.stats.llm_calls >= 1

    @pytest.mark.asyncio
    async def test_findings_populated_from_llm(self) -> None:
        finding = _finding_json()
        engine = _build_engine(
            llm_response=_make_llm_response(f"[{finding}]"),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert len(result.findings) >= 1
        assert result.findings[0].pattern_name == "test-pattern"

    @pytest.mark.asyncio
    async def test_review_stats_populated(self) -> None:
        engine = _build_engine(
            llm_response=_make_llm_response("[]"),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert result.stats.patterns_loaded >= 1
        assert result.stats.duration_ms >= 0


# --------------------------------------------------------------------------- #
# Empty / zero diff cases
# --------------------------------------------------------------------------- #


class TestEmptyDiff:
    @pytest.mark.asyncio
    async def test_empty_diff_file_returns_zero_findings(self) -> None:
        """Zero files in diff → print message, exit 0."""
        engine = _build_engine()
        # Use a target with an empty diff content
        target = ReviewTarget(type="diff", diff_path="/dev/null")
        result = await engine.review(target)

        assert len(result.findings) == 0
        assert result.stats.files_reviewed == 0
        assert result.stats.llm_calls == 0


# --------------------------------------------------------------------------- #
# No pattern matches
# --------------------------------------------------------------------------- #


class TestNoPatternMatch:
    @pytest.mark.asyncio
    async def test_no_patterns_match_returns_zero_findings(self) -> None:
        """No patterns match any files → print message, exit 0."""
        # Pattern only matches Rust files, but diff has Python
        engine = _build_engine(
            patterns=[_make_pattern("rust-only", language="rust")],
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert len(result.findings) == 0
        assert result.stats.llm_calls == 0


# --------------------------------------------------------------------------- #
# LLM failure handling
# --------------------------------------------------------------------------- #


class TestLLMFailures:
    @pytest.mark.asyncio
    async def test_malformed_json_returns_empty_findings(self) -> None:
        """LLM returns malformed JSON → PostProcessor returns []. Not an error."""
        engine = _build_engine(
            llm_response=_make_llm_response("this is not json at all"),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_llm_empty_response_treated_as_no_findings(self) -> None:
        """LLM returns empty response → no findings, not an error."""
        engine = _build_engine(
            llm_response=_make_llm_response(""),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        assert len(result.findings) == 0

    @pytest.mark.asyncio
    async def test_llm_exception_retries_then_skips_chunk(self) -> None:
        """LLM call fails → retry once. If retry fails, skip chunk, continue."""
        engine = _build_engine(
            llm_response=Exception("API timeout"),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        # Should not crash, returns result with 0 findings from failed chunks
        assert len(result.findings) == 0
        # LLM was called twice (original + retry) per chunk
        assert engine._llm_provider.review.call_count >= 2


# --------------------------------------------------------------------------- #
# Reporter dispatch
# --------------------------------------------------------------------------- #


class TestReporterDispatch:
    @pytest.mark.asyncio
    async def test_reporters_called_with_result(self) -> None:
        reporter = AsyncMock()
        reporter.is_enabled = MagicMock(return_value=True)
        engine = _build_engine(
            llm_response=_make_llm_response("[]"),
            patterns=[_make_pattern()],
            reporters=[reporter],
        )
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)

        reporter.report.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_disabled_reporter_not_called(self) -> None:
        reporter = AsyncMock()
        reporter.is_enabled = MagicMock(return_value=False)
        engine = _build_engine(
            llm_response=_make_llm_response("[]"),
            patterns=[_make_pattern()],
            reporters=[reporter],
        )
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        await engine.review(target)

        reporter.report.assert_not_called()

    @pytest.mark.asyncio
    async def test_reporter_failure_does_not_crash(self) -> None:
        """SCM/reporter API fails → log error, review still completes."""
        reporter = AsyncMock()
        reporter.is_enabled = MagicMock(return_value=True)
        reporter.report.side_effect = Exception("GitHub API error")
        engine = _build_engine(
            llm_response=_make_llm_response("[]"),
            patterns=[_make_pattern()],
            reporters=[reporter],
        )
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)

        # Should not raise
        result = await engine.review(target)
        assert result is not None


# --------------------------------------------------------------------------- #
# Exit code logic
# --------------------------------------------------------------------------- #


class TestExitCodes:
    @pytest.mark.asyncio
    async def test_exit_code_0_no_findings(self) -> None:
        engine = _build_engine(
            llm_response=_make_llm_response("[]"),
            patterns=[_make_pattern()],
        )
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)
        assert engine.compute_exit_code(result) == 0

    @pytest.mark.asyncio
    async def test_exit_code_1_findings_at_fail_on(self) -> None:
        finding = _finding_json(severity="critical")
        engine = _build_engine(
            llm_response=_make_llm_response(f"[{finding}]"),
            patterns=[_make_pattern()],
            config={**_default_config(), "fail_on": "critical"},
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)
        assert engine.compute_exit_code(result) == 1

    @pytest.mark.asyncio
    async def test_exit_code_0_findings_below_fail_on(self) -> None:
        finding = _finding_json(severity="low", confidence=0.9)
        engine = _build_engine(
            llm_response=_make_llm_response(f"[{finding}]"),
            patterns=[_make_pattern()],
            config={**_default_config(), "fail_on": "critical", "min_severity": "low"},
        )
        diff_path = str(FIXTURES_DIR / "python_django_violation.diff")
        target = ReviewTarget(type="diff", diff_path=diff_path)
        result = await engine.review(target)
        assert engine.compute_exit_code(result) == 0
