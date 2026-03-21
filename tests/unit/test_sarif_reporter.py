"""Unit tests for reporters/sarif.py — SARIF v2.1.0 reporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.sarif import SarifReporter, _severity_to_sarif_level

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_SARIF_VERSION = "2.1.0"
_SARIF_SCHEMA = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/errata01/os/schemas/sarif-schema-2.1.0.json"


def _make_finding(
    *,
    severity: Severity = Severity.HIGH,
    title: str = "Test issue",
    pattern_name: str = "test-pattern",
    file: str = "src/main.py",
    line: int = 42,
    description: str = "A test finding description.",
    code_snippet: str = "",
) -> Finding:
    return Finding(
        pattern_name=pattern_name,
        severity=severity,
        confidence=0.9,
        file=file,
        line=line,
        title=title,
        description=description,
        rationale="This matters because reasons.",
        remediation="Fix by doing the thing.",
        code_snippet=code_snippet,
    )


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


# --------------------------------------------------------------------------- #
# Severity mapping
# --------------------------------------------------------------------------- #


class TestSeverityToSarifLevel:
    def test_critical_maps_to_error(self) -> None:
        assert _severity_to_sarif_level(Severity.CRITICAL) == "error"

    def test_high_maps_to_error(self) -> None:
        assert _severity_to_sarif_level(Severity.HIGH) == "error"

    def test_medium_maps_to_warning(self) -> None:
        assert _severity_to_sarif_level(Severity.MEDIUM) == "warning"

    def test_low_maps_to_note(self) -> None:
        assert _severity_to_sarif_level(Severity.LOW) == "note"

    def test_info_maps_to_note(self) -> None:
        assert _severity_to_sarif_level(Severity.INFO) == "note"


# --------------------------------------------------------------------------- #
# is_enabled
# --------------------------------------------------------------------------- #


class TestSarifReporterEnabled:
    def test_enabled_when_configured(self, tmp_path: Path) -> None:
        reporter = SarifReporter(output_path=str(tmp_path / "out.sarif"), enabled=True)
        assert reporter.is_enabled() is True

    def test_disabled_when_configured(self, tmp_path: Path) -> None:
        reporter = SarifReporter(output_path=str(tmp_path / "out.sarif"), enabled=False)
        assert reporter.is_enabled() is False


# --------------------------------------------------------------------------- #
# SARIF output structure
# --------------------------------------------------------------------------- #


class TestSarifStructure:
    @pytest.mark.asyncio
    async def test_sarif_version_and_schema(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result()

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        assert sarif["version"] == _SARIF_VERSION
        assert sarif["$schema"] == _SARIF_SCHEMA

    @pytest.mark.asyncio
    async def test_has_single_run(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result()

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        assert len(sarif["runs"]) == 1

    @pytest.mark.asyncio
    async def test_tool_driver_metadata(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result()

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "CodeSentinel"
        assert "version" in driver
        assert "informationUri" in driver


# --------------------------------------------------------------------------- #
# Rules generation
# --------------------------------------------------------------------------- #


class TestSarifRules:
    @pytest.mark.asyncio
    async def test_unique_rules_from_findings(self, tmp_path: Path) -> None:
        """Each unique pattern_name should produce exactly one rule."""
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        findings = (
            _make_finding(pattern_name="sql-injection", severity=Severity.CRITICAL),
            _make_finding(pattern_name="sql-injection", severity=Severity.HIGH),
            _make_finding(pattern_name="xss-prevention", severity=Severity.MEDIUM),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = [r["id"] for r in rules]
        assert sorted(rule_ids) == ["sql-injection", "xss-prevention"]

    @pytest.mark.asyncio
    async def test_rule_has_required_fields(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(pattern_name="clean-arch")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        rule = sarif["runs"][0]["tool"]["driver"]["rules"][0]
        assert rule["id"] == "clean-arch"
        assert "name" in rule
        assert "shortDescription" in rule
        assert rule["shortDescription"]["text"]

    @pytest.mark.asyncio
    async def test_empty_findings_produces_empty_rules(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result(findings=())

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert rules == []


# --------------------------------------------------------------------------- #
# Results generation
# --------------------------------------------------------------------------- #


class TestSarifResults:
    @pytest.mark.asyncio
    async def test_one_result_per_finding(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        findings = (
            _make_finding(severity=Severity.CRITICAL, title="Issue A"),
            _make_finding(severity=Severity.LOW, title="Issue B"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        results = sarif["runs"][0]["results"]
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_result_has_rule_id(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(pattern_name="no-god-class")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        sarif_result = sarif["runs"][0]["results"][0]
        assert sarif_result["ruleId"] == "no-god-class"

    @pytest.mark.asyncio
    async def test_result_has_message(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(title="Missing error handling")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        sarif_result = sarif["runs"][0]["results"][0]
        assert "Missing error handling" in sarif_result["message"]["text"]

    @pytest.mark.asyncio
    async def test_result_level_maps_severity(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        findings = (
            _make_finding(severity=Severity.CRITICAL, title="Crit"),
            _make_finding(severity=Severity.MEDIUM, title="Med"),
            _make_finding(severity=Severity.INFO, title="Info"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        results = sarif["runs"][0]["results"]
        levels = [r["level"] for r in results]
        assert levels == ["error", "warning", "note"]

    @pytest.mark.asyncio
    async def test_result_has_location(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(file="src/api/handler.py", line=99)
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        sarif_result = sarif["runs"][0]["results"][0]
        location = sarif_result["locations"][0]
        physical = location["physicalLocation"]
        assert physical["artifactLocation"]["uri"] == "src/api/handler.py"
        assert physical["region"]["startLine"] == 99

    @pytest.mark.asyncio
    async def test_empty_findings_produces_empty_results(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result(findings=())

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        results = sarif["runs"][0]["results"]
        assert results == []


# --------------------------------------------------------------------------- #
# File output
# --------------------------------------------------------------------------- #


class TestSarifFileOutput:
    @pytest.mark.asyncio
    async def test_writes_valid_json(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result(findings=(_make_finding(),))

        await reporter.report(result)

        content = Path(output_path).read_text()
        parsed = json.loads(content)
        assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "nested" / "dir" / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result()

        await reporter.report(result)

        assert Path(output_path).exists()

    @pytest.mark.asyncio
    async def test_output_is_formatted_json(self, tmp_path: Path) -> None:
        """SARIF output should be indented for readability."""
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        result = _make_result(findings=(_make_finding(),))

        await reporter.report(result)

        content = Path(output_path).read_text()
        assert "\n" in content  # not single-line
        re_parsed = json.dumps(json.loads(content), indent=2)
        assert content.strip() == re_parsed.strip()


# --------------------------------------------------------------------------- #
# Edge cases
# --------------------------------------------------------------------------- #


class TestSarifEdgeCases:
    @pytest.mark.asyncio
    async def test_finding_with_code_snippet(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(code_snippet="x = unsafe_func(user_input)")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        sarif_result = sarif["runs"][0]["results"][0]
        snippet = sarif_result["locations"][0]["physicalLocation"].get("region", {}).get("snippet", {}).get("text", "")
        assert snippet == "x = unsafe_func(user_input)"

    @pytest.mark.asyncio
    async def test_multiple_findings_same_file(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        findings = (
            _make_finding(file="src/app.py", line=10, title="Issue 1"),
            _make_finding(file="src/app.py", line=50, title="Issue 2"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        results = sarif["runs"][0]["results"]
        assert len(results) == 2
        lines = [r["locations"][0]["physicalLocation"]["region"]["startLine"] for r in results]
        assert lines == [10, 50]

    @pytest.mark.asyncio
    async def test_result_includes_description_in_message(self, tmp_path: Path) -> None:
        output_path = str(tmp_path / "report.sarif")
        reporter = SarifReporter(output_path=output_path)
        finding = _make_finding(
            title="Bad pattern",
            description="Detailed explanation of the issue.",
        )
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        sarif = json.loads(Path(output_path).read_text())
        message_text = sarif["runs"][0]["results"][0]["message"]["text"]
        assert "Bad pattern" in message_text
        assert "Detailed explanation of the issue." in message_text
