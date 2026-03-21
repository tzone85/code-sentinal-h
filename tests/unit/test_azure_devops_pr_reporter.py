"""Unit tests for reporters/azure_devops_pr.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.azure_devops_pr import AzureDevOpsPRReporter
from codesentinel.scm.azure_devops import AzureDevOpsSCM


def _make_result(
    findings: tuple[Finding, ...] = (),
    *,
    files_reviewed: int = 3,
    patterns_loaded: int = 5,
) -> ReviewResult:
    severity_counts: dict[Severity, int] = {}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
    return ReviewResult(
        findings=findings,
        stats=ReviewStats(
            files_reviewed=files_reviewed,
            patterns_loaded=patterns_loaded,
            patterns_matched=2,
            findings_total=len(findings),
            findings_by_severity=severity_counts,
        ),
        target=ReviewTarget(
            type="pr",
            pr_url="https://dev.azure.com/org/proj/_git/repo/pullrequest/42",
        ),
    )


def _make_finding(
    severity: Severity = Severity.HIGH,
    title: str = "Test issue",
) -> Finding:
    return Finding(
        pattern_name="test-pattern",
        severity=severity,
        confidence=0.9,
        file="src/main.py",
        line=42,
        title=title,
        description="A test finding description.",
        rationale="This matters because reasons.",
        remediation="Fix by doing the thing.",
    )


class TestAzureDevOpsPRReporterEnabled:
    def test_is_enabled_returns_true(self) -> None:
        scm = MagicMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        assert reporter.is_enabled() is True


class TestAzureDevOpsPRReporterReport:
    @pytest.mark.asyncio
    async def test_no_findings_posts_only_summary(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        result = _make_result()

        await reporter.report(result)

        scm.post_review_comment.assert_not_called()
        scm.post_review_summary.assert_called_once()
        call_kwargs = scm.post_review_summary.call_args[1]
        assert call_kwargs["approve"] is True
        assert call_kwargs["request_changes"] is False
        assert "No issues found" in call_kwargs["body"]

    @pytest.mark.asyncio
    async def test_findings_post_inline_and_summary(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        finding = _make_finding(severity=Severity.HIGH, title="Bug found")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        assert scm.post_review_comment.call_count == 1
        scm.post_review_summary.assert_called_once()

        comment_kwargs = scm.post_review_comment.call_args[1]
        assert comment_kwargs["file_path"] == "src/main.py"
        assert comment_kwargs["line"] == 42
        assert "Bug found" in comment_kwargs["body"]

    @pytest.mark.asyncio
    async def test_critical_findings_request_changes(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        finding = _make_finding(severity=Severity.CRITICAL, title="Critical bug")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args[1]
        assert call_kwargs["request_changes"] is True
        assert call_kwargs["approve"] is False

    @pytest.mark.asyncio
    async def test_medium_findings_no_request_changes(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        finding = _make_finding(severity=Severity.MEDIUM, title="Style issue")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        call_kwargs = scm.post_review_summary.call_args[1]
        assert call_kwargs["request_changes"] is False
        assert call_kwargs["approve"] is False

    @pytest.mark.asyncio
    async def test_multiple_findings_post_all_inline(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        findings = (
            _make_finding(severity=Severity.HIGH, title="Issue 1"),
            _make_finding(severity=Severity.LOW, title="Issue 2"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        assert scm.post_review_comment.call_count == 2
        scm.post_review_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_inline_comment_failure_does_not_stop_report(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        scm.post_review_comment.side_effect = Exception("API error")
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        finding = _make_finding()
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        scm.post_review_summary.assert_called_once()

    @pytest.mark.asyncio
    async def test_summary_contains_severity_table(self) -> None:
        scm = AsyncMock(spec=AzureDevOpsSCM)
        reporter = AzureDevOpsPRReporter(scm=scm, pr_identifier="o/p/r#42")
        findings = (
            _make_finding(severity=Severity.CRITICAL, title="Critical bug"),
            _make_finding(severity=Severity.MEDIUM, title="Medium issue"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        body = scm.post_review_summary.call_args[1]["body"]
        assert "CRITICAL" in body
        assert "MEDIUM" in body
        assert "Severity" in body
