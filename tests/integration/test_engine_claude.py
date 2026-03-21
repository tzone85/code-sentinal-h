"""Integration tests for the full review pipeline with Claude API.

Requires ANTHROPIC_API_KEY environment variable. Skipped if not set.
Uses real API calls — no mocks.

NOTE: LLM output is non-deterministic. Tests assert on pipeline behavior
(completion, stats, no crashes) rather than specific finding content.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import Severity
from codesentinel.core.models import ReviewTarget
from codesentinel.llm.claude import ClaudeProvider
from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.reporters.terminal import TerminalReporter

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DIFFS_DIR = FIXTURES_DIR / "diffs"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set",
    ),
]


def _build_engine(
    *,
    mode: str = "coaching",
    min_severity: str = "medium",
    fail_on: str = "critical",
) -> ReviewEngine:
    """Build a ReviewEngine with Claude provider and builtin patterns."""
    provider = ClaudeProvider()
    loader = PatternLoader()
    patterns = loader.load_builtin()
    registry = PatternRegistry(patterns)

    config: dict[str, object] = {
        "mode": mode,
        "min_severity": min_severity,
        "min_confidence": 0.7,
        "max_findings": 15,
        "fail_on": fail_on,
    }

    return ReviewEngine(
        config=config,
        llm_provider=provider,
        scm_provider=None,
        pattern_registry=registry,
        reporters=[TerminalReporter(verbose=True)],
    )


class TestClaudeCoachingMode:
    @pytest.mark.asyncio
    async def test_pipeline_completes_with_violation_diff(self) -> None:
        engine = _build_engine(mode="coaching")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "python_django_violation.diff"),
        )

        result = await engine.review(target)

        # Pipeline should complete and report stats
        assert result.stats.files_reviewed > 0
        assert result.stats.patterns_loaded > 0
        # Findings may or may not be returned depending on LLM response

    @pytest.mark.asyncio
    async def test_clean_pr_returns_no_critical_findings(self) -> None:
        engine = _build_engine(mode="coaching")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "clean_pr_no_issues.diff"),
        )

        result = await engine.review(target)

        critical_count = sum(
            1 for f in result.findings if f.severity == Severity.CRITICAL
        )
        assert critical_count == 0, "Clean PR should have no critical findings"


class TestClaudeStrictMode:
    @pytest.mark.asyncio
    async def test_strict_mode_completes_without_error(self) -> None:
        engine = _build_engine(mode="strict")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "python_django_violation.diff"),
        )

        result = await engine.review(target)

        # Pipeline should complete without raising
        assert result.stats.files_reviewed > 0
        # Strict mode should attempt LLM calls
        assert result.stats.patterns_matched >= 0


class TestClaudeMultiFileReview:
    @pytest.mark.asyncio
    async def test_multi_file_diff_reviews_all_files(self) -> None:
        engine = _build_engine(mode="coaching")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "multi_file_service.diff"),
        )

        result = await engine.review(target)

        assert result.stats.files_reviewed >= 2, "Should review multiple files"


class TestExitCodeComputation:
    @pytest.mark.asyncio
    async def test_exit_code_reflects_fail_on_threshold(self) -> None:
        engine = _build_engine(mode="coaching", fail_on="critical")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "python_django_violation.diff"),
        )

        result = await engine.review(target)
        exit_code = engine.compute_exit_code(result)

        has_critical = any(
            f.severity >= Severity.CRITICAL for f in result.findings
        )
        if has_critical:
            assert exit_code == 1
        else:
            assert exit_code == 0


class TestFindingStructure:
    @pytest.mark.asyncio
    async def test_findings_have_valid_structure(self) -> None:
        engine = _build_engine(mode="coaching")
        target = ReviewTarget(
            type="diff",
            diff_path=str(DIFFS_DIR / "python_django_violation.diff"),
        )

        result = await engine.review(target)

        for finding in result.findings:
            assert finding.pattern_name, "Finding must have pattern name"
            assert isinstance(finding.severity, Severity)
            assert 0.0 <= finding.confidence <= 1.0
            assert finding.file, "Finding must have a file"
            assert finding.line >= 0
            assert finding.title, "Finding must have a title"
