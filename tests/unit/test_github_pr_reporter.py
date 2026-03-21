"""Unit tests for reporters/github_pr.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codesentinel.config.schema import GitHubReporterConfig
from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.github_pr import GitHubPRReporter

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_finding(
    severity: Severity = Severity.HIGH,
    title: str = "Test issue",
    file: str = "src/main.py",
    line: int = 42,
    pattern_name: str = "test-pattern",
) -> Finding:
    return Finding(
        pattern_name=pattern_name,
        severity=severity,
        confidence=0.9,
        file=file,
        line=line,
        title=title,
        description="A test finding description.",
        rationale="This matters because reasons.",
        remediation="Fix by doing the thing.",
    )


def _make_result(
    findings: tuple[Finding, ...] = (),
    *,
    pr_url: str = "https://github.com/owner/repo/pull/1",
) -> ReviewResult:
    severity_counts: dict[Severity, int] = {}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
    return ReviewResult(
        findings=findings,
        stats=ReviewStats(
            files_reviewed=3,
            patterns_loaded=5,
            patterns_matched=2,
            findings_total=len(findings),
            findings_by_severity=severity_counts,
        ),
        target=ReviewTarget(type="pr", pr_url=pr_url),
    )


def _make_scm() -> MagicMock:
    scm = MagicMock()
    scm.post_review_comment = AsyncMock()
    scm.post_review_summary = AsyncMock()
    return scm


def _make_reporter(
    scm: MagicMock | None = None,
    *,
    enabled: bool = True,
    comment_style: str = "both",
    request_changes_on: str = "critical",
) -> GitHubPRReporter:
    config = GitHubReporterConfig(
        enabled=enabled,
        post_review=True,
        comment_style=comment_style,
        request_changes_on=request_changes_on,
    )
    return GitHubPRReporter(
        config=config,
        scm=scm or _make_scm(),
    )


# ------------------------------------------------------------------ #
# is_enabled
# ------------------------------------------------------------------ #


class TestIsEnabled:
    def test_enabled_when_config_says_true(self) -> None:
        reporter = _make_reporter(enabled=True)
        assert reporter.is_enabled() is True

    def test_disabled_when_config_says_false(self) -> None:
        reporter = _make_reporter(enabled=False)
        assert reporter.is_enabled() is False


# ------------------------------------------------------------------ #
# No findings
# ------------------------------------------------------------------ #


class TestNoFindings:
    @pytest.mark.asyncio
    async def test_no_findings_posts_clean_summary(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary")
        result = _make_result()

        await reporter.report(result)

        scm.post_review_summary.assert_called_once()
        call_kwargs = scm.post_review_summary.call_args
        body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body") or call_kwargs[0][1]
        assert "no findings" in body.lower() or "No findings" in body or "0" in body

    @pytest.mark.asyncio
    async def test_no_findings_no_inline_comments(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="both")
        result = _make_result()

        await reporter.report(result)

        scm.post_review_comment.assert_not_called()


# ------------------------------------------------------------------ #
# Inline comment style
# ------------------------------------------------------------------ #


class TestInlineComments:
    @pytest.mark.asyncio
    async def test_inline_posts_comment_per_finding(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        findings = (
            _make_finding(severity=Severity.HIGH, file="src/a.py", line=10),
            _make_finding(severity=Severity.LOW, file="src/b.py", line=20),
        )
        result = _make_result(findings)

        await reporter.report(result)

        assert scm.post_review_comment.call_count == 2

    @pytest.mark.asyncio
    async def test_inline_comment_includes_severity_badge(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(severity=Severity.CRITICAL),))

        await reporter.report(result)

        call_args = scm.post_review_comment.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body") or call_args[0][2]
        assert "CRITICAL" in body

    @pytest.mark.asyncio
    async def test_inline_comment_includes_pattern_name(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(pattern_name="sql-injection"),))

        await reporter.report(result)

        call_args = scm.post_review_comment.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body") or call_args[0][2]
        assert "sql-injection" in body

    @pytest.mark.asyncio
    async def test_inline_comment_includes_remediation(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        call_args = scm.post_review_comment.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body") or call_args[0][2]
        assert "Fix by doing the thing" in body

    @pytest.mark.asyncio
    async def test_inline_comment_includes_rationale(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        call_args = scm.post_review_comment.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body") or call_args[0][2]
        assert "This matters because reasons" in body

    @pytest.mark.asyncio
    async def test_inline_passes_correct_file_and_line(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(file="api/handler.py", line=99),))

        await reporter.report(result)

        scm.post_review_comment.assert_called_once()
        call_kwargs = scm.post_review_comment.call_args.kwargs
        assert call_kwargs["file_path"] == "api/handler.py"
        assert call_kwargs["line"] == 99

    @pytest.mark.asyncio
    async def test_inline_only_does_not_post_summary(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        scm.post_review_summary.assert_not_called()


# ------------------------------------------------------------------ #
# Summary comment style
# ------------------------------------------------------------------ #


class TestSummaryComment:
    @pytest.mark.asyncio
    async def test_summary_posts_single_review(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary")
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        scm.post_review_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_summary_contains_findings_table(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary")
        findings = (
            _make_finding(severity=Severity.HIGH, file="src/a.py", line=10, title="Issue A"),
            _make_finding(severity=Severity.LOW, file="src/b.py", line=20, title="Issue B"),
        )
        result = _make_result(findings)

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args.kwargs
        body = call_kwargs["body"]
        # Table should contain file:line, severity, pattern, title
        assert "src/a.py" in body
        assert "src/b.py" in body
        assert "Issue A" in body
        assert "Issue B" in body

    @pytest.mark.asyncio
    async def test_summary_only_does_not_post_inline(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary")
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        scm.post_review_comment.assert_not_called()


# ------------------------------------------------------------------ #
# Both comment style
# ------------------------------------------------------------------ #


class TestBothCommentStyle:
    @pytest.mark.asyncio
    async def test_both_posts_inline_and_summary(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="both")
        findings = (_make_finding(), _make_finding(file="other.py", line=5))
        result = _make_result(findings)

        await reporter.report(result)

        assert scm.post_review_comment.call_count == 2
        scm.post_review_summary.assert_called_once()


# ------------------------------------------------------------------ #
# Review decision (REQUEST_CHANGES vs COMMENT)
# ------------------------------------------------------------------ #


class TestReviewDecision:
    @pytest.mark.asyncio
    async def test_request_changes_when_finding_meets_threshold(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary", request_changes_on="high")
        result = _make_result((_make_finding(severity=Severity.CRITICAL),))

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args.kwargs
        assert call_kwargs["request_changes"] is True
        assert call_kwargs["approve"] is False

    @pytest.mark.asyncio
    async def test_request_changes_when_finding_equals_threshold(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary", request_changes_on="high")
        result = _make_result((_make_finding(severity=Severity.HIGH),))

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args.kwargs
        assert call_kwargs["request_changes"] is True

    @pytest.mark.asyncio
    async def test_comment_when_findings_below_threshold(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary", request_changes_on="critical")
        result = _make_result((_make_finding(severity=Severity.MEDIUM),))

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args.kwargs
        assert call_kwargs["request_changes"] is False
        assert call_kwargs["approve"] is False

    @pytest.mark.asyncio
    async def test_comment_when_no_findings(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="summary")
        result = _make_result()

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args.kwargs
        assert call_kwargs["request_changes"] is False


# ------------------------------------------------------------------ #
# Severity badges
# ------------------------------------------------------------------ #


class TestSeverityBadges:
    @pytest.mark.asyncio
    async def test_all_severity_levels_have_badges(self) -> None:
        for sev in Severity:
            scm = _make_scm()
            reporter = _make_reporter(scm, comment_style="inline")
            result = _make_result((_make_finding(severity=sev),))

            await reporter.report(result)

            call_args = scm.post_review_comment.call_args
            body = call_args.kwargs.get("body") or call_args[0][2]
            assert sev.value.upper() in body.upper()


# ------------------------------------------------------------------ #
# Error handling
# ------------------------------------------------------------------ #


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_inline_api_error_does_not_crash(self) -> None:
        scm = _make_scm()
        scm.post_review_comment.side_effect = Exception("API error")
        reporter = _make_reporter(scm, comment_style="inline")
        result = _make_result((_make_finding(),))

        # Should not raise
        await reporter.report(result)

    @pytest.mark.asyncio
    async def test_summary_api_error_does_not_crash(self) -> None:
        scm = _make_scm()
        scm.post_review_summary.side_effect = Exception("API error")
        reporter = _make_reporter(scm, comment_style="summary")
        result = _make_result((_make_finding(),))

        # Should not raise
        await reporter.report(result)

    @pytest.mark.asyncio
    async def test_no_pr_url_does_not_crash(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, comment_style="both")
        result = ReviewResult(
            findings=(_make_finding(),),
            stats=ReviewStats(
                files_reviewed=1,
                patterns_loaded=1,
                patterns_matched=1,
                findings_total=1,
            ),
            target=ReviewTarget(type="diff", pr_url=None),
        )

        # Should not raise — just skip posting
        await reporter.report(result)
        scm.post_review_comment.assert_not_called()
        scm.post_review_summary.assert_not_called()


# ------------------------------------------------------------------ #
# Disabled reporter
# ------------------------------------------------------------------ #


class TestDisabledReporter:
    @pytest.mark.asyncio
    async def test_disabled_reporter_does_nothing(self) -> None:
        scm = _make_scm()
        reporter = _make_reporter(scm, enabled=False)
        result = _make_result((_make_finding(),))

        await reporter.report(result)

        scm.post_review_comment.assert_not_called()
        scm.post_review_summary.assert_not_called()
