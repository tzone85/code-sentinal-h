"""GitHub PR reporter — posts review findings as PR comments."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from codesentinel.core.enums import Severity
from codesentinel.reporters.base import Reporter

if TYPE_CHECKING:
    from codesentinel.config.schema import GitHubReporterConfig
    from codesentinel.core.models import Finding, ReviewResult
    from codesentinel.scm.github import GitHubSCM

logger = logging.getLogger(__name__)

_SEVERITY_BADGES: dict[Severity, str] = {
    Severity.CRITICAL: "\U0001f534 **CRITICAL**",
    Severity.HIGH: "\U0001f7e0 **HIGH**",
    Severity.MEDIUM: "\U0001f7e1 **MEDIUM**",
    Severity.LOW: "\U0001f535 **LOW**",
    Severity.INFO: "\u2139\ufe0f **INFO**",
}

class GitHubPRReporter(Reporter):
    """Posts review findings as GitHub PR comments via the GitHub API."""

    def __init__(
        self,
        config: GitHubReporterConfig,
        scm: GitHubSCM,
    ) -> None:
        self._config = config
        self._scm = scm

    def is_enabled(self) -> bool:
        return self._config.enabled

    async def report(self, result: ReviewResult) -> None:
        if not self._config.enabled:
            return

        pr_url = result.target.pr_url
        if not pr_url:
            logger.warning("No PR URL in review target — skipping GitHub report")
            return

        style = self._config.comment_style

        if style in ("inline", "both"):
            await self._post_inline_comments(pr_url, result.findings)

        if style in ("summary", "both"):
            await self._post_summary(pr_url, result)

    # ------------------------------------------------------------------ #
    # Inline comments
    # ------------------------------------------------------------------ #

    async def _post_inline_comments(
        self,
        pr_url: str,
        findings: tuple[Finding, ...],
    ) -> None:
        for finding in findings:
            body = _format_inline_comment(finding)
            try:
                await self._scm.post_review_comment(
                    pr_identifier=pr_url,
                    file_path=finding.file,
                    line=finding.line,
                    body=body,
                    severity=finding.severity.value,
                )
            except Exception:
                logger.exception(
                    "Failed to post inline comment on %s:%d",
                    finding.file,
                    finding.line,
                )

    # ------------------------------------------------------------------ #
    # Summary review
    # ------------------------------------------------------------------ #

    async def _post_summary(
        self,
        pr_url: str,
        result: ReviewResult,
    ) -> None:
        body = _format_summary(result)
        should_request_changes = _should_request_changes(
            result.findings,
            self._config.request_changes_on,
        )

        try:
            await self._scm.post_review_summary(
                pr_identifier=pr_url,
                body=body,
                approve=False,
                request_changes=should_request_changes,
            )
        except Exception:
            logger.exception("Failed to post review summary on %s", pr_url)


# ------------------------------------------------------------------ #
# Formatting helpers (module-level, pure functions)
# ------------------------------------------------------------------ #


def _format_inline_comment(finding: Finding) -> str:
    badge = _SEVERITY_BADGES.get(finding.severity, finding.severity.value.upper())
    lines = [
        f"{badge}",
        "",
        f"**Pattern:** `{finding.pattern_name}`",
        "",
        finding.description,
        "",
        f"**Why:** {finding.rationale}",
        "",
        f"**Remediation:** {finding.remediation}",
    ]
    return "\n".join(lines)


def _format_summary(result: ReviewResult) -> str:
    findings = result.findings
    if not findings:
        return (
            "## CodeSentinel Review\n\n"
            "No findings detected. The code looks good!"
        )

    parts = [
        "## CodeSentinel Review",
        "",
        f"**{len(findings)} finding(s) detected.**",
        "",
        "| File | Line | Severity | Pattern | Title |",
        "|------|------|----------|---------|-------|",
    ]
    for f in findings:
        badge = _SEVERITY_BADGES.get(f.severity, f.severity.value.upper())
        parts.append(
            f"| `{f.file}` | {f.line} | {badge} | `{f.pattern_name}` | {f.title} |"
        )

    return "\n".join(parts)


def _should_request_changes(
    findings: tuple[Finding, ...],
    threshold_str: str,
) -> bool:
    try:
        threshold = Severity(threshold_str)
    except ValueError:
        logger.warning("Unknown request_changes_on value %r — skipping", threshold_str)
        return False
    return any(f.severity >= threshold for f in findings)
