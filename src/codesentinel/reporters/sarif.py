"""SARIF v2.1.0 reporter for IDE integration (VS Code, IntelliJ).

Generates a SARIF (Static Analysis Results Interchange Format) JSON file
from review findings. The output conforms to the OASIS SARIF v2.1.0 spec.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import codesentinel
from codesentinel.core.enums import Severity
from codesentinel.core.models import Finding, ReviewResult
from codesentinel.reporters.base import Reporter

logger = logging.getLogger(__name__)

_SARIF_VERSION = "2.1.0"
_SARIF_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"
_INFORMATION_URI = "https://github.com/tzone85/code-sentinal-h"

_SEVERITY_TO_LEVEL: dict[Severity, str] = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}

_DEFAULT_SARIF_LEVEL = "warning"


def _severity_to_sarif_level(severity: Severity) -> str:
    """Map a CodeSentinel severity to the SARIF ``level`` value.

    Falls back to ``"warning"`` for any unmapped severity to avoid
    crashing on future enum additions.
    """
    level = _SEVERITY_TO_LEVEL.get(severity)
    if level is None:
        logger.warning("Unmapped severity %r; defaulting to %r", severity, _DEFAULT_SARIF_LEVEL)
        return _DEFAULT_SARIF_LEVEL
    return level


class SarifReporter(Reporter):
    """Write review findings as a SARIF v2.1.0 JSON file."""

    def __init__(
        self,
        *,
        output_path: str = "codesentinel-report.sarif",
        enabled: bool = True,
    ) -> None:
        self._output_path = output_path
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def report(self, result: ReviewResult) -> None:
        """Generate a SARIF document and write it to *output_path*."""
        rules, rule_index = _build_rules(result.findings)
        results = _build_results(result.findings, rule_index)

        sarif: dict[str, Any] = {
            "$schema": _SARIF_SCHEMA,
            "version": _SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "CodeSentinel",
                            "version": codesentinel.__version__,
                            "informationUri": _INFORMATION_URI,
                            "rules": rules,
                        },
                    },
                    "results": results,
                    "originalUriBaseIds": {
                        "%SRCROOT%": {"uri": "file:///"},
                    },
                },
            ],
        }

        output = Path(self._output_path)
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(sarif, indent=2), encoding="utf-8")
        except OSError:
            logger.error("Failed to write SARIF report to %s", self._output_path, exc_info=True)
            return
        logger.info("SARIF report written to %s", self._output_path)


# --------------------------------------------------------------------------- #
# Internal builders (pure functions — no side effects)
# --------------------------------------------------------------------------- #


def _build_rules(
    findings: tuple[Finding, ...],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Build deduplicated SARIF rules and a name→index mapping.

    When multiple findings share a ``pattern_name``, the first occurrence's
    metadata (title, description, severity) wins — consistent with how
    the pattern registry treats the pattern as a single logical rule.
    """
    rules: list[dict[str, Any]] = []
    rule_index: dict[str, int] = {}

    for finding in findings:
        if finding.pattern_name in rule_index:
            continue
        rule_index[finding.pattern_name] = len(rules)
        rules.append(
            {
                "id": finding.pattern_name,
                "name": finding.title,
                "shortDescription": {"text": finding.title},
                "fullDescription": {"text": finding.description},
                "defaultConfiguration": {
                    "level": _severity_to_sarif_level(finding.severity),
                },
            },
        )

    return rules, rule_index


def _build_results(
    findings: tuple[Finding, ...],
    rule_index: dict[str, int],
) -> list[dict[str, Any]]:
    """Build a SARIF results array — one entry per finding."""
    return [_finding_to_result(f, rule_index) for f in findings]


def _finding_to_result(
    finding: Finding,
    rule_index: dict[str, int],
) -> dict[str, Any]:
    """Convert a single Finding to a SARIF result object."""
    region: dict[str, Any] = {"startLine": finding.line}
    if finding.code_snippet:
        region["snippet"] = {"text": finding.code_snippet}

    # Normalize path separators to forward slashes for valid URI (SARIF §3.29.5)
    uri = finding.file.replace("\\", "/")
    message_text = f"{finding.title}: {finding.description}"

    return {
        "ruleId": finding.pattern_name,
        "ruleIndex": rule_index[finding.pattern_name],
        "level": _severity_to_sarif_level(finding.severity),
        "message": {"text": message_text},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": uri,
                        "uriBaseId": "%SRCROOT%",
                    },
                    "region": region,
                },
            },
        ],
    }
