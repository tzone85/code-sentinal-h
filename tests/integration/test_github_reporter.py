"""Integration tests for GitHub PR reporter comment posting.

Requires GITHUB_TOKEN environment variable. Skipped if not set.
Tests verify that the reporter can format and attempt to post comments.

NOTE: These tests do NOT actually post to a real PR to avoid spam.
Instead they verify the reporter's formatting and decision logic
using the real GitHubSCM class with a mock-able PR target.
For true write-path integration tests, configure a dedicated test repo.
"""

from __future__ import annotations

import os

import pytest

from codesentinel.config.schema import GitHubReporterConfig
from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.github_pr import (
    GitHubPRReporter,
    _format_inline_comment,
    _format_summary,
    _should_request_changes,
)
from codesentinel.scm.github import GitHubSCM

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="GITHUB_TOKEN not set",
    ),
]


def _make_finding(
    severity: Severity = Severity.HIGH,
    title: str = "SQL Injection Risk",
    file: str = "src/db.py",
    line: int = 42,
) -> Finding:
    return Finding(
        pattern_name="sql-injection",
        severity=severity,
        confidence=0.95,
        file=file,
        line=line,
        title=title,
        description="User input concatenated into SQL query without parameterization.",
        rationale="OWASP A03:2021 - Injection. Untrusted data in queries can lead to data breach.",
        remediation="Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
    )


def _make_result(
    findings: tuple[Finding, ...] = (),
    pr_url: str = "tzone85/code-sentinal-h#1",
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


class TestInlineCommentFormatting:
    """Verify inline comment formatting with real data."""

    def test_format_includes_all_required_fields(self) -> None:
        finding = _make_finding()
        body = _format_inline_comment(finding)

        assert "HIGH" in body
        assert "sql-injection" in body
        assert "User input concatenated" in body
        assert "OWASP" in body
        assert "parameterized queries" in body

    def test_critical_finding_has_critical_badge(self) -> None:
        finding = _make_finding(severity=Severity.CRITICAL)
        body = _format_inline_comment(finding)

        assert "CRITICAL" in body


class TestSummaryFormatting:
    """Verify summary table formatting with real data."""

    def test_summary_table_with_multiple_findings(self) -> None:
        findings = (
            _make_finding(severity=Severity.CRITICAL, file="src/auth.py", line=10),
            _make_finding(severity=Severity.HIGH, file="src/db.py", line=42),
            _make_finding(severity=Severity.MEDIUM, file="src/api.py", line=5, title="Missing validation"),
        )
        result = _make_result(findings)
        body = _format_summary(result)

        assert "3 finding(s)" in body
        assert "src/auth.py" in body
        assert "src/db.py" in body
        assert "src/api.py" in body
        assert "CRITICAL" in body
        assert "| File |" in body  # Table header

    def test_no_findings_summary(self) -> None:
        result = _make_result()
        body = _format_summary(result)

        assert "No findings" in body or "code looks good" in body.lower()


class TestRequestChangesDecision:
    """Verify the severity threshold logic for REQUEST_CHANGES."""

    def test_critical_finding_triggers_request_changes(self) -> None:
        findings = (_make_finding(severity=Severity.CRITICAL),)
        assert _should_request_changes(findings, "critical") is True

    def test_high_finding_does_not_trigger_when_threshold_is_critical(self) -> None:
        findings = (_make_finding(severity=Severity.HIGH),)
        assert _should_request_changes(findings, "critical") is False

    def test_medium_finding_triggers_when_threshold_is_medium(self) -> None:
        findings = (_make_finding(severity=Severity.MEDIUM),)
        assert _should_request_changes(findings, "medium") is True


class TestReporterWithRealSCM:
    """Test reporter initialization with a real GitHubSCM instance."""

    def test_reporter_initializes_with_real_scm(self) -> None:
        token = os.environ["GITHUB_TOKEN"]
        scm = GitHubSCM(token=token)
        config = GitHubReporterConfig(
            enabled=True,
            post_review=True,
            comment_style="both",
            request_changes_on="critical",
        )
        reporter = GitHubPRReporter(config=config, scm=scm)

        assert reporter.is_enabled() is True

    @pytest.mark.asyncio
    async def test_disabled_reporter_skips_posting(self) -> None:
        token = os.environ["GITHUB_TOKEN"]
        scm = GitHubSCM(token=token)
        config = GitHubReporterConfig(enabled=False)
        reporter = GitHubPRReporter(config=config, scm=scm)

        result = _make_result((_make_finding(),))
        # Should not raise or make any API calls
        await reporter.report(result)
