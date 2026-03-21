"""Unit tests for the ReviewEngine orchestrator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from codesentinel.core.engine import (
    EXIT_CLEAN,
    EXIT_FINDINGS,
    EngineConfig,
    ReviewEngine,
    _count_by_severity,
    _dict_to_finding,
)
from codesentinel.core.enums import Severity
from codesentinel.core.exceptions import LLMError, SCMError
from codesentinel.core.models import (
    Finding,
    LLMResponse,
    ReviewTarget,
)
from codesentinel.llm.base import LLMProvider
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.patterns.schema import (
    AppliesTo,
    Pattern,
    PatternMetadata,
    PatternSpec,
)
from codesentinel.reporters.base import Reporter
from codesentinel.scm.base import SCMProvider

# --------------------------------------------------------------------------- #
# Fixtures — sample diff that includes intentional bad patterns for detection
# --------------------------------------------------------------------------- #

# NOTE: This diff is TEST DATA representing code a reviewer would analyze.
# The SQL injection and command injection in the diff are intentional examples
# of vulnerabilities that CodeSentinel is designed to detect.
_SAMPLE_DIFF = (
    "diff --git a/src/service/user.py b/src/service/user.py\n"
    "new file mode 100644\n"
    "--- /dev/null\n"
    "+++ b/src/service/user.py\n"
    "@@ -0,0 +1,10 @@\n"
    "+class UserService:\n"
    "+    def get_user(self, user_id):\n"
    '+        query = f"SELECT * FROM users WHERE id = {user_id}"\n'
    "+        return self.db.execute(query)\n"
)

_SAMPLE_FINDING_JSON = json.dumps([
    {
        "pattern_name": "sql-injection",
        "severity": "critical",
        "confidence": 0.95,
        "file": "src/service/user.py",
        "line": 5,
        "title": "SQL injection vulnerability",
        "description": "User input interpolated into SQL query",
        "rationale": "Allows attackers to execute arbitrary SQL",
        "remediation": "Use parameterized queries",
        "code_snippet": 'f"SELECT * FROM users WHERE id = {user_id}"',
    }
])


def _make_pattern(
    name: str = "sql-injection",
    language: str | None = "python",
    severity: Severity = Severity.CRITICAL,
    include: tuple[str, ...] = ("**/*.py",),
) -> Pattern:
    return Pattern(
        metadata=PatternMetadata(
            name=name,
            category="security",
            language=language,
            severity=severity,
        ),
        spec=PatternSpec(
            description=f"Detect {name} violations",
            applies_to=AppliesTo(include=include),
        ),
    )


def _make_llm_response(content: str = _SAMPLE_FINDING_JSON) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )


def _mock_llm_provider(response: LLMResponse | None = None) -> LLMProvider:
    """Create a mock LLMProvider that returns the given response."""
    provider = MagicMock(spec=LLMProvider)
    provider.review = AsyncMock(return_value=response or _make_llm_response())
    provider.estimate_tokens = MagicMock(side_effect=lambda text: len(text) // 4)
    provider.max_context_tokens = MagicMock(return_value=200_000)
    provider.name = "mock"
    return provider


def _mock_scm_provider(diff: str = _SAMPLE_DIFF) -> SCMProvider:
    """Create a mock SCMProvider returning the given diff."""
    scm = MagicMock(spec=SCMProvider)
    scm.get_pr_diff = AsyncMock(return_value=diff)
    scm.get_local_diff = AsyncMock(return_value=diff)
    return scm


def _mock_reporter(enabled: bool = True) -> Reporter:
    """Create a mock Reporter."""
    reporter = MagicMock(spec=Reporter)
    reporter.is_enabled = MagicMock(return_value=enabled)
    reporter.report = AsyncMock()
    return reporter


def _make_engine(
    *,
    llm_response: LLMResponse | None = None,
    diff: str = _SAMPLE_DIFF,
    patterns: list[Pattern] | None = None,
    reporters: list[Reporter] | None = None,
    config: EngineConfig | None = None,
    scm: SCMProvider | None = None,
) -> ReviewEngine:
    """Build a ReviewEngine with sensible test defaults."""
    registry = PatternRegistry(patterns or [_make_pattern()])
    return ReviewEngine(
        config=config or EngineConfig(),
        llm_provider=_mock_llm_provider(llm_response),
        scm_provider=scm or _mock_scm_provider(diff),
        pattern_registry=registry,
        reporters=reporters,
    )


def _diff_target(path: str | None = None) -> ReviewTarget:
    return ReviewTarget(type="diff", diff_path=path)


def _pr_target(url: str = "https://github.com/o/r/pull/1") -> ReviewTarget:
    return ReviewTarget(type="pr", pr_url=url)


def _branch_target(branch: str = "feature", base: str = "main") -> ReviewTarget:
    return ReviewTarget(type="branch", branch=branch, base_branch=base)


# --------------------------------------------------------------------------- #
# Tests: full pipeline happy path
# --------------------------------------------------------------------------- #


class TestReviewPipelineHappyPath:
    """Test the full review pipeline with a working setup."""

    async def test_review_via_pr_returns_findings(self) -> None:
        engine = _make_engine()
        result = await engine.review(_pr_target())

        assert len(result.findings) > 0
        assert result.stats.files_reviewed > 0
        assert result.stats.llm_calls > 0

    async def test_review_via_branch_returns_findings(self) -> None:
        engine = _make_engine()
        result = await engine.review(_branch_target())

        assert len(result.findings) > 0

    async def test_review_via_diff_file(self, tmp_path: object) -> None:
        import pathlib
        diff_file = pathlib.Path(str(tmp_path)) / "test.diff"
        diff_file.write_text(_SAMPLE_DIFF)

        engine = _make_engine()
        result = await engine.review(_diff_target(str(diff_file)))

        assert len(result.findings) > 0
        assert result.stats.files_reviewed == 1

    async def test_stats_include_token_counts(self) -> None:
        engine = _make_engine()
        result = await engine.review(_pr_target())

        assert result.stats.input_tokens > 0
        assert result.stats.output_tokens > 0

    async def test_stats_include_duration(self) -> None:
        engine = _make_engine()
        result = await engine.review(_pr_target())

        assert result.stats.duration_ms >= 0

    async def test_findings_have_correct_severity(self) -> None:
        engine = _make_engine()
        result = await engine.review(_pr_target())

        for finding in result.findings:
            assert isinstance(finding.severity, Severity)


# --------------------------------------------------------------------------- #
# Tests: zero files / no matches (Section 20 edge cases)
# --------------------------------------------------------------------------- #


class TestEdgeCases:
    """Test graceful handling of edge cases per Section 20."""

    async def test_empty_diff_returns_zero_findings(self) -> None:
        engine = _make_engine(diff="")
        result = await engine.review(_pr_target())

        assert result.findings == ()
        assert result.stats.files_reviewed == 0

    async def test_no_pattern_matches_returns_zero_findings(self) -> None:
        # Pattern only matches .java files, but diff has .py
        java_pattern = _make_pattern(language="java", include=("**/*.java",))
        engine = _make_engine(patterns=[java_pattern])
        result = await engine.review(_pr_target())

        assert result.findings == ()
        assert result.stats.patterns_loaded == 1
        assert result.stats.patterns_matched == 0

    async def test_llm_returns_empty_response(self) -> None:
        empty_response = _make_llm_response(content="")
        engine = _make_engine(llm_response=empty_response)
        result = await engine.review(_pr_target())

        assert result.findings == ()

    async def test_llm_returns_no_findings_text(self) -> None:
        no_findings_response = _make_llm_response(content="Looks good! No issues found.")
        engine = _make_engine(llm_response=no_findings_response)
        result = await engine.review(_pr_target())

        assert result.findings == ()

    async def test_llm_returns_empty_json_array(self) -> None:
        empty_array = _make_llm_response(content="[]")
        engine = _make_engine(llm_response=empty_array)
        result = await engine.review(_pr_target())

        assert result.findings == ()

    async def test_all_findings_filtered_returns_zero(self) -> None:
        # Set min_severity to CRITICAL, but response has only INFO findings
        info_response = _make_llm_response(content=json.dumps([{
            "pattern_name": "minor-style",
            "severity": "info",
            "confidence": 0.9,
            "file": "src/service/user.py",
            "line": 1,
            "title": "Style issue",
            "description": "Minor style issue",
            "rationale": "Consistency",
            "remediation": "Fix style",
        }]))
        config = EngineConfig(min_severity=Severity.CRITICAL)
        engine = _make_engine(llm_response=info_response, config=config)
        result = await engine.review(_pr_target())

        assert result.findings == ()


# --------------------------------------------------------------------------- #
# Tests: LLM error handling (Section 20)
# --------------------------------------------------------------------------- #


class TestLLMErrorHandling:
    """Test retry logic and graceful degradation on LLM failures."""

    async def test_llm_failure_retries_once_then_skips(self) -> None:
        llm = _mock_llm_provider()
        llm.review = AsyncMock(side_effect=LLMError("rate limited"))

        engine = ReviewEngine(
            config=EngineConfig(),
            llm_provider=llm,
            scm_provider=_mock_scm_provider(),
            pattern_registry=PatternRegistry([_make_pattern()]),
        )
        result = await engine.review(_pr_target())

        # Both attempts fail → 0 findings, but no crash
        assert result.findings == ()
        assert llm.review.call_count == 2  # initial + retry

    async def test_llm_malformed_json_returns_empty(self) -> None:
        bad_json = _make_llm_response(content="this is not json {{{")
        engine = _make_engine(llm_response=bad_json)
        result = await engine.review(_pr_target())

        assert result.findings == ()

    async def test_llm_succeeds_on_retry(self) -> None:
        llm = _mock_llm_provider()
        llm.review = AsyncMock(
            side_effect=[LLMError("timeout"), _make_llm_response()]
        )

        engine = ReviewEngine(
            config=EngineConfig(),
            llm_provider=llm,
            scm_provider=_mock_scm_provider(),
            pattern_registry=PatternRegistry([_make_pattern()]),
        )
        result = await engine.review(_pr_target())

        assert len(result.findings) > 0
        assert llm.review.call_count == 2


# --------------------------------------------------------------------------- #
# Tests: reporter dispatch
# --------------------------------------------------------------------------- #


class TestReporterDispatch:
    """Test that reporters are called correctly."""

    async def test_enabled_reporter_receives_result(self) -> None:
        reporter = _mock_reporter(enabled=True)
        engine = _make_engine(reporters=[reporter])
        result = await engine.review(_pr_target())

        reporter.report.assert_awaited_once_with(result)

    async def test_disabled_reporter_is_skipped(self) -> None:
        reporter = _mock_reporter(enabled=False)
        engine = _make_engine(reporters=[reporter])
        await engine.review(_pr_target())

        reporter.report.assert_not_awaited()

    async def test_reporter_failure_does_not_crash(self) -> None:
        reporter = _mock_reporter(enabled=True)
        reporter.report = AsyncMock(side_effect=RuntimeError("post failed"))
        engine = _make_engine(reporters=[reporter])

        # Should not raise
        result = await engine.review(_pr_target())
        assert result is not None

    async def test_multiple_reporters_all_called(self) -> None:
        r1 = _mock_reporter(enabled=True)
        r2 = _mock_reporter(enabled=True)
        engine = _make_engine(reporters=[r1, r2])
        await engine.review(_pr_target())

        r1.report.assert_awaited_once()
        r2.report.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Tests: exit code computation
# --------------------------------------------------------------------------- #


class TestExitCodes:
    """Test exit code determination."""

    async def test_no_findings_returns_exit_clean(self) -> None:
        engine = _make_engine(diff="")
        result = await engine.review(_pr_target())
        assert engine.compute_exit_code(result) == EXIT_CLEAN

    async def test_critical_finding_returns_exit_findings(self) -> None:
        engine = _make_engine(config=EngineConfig(fail_on=Severity.CRITICAL))
        result = await engine.review(_pr_target())

        # Our sample response has a CRITICAL finding
        assert engine.compute_exit_code(result) == EXIT_FINDINGS

    async def test_findings_below_fail_on_returns_clean(self) -> None:
        # Only INFO finding, fail_on=CRITICAL
        info_response = _make_llm_response(content=json.dumps([{
            "pattern_name": "style-check",
            "severity": "info",
            "confidence": 0.9,
            "file": "src/service/user.py",
            "line": 1,
            "title": "Style",
            "description": "Minor",
            "rationale": "Consistency",
            "remediation": "Fix",
        }]))
        config = EngineConfig(
            fail_on=Severity.CRITICAL,
            min_severity=Severity.INFO,
        )
        engine = _make_engine(llm_response=info_response, config=config)
        result = await engine.review(_pr_target())

        assert engine.compute_exit_code(result) == EXIT_CLEAN


# --------------------------------------------------------------------------- #
# Tests: SCM error handling
# --------------------------------------------------------------------------- #


class TestSCMErrors:
    """Test SCM-related error scenarios."""

    async def test_pr_review_without_scm_raises(self) -> None:
        engine = ReviewEngine(
            config=EngineConfig(),
            llm_provider=_mock_llm_provider(),
            scm_provider=None,
            pattern_registry=PatternRegistry([_make_pattern()]),
        )
        with pytest.raises(SCMError, match="SCM provider required"):
            await engine.review(_pr_target())

    async def test_branch_review_without_scm_raises(self) -> None:
        engine = ReviewEngine(
            config=EngineConfig(),
            llm_provider=_mock_llm_provider(),
            scm_provider=None,
            pattern_registry=PatternRegistry([_make_pattern()]),
        )
        with pytest.raises(SCMError, match="SCM provider required"):
            await engine.review(_branch_target())

    async def test_diff_file_not_found_raises(self) -> None:
        engine = _make_engine()
        with pytest.raises(SCMError, match="not found"):
            await engine.review(_diff_target("/nonexistent/file.diff"))

    async def test_unsupported_target_type_raises(self) -> None:
        engine = _make_engine()
        target = ReviewTarget(type="unknown")
        with pytest.raises(SCMError, match="Unsupported"):
            await engine.review(target)


# --------------------------------------------------------------------------- #
# Tests: pure helper functions
# --------------------------------------------------------------------------- #


class TestHelpers:
    """Test module-level helper functions."""

    def test_count_by_severity(self) -> None:
        findings = [
            Finding(
                pattern_name="a", severity=Severity.CRITICAL,
                confidence=0.9, file="f.py", line=1,
                title="t", description="d", rationale="r", remediation="x",
            ),
            Finding(
                pattern_name="b", severity=Severity.CRITICAL,
                confidence=0.9, file="f.py", line=2,
                title="t", description="d", rationale="r", remediation="x",
            ),
            Finding(
                pattern_name="c", severity=Severity.LOW,
                confidence=0.9, file="f.py", line=3,
                title="t", description="d", rationale="r", remediation="x",
            ),
        ]
        counts = _count_by_severity(findings)
        assert counts[Severity.CRITICAL] == 2
        assert counts[Severity.LOW] == 1

    def test_dict_to_finding_valid(self) -> None:
        raw = {
            "pattern_name": "sql-injection",
            "severity": "critical",
            "confidence": 0.95,
            "file": "f.py",
            "line": 5,
            "title": "SQL injection",
            "description": "Bad query",
            "rationale": "Security",
            "remediation": "Use params",
        }
        finding = _dict_to_finding(raw)
        assert finding is not None
        assert finding.severity == Severity.CRITICAL
        assert finding.confidence == 0.95

    def test_dict_to_finding_with_unknown_severity(self) -> None:
        raw = {"severity": "superbad", "file": "f.py", "line": 1}
        finding = _dict_to_finding(raw)
        assert finding is not None
        assert finding.severity == Severity.MEDIUM  # default fallback

    def test_dict_to_finding_missing_fields_uses_defaults(self) -> None:
        raw: dict[str, object] = {}
        finding = _dict_to_finding(raw)
        assert finding is not None
        assert finding.pattern_name == "unknown"
        assert finding.confidence == 0.5

    def test_count_by_severity_empty(self) -> None:
        assert _count_by_severity([]) == {}


# --------------------------------------------------------------------------- #
# Tests: staged review target
# --------------------------------------------------------------------------- #


class TestStagedReview:
    """Test the staged diff review path."""

    async def test_staged_review_calls_scm(self) -> None:
        scm = _mock_scm_provider()
        engine = _make_engine(scm=scm)
        target = ReviewTarget(type="staged", repo_path="/repo")
        await engine.review(target)

        scm.get_local_diff.assert_awaited_once_with("/repo", "HEAD", None)
