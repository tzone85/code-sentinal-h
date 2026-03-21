"""Post-processor for raw LLM review output.

Parses, validates, deduplicates, filters, sorts, and truncates findings
from the LLM before they are presented to the user.
"""

from __future__ import annotations

import json
import logging
import re

from rapidfuzz import fuzz

from codesentinel.core.enums import Severity
from codesentinel.core.models import Finding

logger = logging.getLogger(__name__)

_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}

_NO_FINDINGS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"no\s+(findings|issues|problems|violations)", re.IGNORECASE),
    re.compile(r"(looks?\s+good|lgtm|all\s+clear)", re.IGNORECASE),
)

_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*\n(.*?)\n\s*```",
    re.DOTALL,
)

_DEDUP_SIMILARITY_THRESHOLD = 0.85


class PostProcessor:
    """Cleans up and filters raw LLM output into validated findings.

    Pipeline: validate → deduplicate → filter severity → filter confidence
    → sort (critical first) → truncate to max_findings.
    """

    def __init__(
        self,
        *,
        min_severity: Severity = Severity.MEDIUM,
        min_confidence: float = 0.7,
        max_findings: int = 15,
    ) -> None:
        self.min_severity = min_severity
        self.min_confidence = min_confidence
        self.max_findings = max_findings

    # ── Public API ─────────────────────────────────────────────────────── #

    def process(self, raw_findings: list[Finding]) -> list[Finding]:
        """Run the full post-processing pipeline on a list of findings.

        Steps:
        1. Deduplicate (rapidfuzz >0.85 similarity on same file + pattern)
        2. Filter by min_severity
        3. Filter by min_confidence
        4. Sort by severity (critical first)
        5. Truncate to max_findings
        """
        if not raw_findings:
            return []

        findings = list(raw_findings)
        findings = self._deduplicate(findings)
        findings = self._filter_severity(findings)
        findings = self._filter_confidence(findings)
        findings = self._sort_by_severity(findings)
        findings = findings[: self.max_findings]
        return findings

    @staticmethod
    def parse_llm_response(content: str) -> list[dict[str, object]]:
        """Parse raw LLM response text into a list of finding dicts.

        Handles:
        - Clean JSON array
        - JSON in markdown fences (```json ... ```)
        - JSON with leading/trailing text
        - Single JSON object (wrapped into list)
        - Empty / "no findings" text → []
        - Malformed JSON → [] (logs warning, NEVER crashes)
        """
        if not content or not content.strip():
            return []

        stripped = content.strip()

        # Check for "no findings" phrases
        for pattern in _NO_FINDINGS_PATTERNS:
            if pattern.search(stripped) and not _looks_like_json(stripped):
                return []

        # 1. Try direct JSON parse
        result = _try_parse_json_array(stripped)
        if result is not None:
            return result

        # 2. Try extracting from markdown fences
        fence_match = _FENCED_JSON_RE.search(content)
        if fence_match:
            result = _try_parse_json_array(fence_match.group(1).strip())
            if result is not None:
                return result

        # 3. Try finding JSON array/object in the text
        result = _extract_json_from_text(stripped)
        if result is not None:
            return result

        logger.warning("Failed to parse LLM response as JSON: %.100s...", stripped)
        return []

    # ── Internal pipeline steps ────────────────────────────────────────── #

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """Remove duplicate findings using rapidfuzz string matching.

        Two findings are considered duplicates when they share the same
        file and pattern, and their descriptions have >0.85 similarity.
        The finding with higher confidence is kept.
        """
        if len(findings) <= 1:
            return findings

        kept: list[Finding] = []

        for finding in findings:
            merged = False
            for i, existing in enumerate(kept):
                if (
                    existing.file == finding.file
                    and existing.pattern_name == finding.pattern_name
                    and fuzz.ratio(existing.description, finding.description) > _DEDUP_SIMILARITY_THRESHOLD * 100
                ):
                    # Keep the one with higher confidence
                    if finding.confidence > existing.confidence:
                        kept[i] = finding
                    merged = True
                    break

            if not merged:
                kept.append(finding)

        return kept

    def _filter_severity(self, findings: list[Finding]) -> list[Finding]:
        """Keep only findings at or above the minimum severity threshold."""
        return [f for f in findings if f.severity >= self.min_severity]

    def _filter_confidence(self, findings: list[Finding]) -> list[Finding]:
        """Keep only findings at or above the minimum confidence threshold."""
        return [f for f in findings if f.confidence >= self.min_confidence]

    @staticmethod
    def _sort_by_severity(findings: list[Finding]) -> list[Finding]:
        """Sort findings by severity, most severe first."""
        return sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99))


# ── Module-private helpers ────────────────────────────────────────────────── #


def _looks_like_json(text: str) -> bool:
    """Quick check if text likely contains JSON."""
    return "[" in text or "{" in text


def _try_parse_json_array(text: str) -> list[dict[str, object]] | None:
    """Try to parse text as a JSON array or single object.

    Returns None if parsing fails (caller should try next strategy).
    Returns [] for empty arrays.
    """
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None

    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]

    if isinstance(parsed, dict):
        return [parsed]

    return None


def _extract_json_from_text(text: str) -> list[dict[str, object]] | None:
    """Try to find and extract a JSON array or object embedded in text."""
    for open_char, close_char in [("[", "]"), ("{", "}")]:
        start = text.find(open_char)
        if start == -1:
            continue

        # Try from open bracket to each matching close bracket (last first)
        end = text.rfind(close_char)
        while end > start:
            candidate = text[start : end + 1]
            result = _try_parse_json_array(candidate)
            if result is not None:
                return result
            end = text.rfind(close_char, start, end)

    return None
