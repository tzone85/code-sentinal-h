"""Unit tests for reporters/terminal.py."""

from __future__ import annotations

import pytest
from rich.console import Console

from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.terminal import TerminalReporter


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
            input_tokens=500,
            output_tokens=200,
            llm_calls=2,
            duration_ms=1500,
        ),
        target=ReviewTarget(type="diff", diff_path="test.diff"),
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


class TestTerminalReporterEnabled:
    def test_is_enabled_returns_true(self) -> None:
        reporter = TerminalReporter()
        assert reporter.is_enabled() is True


class TestTerminalReporterOutput:
    @pytest.mark.asyncio
    async def test_no_findings_shows_message(self) -> None:
        console = Console(file=None, force_terminal=False, no_color=True, width=120)
        reporter = TerminalReporter(color=False, console=console)
        result = _make_result()

        with console.capture() as capture:
            reporter._console = console
            await reporter.report(result)

        output = capture.get()
        assert "No findings" in output
        assert "CodeSentinel" in output

    @pytest.mark.asyncio
    async def test_findings_displayed(self) -> None:
        console = Console(file=None, force_terminal=False, no_color=True, width=120)
        finding = _make_finding(severity=Severity.CRITICAL, title="Critical bug")
        result = _make_result(findings=(finding,))

        reporter = TerminalReporter(color=False, console=console)
        with console.capture() as capture:
            await reporter.report(result)

        output = capture.get()
        assert "CRITICAL" in output
        assert "Critical bug" in output
        assert "test-pattern" in output
        assert "src/main.py:42" in output

    @pytest.mark.asyncio
    async def test_verbose_shows_rationale_and_remediation(self) -> None:
        console = Console(file=None, force_terminal=False, no_color=True, width=120)
        finding = _make_finding()
        result = _make_result(findings=(finding,))

        reporter = TerminalReporter(color=False, verbose=True, console=console)
        with console.capture() as capture:
            await reporter.report(result)

        output = capture.get()
        assert "This matters because reasons" in output
        assert "Fix by doing the thing" in output

    @pytest.mark.asyncio
    async def test_summary_shows_stats(self) -> None:
        console = Console(file=None, force_terminal=False, no_color=True, width=120)
        result = _make_result()

        reporter = TerminalReporter(color=False, console=console)
        with console.capture() as capture:
            await reporter.report(result)

        output = capture.get()
        assert "Summary" in output
        assert "3" in output  # files reviewed
        assert "1.5s" in output  # duration

    @pytest.mark.asyncio
    async def test_multiple_severity_findings(self) -> None:
        console = Console(file=None, force_terminal=False, no_color=True, width=120)
        findings = (
            _make_finding(severity=Severity.CRITICAL, title="Critical issue"),
            _make_finding(severity=Severity.LOW, title="Minor issue"),
        )
        result = _make_result(findings=findings)

        reporter = TerminalReporter(color=False, console=console)
        with console.capture() as capture:
            await reporter.report(result)

        output = capture.get()
        assert "CRITICAL" in output
        assert "LOW" in output
