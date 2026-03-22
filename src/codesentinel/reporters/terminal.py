"""Terminal reporter using Rich for formatted, color-coded output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codesentinel.core.enums import Severity
from codesentinel.core.models import Finding, ReviewResult, ReviewStats
from codesentinel.reporters.base import Reporter

_SEVERITY_COLORS: dict[Severity, str] = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "bright_red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
    Severity.INFO: "dim",
}

_SEVERITY_ICONS: dict[Severity, str] = {
    Severity.CRITICAL: "[!]",
    Severity.HIGH: "[H]",
    Severity.MEDIUM: "[M]",
    Severity.LOW: "[L]",
    Severity.INFO: "[i]",
}


class TerminalReporter(Reporter):
    """Display review results in the terminal using Rich."""

    def __init__(
        self,
        *,
        color: bool = True,
        verbose: bool = False,
        console: Console | None = None,
    ) -> None:
        self._color = color
        self._verbose = verbose
        self._console = console or Console(force_terminal=color, no_color=not color)

    def is_enabled(self) -> bool:
        return True

    async def report(self, result: ReviewResult) -> None:
        """Print the review result to the terminal."""
        self._print_header()
        self._print_target_info(result)

        if result.findings:
            self._print_findings(result.findings)
        else:
            self._console.print("\n[green]No findings.[/green]\n")

        self._print_summary(result.stats)

    # ------------------------------------------------------------------ #
    # Header
    # ------------------------------------------------------------------ #

    def _print_header(self) -> None:
        title = Text("CodeSentinel", style="bold cyan")
        tagline = Text(" - AI-Powered Code Review", style="dim")
        self._console.print()
        self._console.print(title + tagline)
        self._console.print()

    # ------------------------------------------------------------------ #
    # Target info
    # ------------------------------------------------------------------ #

    def _print_target_info(self, result: ReviewResult) -> None:
        target = result.target
        info_parts: list[str] = []

        if target.pr_url:
            info_parts.append(f"PR: {target.pr_url}")
        elif target.branch:
            base = target.base_branch or "main"
            info_parts.append(f"Branch: {target.branch} (base: {base})")
        elif target.diff_path:
            info_parts.append(f"Diff: {target.diff_path}")

        info_parts.append(f"Files: {result.stats.files_reviewed}")
        info_parts.append(f"Patterns: {result.stats.patterns_loaded}")

        self._console.print("  ".join(info_parts), style="dim")

    # ------------------------------------------------------------------ #
    # Findings
    # ------------------------------------------------------------------ #

    def _print_findings(self, findings: tuple[Finding, ...]) -> None:
        self._console.print()
        for finding in findings:
            self._print_finding(finding)

    def _print_finding(self, finding: Finding) -> None:
        severity = finding.severity
        color = _SEVERITY_COLORS.get(severity, "white")
        icon = _SEVERITY_ICONS.get(severity, "[-]")

        title_text = f"{icon} {severity.value.upper()}: {finding.title}"
        body_lines: list[str] = [
            f"Pattern: {finding.pattern_name}",
            f"File:    {finding.file}:{finding.line}",
            f"\n{finding.description}",
        ]

        if self._verbose and finding.rationale:
            body_lines.append(f"\nWhy: {finding.rationale}")
        if self._verbose and finding.remediation:
            body_lines.append(f"\nFix: {finding.remediation}")

        panel = Panel(
            "\n".join(body_lines),
            title=title_text,
            border_style=color,
            expand=False,
        )
        self._console.print(panel)

    # ------------------------------------------------------------------ #
    # Summary footer
    # ------------------------------------------------------------------ #

    def _print_summary(self, stats: ReviewStats) -> None:
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("label", style="dim")
        table.add_column("value")

        # Findings by severity
        severity_parts: list[str] = []
        for sev in Severity:
            count = stats.findings_by_severity.get(sev, 0)
            if count > 0:
                color = _SEVERITY_COLORS.get(sev, "white")
                severity_parts.append(f"[{color}]{count} {sev.value}[/{color}]")

        findings_str = ", ".join(severity_parts) if severity_parts else "0"
        table.add_row("Findings:", findings_str)
        table.add_row("Files reviewed:", str(stats.files_reviewed))

        if stats.input_tokens or stats.output_tokens:
            tokens = f"{stats.input_tokens + stats.output_tokens:,} ({stats.llm_calls} calls)"
            table.add_row("Tokens:", tokens)

        if stats.duration_ms:
            seconds = stats.duration_ms / 1000
            table.add_row("Time:", f"{seconds:.1f}s")

        self._console.print()
        self._console.print(
            Panel(table, title="Summary", border_style="cyan", expand=False)
        )
        self._console.print()
