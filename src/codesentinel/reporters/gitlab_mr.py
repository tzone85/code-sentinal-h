"""GitLab Merge Request reporter — posts findings as MR discussion threads."""

from __future__ import annotations

import logging

from codesentinel.core.enums import Severity
from codesentinel.core.models import Finding, ReviewResult
from codesentinel.reporters.base import Reporter
from codesentinel.scm.gitlab import GitLabSCM

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI: dict[Severity, str] = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
    Severity.INFO: "\u2139\ufe0f",
}


class GitLabMRReporter(Reporter):
    """Post review findings as GitLab MR discussion threads.

    Each finding becomes an inline discussion thread on the affected file/line.
    A summary note aggregates all findings at the MR level.
    """

    def __init__(
        self,
        scm: GitLabSCM,
        mr_identifier: str,
    ) -> None:
        self._scm = scm
        self._mr_identifier = mr_identifier

    def is_enabled(self) -> bool:
        return True

    async def report(self, result: ReviewResult) -> None:
        """Post all findings as inline threads plus a summary note."""
        for finding in result.findings:
            await self._post_inline_comment(finding)

        await self._post_summary(result)

    async def _post_inline_comment(self, finding: Finding) -> None:
        """Post a single finding as an inline MR discussion thread."""
        emoji = _SEVERITY_EMOJI.get(finding.severity, "❓")
        body = (
            f"{emoji} **{finding.severity.value.upper()}**: {finding.title}\n\n"
            f"**Pattern:** {finding.pattern_name}\n\n"
            f"{finding.description}\n\n"
            f"**Remediation:** {finding.remediation}"
        )

        try:
            await self._scm.post_review_comment(
                self._mr_identifier,
                file_path=finding.file,
                line=finding.line,
                body=body,
                severity=finding.severity.value,
            )
        except Exception:
            logger.warning(
                "Failed to post inline comment for %s at %s:%d",
                finding.pattern_name,
                finding.file,
                finding.line,
            )

    async def _post_summary(self, result: ReviewResult) -> None:
        """Post a summary note on the MR with all findings aggregated."""
        lines: list[str] = ["## 🔍 CodeSentinel Review Summary\n"]

        stats = result.stats
        lines.append(f"**Files reviewed:** {stats.files_reviewed}")
        lines.append(f"**Patterns loaded:** {stats.patterns_loaded}")
        lines.append(f"**Total findings:** {stats.findings_total}\n")

        if result.findings:
            lines.append("### Findings by Severity\n")
            lines.append("| Severity | Count |")
            lines.append("|----------|-------|")
            for sev in Severity:
                count = stats.findings_by_severity.get(sev, 0)
                if count > 0:
                    emoji = _SEVERITY_EMOJI.get(sev, "")
                    lines.append(f"| {emoji} {sev.value.upper()} | {count} |")

            lines.append("\n### Details\n")
            for finding in result.findings:
                emoji = _SEVERITY_EMOJI.get(finding.severity, "")
                lines.append(
                    f"- {emoji} **{finding.severity.value.upper()}** "
                    f"`{finding.file}:{finding.line}` — {finding.title}"
                )
        else:
            lines.append("✅ **No issues found.** Great work!")

        body = "\n".join(lines)

        has_critical = stats.findings_by_severity.get(Severity.CRITICAL, 0) > 0
        has_high = stats.findings_by_severity.get(Severity.HIGH, 0) > 0
        request_changes = has_critical or has_high
        approve = not result.findings

        try:
            await self._scm.post_review_summary(
                self._mr_identifier,
                body=body,
                approve=approve,
                request_changes=request_changes,
            )
        except Exception:
            logger.warning("Failed to post review summary on %s", self._mr_identifier)
