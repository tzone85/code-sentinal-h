"""Tests for core/post_processor.py — PostProcessor and parse_llm_response."""

from __future__ import annotations

import json

from codesentinel.core.enums import Severity
from codesentinel.core.models import Finding
from codesentinel.core.post_processor import PostProcessor

# ── Helpers ────────────────────────────────────────────────────────────────── #


def _finding(
    *,
    pattern: str = "test-pattern",
    severity: Severity = Severity.MEDIUM,
    confidence: float = 0.9,
    file: str = "src/main.py",
    line: int = 10,
    title: str = "Test finding",
    description: str = "A test finding description",
    rationale: str = "Because tests",
    remediation: str = "Fix it",
) -> Finding:
    return Finding(
        pattern_name=pattern,
        severity=severity,
        confidence=confidence,
        file=file,
        line=line,
        title=title,
        description=description,
        rationale=rationale,
        remediation=remediation,
    )


def _raw_finding_dict(
    *,
    pattern_name: str = "test-pattern",
    severity: str = "medium",
    confidence: float = 0.9,
    file: str = "src/main.py",
    line: int = 10,
    title: str = "Test finding",
    description: str = "A test finding",
    rationale: str = "Because",
    remediation: str = "Fix",
) -> dict[str, object]:
    return {
        "pattern_name": pattern_name,
        "severity": severity,
        "confidence": confidence,
        "file": file,
        "line": line,
        "title": title,
        "description": description,
        "rationale": rationale,
        "remediation": remediation,
    }


# ══════════════════════════════════════════════════════════════════════════════ #
#  parse_llm_response
# ══════════════════════════════════════════════════════════════════════════════ #


class TestParseLlmResponse:
    """Tests for PostProcessor.parse_llm_response static method."""

    def test_clean_json_array(self) -> None:
        findings = [_raw_finding_dict(), _raw_finding_dict(title="Second")]
        content = json.dumps(findings)
        result = PostProcessor.parse_llm_response(content)
        assert len(result) == 2
        assert result[0]["title"] == "Test finding"
        assert result[1]["title"] == "Second"

    def test_json_in_markdown_fences(self) -> None:
        finding = _raw_finding_dict()
        content = f"Here are the findings:\n```json\n{json.dumps([finding])}\n```\nEnd of review."
        result = PostProcessor.parse_llm_response(content)
        assert len(result) == 1
        assert result[0]["title"] == "Test finding"

    def test_json_in_plain_fences(self) -> None:
        finding = _raw_finding_dict()
        content = f"```\n{json.dumps([finding])}\n```"
        result = PostProcessor.parse_llm_response(content)
        assert len(result) == 1

    def test_json_with_leading_trailing_text(self) -> None:
        finding = _raw_finding_dict()
        content = f"I found these issues:\n{json.dumps([finding])}\nThat's all."
        result = PostProcessor.parse_llm_response(content)
        assert len(result) == 1

    def test_empty_string_returns_empty(self) -> None:
        result = PostProcessor.parse_llm_response("")
        assert result == []

    def test_no_findings_text_returns_empty(self) -> None:
        result = PostProcessor.parse_llm_response("No findings detected.")
        assert result == []

    def test_no_issues_text_returns_empty(self) -> None:
        result = PostProcessor.parse_llm_response("No issues found in this code.")
        assert result == []

    def test_empty_json_array_returns_empty(self) -> None:
        result = PostProcessor.parse_llm_response("[]")
        assert result == []

    def test_malformed_json_returns_empty(self) -> None:
        result = PostProcessor.parse_llm_response("{broken json [[[")
        assert result == []

    def test_malformed_json_never_crashes(self) -> None:
        """parse_llm_response must NEVER raise — always returns []."""
        bad_inputs = [
            "not json at all",
            "{ incomplete",
            "[{]",
            "null",
            "true",
            "42",
            '{"key": "not an array"}',
        ]
        for bad_input in bad_inputs:
            result = PostProcessor.parse_llm_response(bad_input)
            assert isinstance(result, list)

    def test_single_object_wrapped_as_list(self) -> None:
        """A single JSON object (not array) should be wrapped into a list."""
        finding = _raw_finding_dict()
        content = json.dumps(finding)
        result = PostProcessor.parse_llm_response(content)
        assert len(result) == 1
        assert result[0]["title"] == "Test finding"


# ══════════════════════════════════════════════════════════════════════════════ #
#  PostProcessor construction
# ══════════════════════════════════════════════════════════════════════════════ #


class TestPostProcessorInit:
    """Tests for PostProcessor initialisation."""

    def test_defaults(self) -> None:
        pp = PostProcessor()
        assert pp.min_severity == Severity.MEDIUM
        assert pp.min_confidence == 0.7
        assert pp.max_findings == 15

    def test_custom_values(self) -> None:
        pp = PostProcessor(
            min_severity=Severity.HIGH,
            min_confidence=0.5,
            max_findings=10,
        )
        assert pp.min_severity == Severity.HIGH
        assert pp.min_confidence == 0.5
        assert pp.max_findings == 10


# ══════════════════════════════════════════════════════════════════════════════ #
#  process — full pipeline
# ══════════════════════════════════════════════════════════════════════════════ #


class TestProcess:
    """Tests for PostProcessor.process() pipeline."""

    def test_empty_input_returns_empty(self) -> None:
        pp = PostProcessor()
        assert pp.process([]) == []

    def test_valid_findings_pass_through(self) -> None:
        pp = PostProcessor(min_severity=Severity.LOW)
        findings = [
            _finding(
                severity=Severity.HIGH,
                confidence=0.9,
                file="src/a.py",
                description="Missing authentication check on endpoint",
            ),
            _finding(
                severity=Severity.MEDIUM,
                confidence=0.8,
                file="src/b.py",
                title="Second",
                description="Database connection pool exhaustion risk",
            ),
        ]
        result = pp.process(findings)
        assert len(result) == 2

    def test_sorted_by_severity_critical_first(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO)
        findings = [
            _finding(
                severity=Severity.LOW,
                title="low",
                file="src/e.py",
                description="Variable naming does not follow convention",
            ),
            _finding(
                severity=Severity.CRITICAL,
                title="critical",
                file="src/a.py",
                description="SQL injection via unsanitized user input",
            ),
            _finding(
                severity=Severity.MEDIUM,
                title="medium",
                file="src/c.py",
                description="Missing error handling in API call",
            ),
            _finding(
                severity=Severity.HIGH,
                title="high",
                file="src/b.py",
                description="Hardcoded database credentials found",
            ),
            _finding(
                severity=Severity.INFO, title="info", file="src/d.py", description="Consider extracting helper function"
            ),
        ]
        result = pp.process(findings)
        severities = [f.severity for f in result]
        assert severities == [
            Severity.CRITICAL,
            Severity.HIGH,
            Severity.MEDIUM,
            Severity.LOW,
            Severity.INFO,
        ]

    def test_filter_by_min_severity(self) -> None:
        pp = PostProcessor(min_severity=Severity.HIGH)
        findings = [
            _finding(severity=Severity.CRITICAL, file="src/a.py", description="Remote code execution via eval"),
            _finding(
                severity=Severity.HIGH, title="high", file="src/b.py", description="Missing CSRF token validation"
            ),
            _finding(severity=Severity.MEDIUM, title="medium", file="src/c.py", description="Unused import in module"),
            _finding(severity=Severity.LOW, title="low", file="src/d.py", description="Line exceeds maximum length"),
        ]
        result = pp.process(findings)
        assert all(f.severity >= Severity.HIGH for f in result)
        assert len(result) == 2

    def test_filter_by_min_confidence(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO, min_confidence=0.7)
        findings = [
            _finding(
                confidence=0.9, title="high-conf", file="src/a.py", description="Authentication bypass vulnerability"
            ),
            _finding(confidence=0.5, title="low-conf", file="src/b.py", description="Potential memory leak in loop"),
            _finding(
                confidence=0.7, title="threshold-conf", file="src/c.py", description="Missing input validation on form"
            ),
        ]
        result = pp.process(findings)
        assert len(result) == 2
        titles = {f.title for f in result}
        assert "low-conf" not in titles

    def test_truncate_to_max_findings(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO, max_findings=3)
        findings = [
            _finding(
                title=f"finding-{i}",
                severity=Severity.MEDIUM,
                file=f"src/file_{i}.py",
                description=f"Unique issue number {i} in different module",
            )
            for i in range(10)
        ]
        result = pp.process(findings)
        assert len(result) == 3

    def test_truncation_keeps_highest_severity(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO, max_findings=2)
        findings = [
            _finding(
                severity=Severity.LOW, title="low", file="src/c.py", description="Variable naming convention violation"
            ),
            _finding(
                severity=Severity.CRITICAL,
                title="critical",
                file="src/a.py",
                description="SQL injection via raw query execution",
            ),
            _finding(
                severity=Severity.MEDIUM,
                title="medium",
                file="src/b.py",
                description="Missing error boundary in component",
            ),
        ]
        result = pp.process(findings)
        assert len(result) == 2
        assert result[0].severity == Severity.CRITICAL
        assert result[1].severity == Severity.MEDIUM


# ══════════════════════════════════════════════════════════════════════════════ #
#  _deduplicate
# ══════════════════════════════════════════════════════════════════════════════ #


class TestDeduplicate:
    """Tests for PostProcessor._deduplicate."""

    def test_no_duplicates_unchanged(self) -> None:
        pp = PostProcessor()
        findings = [
            _finding(description="Totally unique finding A"),
            _finding(description="Completely different finding B"),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 2

    def test_exact_duplicates_merged(self) -> None:
        pp = PostProcessor()
        findings = [
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="SQL injection via unsanitized input",
                confidence=0.8,
            ),
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="SQL injection via unsanitized input",
                confidence=0.9,
            ),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 1
        assert result[0].confidence == 0.9  # keeps higher confidence

    def test_similar_descriptions_merged(self) -> None:
        """Findings with >0.85 similarity on same file+pattern should merge."""
        pp = PostProcessor()
        findings = [
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="SQL injection vulnerability in user input handling",
                confidence=0.75,
            ),
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="SQL injection vulnerability in user input processing",
                confidence=0.85,
            ),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 1
        assert result[0].confidence == 0.85

    def test_different_files_not_merged(self) -> None:
        """Same description but different files should NOT be merged."""
        pp = PostProcessor()
        findings = [
            _finding(
                file="src/a.py",
                pattern="sec-001",
                description="SQL injection vulnerability",
            ),
            _finding(
                file="src/b.py",
                pattern="sec-001",
                description="SQL injection vulnerability",
            ),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 2

    def test_different_patterns_not_merged(self) -> None:
        """Same description but different patterns should NOT be merged."""
        pp = PostProcessor()
        findings = [
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="SQL injection vulnerability",
            ),
            _finding(
                file="src/main.py",
                pattern="perf-001",
                description="SQL injection vulnerability",
            ),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 2

    def test_low_similarity_not_merged(self) -> None:
        """Findings with low similarity should stay separate."""
        pp = PostProcessor()
        findings = [
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="Missing input validation on user email",
            ),
            _finding(
                file="src/main.py",
                pattern="sec-001",
                description="Hardcoded database password in config",
            ),
        ]
        result = pp._deduplicate(findings)
        assert len(result) == 2


# ══════════════════════════════════════════════════════════════════════════════ #
#  Edge cases & integration
# ══════════════════════════════════════════════════════════════════════════════ #


class TestEdgeCases:
    """Edge cases and integration-style tests for the full pipeline."""

    def test_single_finding(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO)
        result = pp.process([_finding()])
        assert len(result) == 1

    def test_all_findings_filtered_by_severity(self) -> None:
        pp = PostProcessor(min_severity=Severity.CRITICAL)
        findings = [
            _finding(severity=Severity.MEDIUM),
            _finding(severity=Severity.LOW, title="low"),
        ]
        result = pp.process(findings)
        assert result == []

    def test_all_findings_filtered_by_confidence(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO, min_confidence=0.95)
        findings = [
            _finding(confidence=0.5),
            _finding(confidence=0.7, title="medium-conf"),
        ]
        result = pp.process(findings)
        assert result == []

    def test_dedup_then_filter_then_sort(self) -> None:
        """Integration: dedup removes dups, filter removes low-sev, sort orders."""
        pp = PostProcessor(min_severity=Severity.MEDIUM, min_confidence=0.6)
        findings = [
            _finding(
                severity=Severity.LOW,
                confidence=0.9,
                title="low-sev",
                description="This is a low severity issue",
            ),
            _finding(
                severity=Severity.HIGH,
                confidence=0.8,
                title="high-a",
                description="Important security issue found",
            ),
            _finding(
                severity=Severity.HIGH,
                confidence=0.9,
                title="high-dup",
                description="Important security issue found",  # duplicate
            ),
            _finding(
                severity=Severity.CRITICAL,
                confidence=0.95,
                title="critical",
                description="Critical vulnerability detected",
            ),
        ]
        result = pp.process(findings)
        # low-sev filtered out, one high-dup merged, critical first
        assert result[0].severity == Severity.CRITICAL
        assert all(f.severity >= Severity.MEDIUM for f in result)

    def test_process_immutability(self) -> None:
        """process() must not mutate the input list."""
        pp = PostProcessor(min_severity=Severity.INFO)
        original = [_finding(), _finding(title="second")]
        original_copy = list(original)
        pp.process(original)
        assert original == original_copy

    def test_max_findings_zero_returns_empty(self) -> None:
        pp = PostProcessor(min_severity=Severity.INFO, max_findings=0)
        result = pp.process([_finding()])
        assert result == []

    def test_confidence_at_boundary(self) -> None:
        """Confidence exactly at threshold should be included."""
        pp = PostProcessor(min_severity=Severity.INFO, min_confidence=0.7)
        result = pp.process([_finding(confidence=0.7)])
        assert len(result) == 1

    def test_severity_at_boundary(self) -> None:
        """Severity exactly at threshold should be included."""
        pp = PostProcessor(min_severity=Severity.MEDIUM)
        result = pp.process([_finding(severity=Severity.MEDIUM)])
        assert len(result) == 1
