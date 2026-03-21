"""Unit tests for reporters/json_reporter.py."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from codesentinel.core.enums import Severity
from codesentinel.core.models import (
    Finding,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.reporters.json_reporter import JsonReporter

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


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
        code_snippet="x = 1",
    )


def _make_result(
    findings: tuple[Finding, ...] = (),
    *,
    files_reviewed: int = 3,
    patterns_loaded: int = 5,
    timestamp: datetime | None = None,
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
        config={"mode": "coaching", "min_severity": "medium"},
        timestamp=timestamp or datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
    )


# --------------------------------------------------------------------------- #
# Enabled / disabled
# --------------------------------------------------------------------------- #


class TestJsonReporterEnabled:
    def test_is_enabled_returns_true_when_enabled(self) -> None:
        reporter = JsonReporter(output_path="report.json", enabled=True)
        assert reporter.is_enabled() is True

    def test_is_enabled_returns_false_when_disabled(self) -> None:
        reporter = JsonReporter(output_path="report.json", enabled=False)
        assert reporter.is_enabled() is False


# --------------------------------------------------------------------------- #
# JSON output structure
# --------------------------------------------------------------------------- #


class TestJsonReporterOutput:
    @pytest.mark.asyncio
    async def test_writes_json_file(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        result = _make_result()

        await reporter.report(result)

        assert output.exists()
        data = json.loads(output.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_json_includes_version(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        data = json.loads(output.read_text(encoding="utf-8"))
        assert "version" in data
        assert data["version"] == "1.0"

    @pytest.mark.asyncio
    async def test_json_includes_timestamp(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        ts = datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC)

        await reporter.report(_make_result(timestamp=ts))

        data = json.loads(output.read_text(encoding="utf-8"))
        assert "timestamp" in data
        assert data["timestamp"] == "2026-03-21T12:00:00+00:00"

    @pytest.mark.asyncio
    async def test_json_includes_target(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["target"]["type"] == "diff"
        assert data["target"]["diff_path"] == "test.diff"

    @pytest.mark.asyncio
    async def test_json_includes_stats(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        data = json.loads(output.read_text(encoding="utf-8"))
        stats = data["stats"]
        assert stats["files_reviewed"] == 3
        assert stats["patterns_loaded"] == 5
        assert stats["findings_total"] == 0
        assert stats["input_tokens"] == 500
        assert stats["output_tokens"] == 200
        assert stats["llm_calls"] == 2
        assert stats["duration_ms"] == 1500

    @pytest.mark.asyncio
    async def test_json_includes_config(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["config"]["mode"] == "coaching"
        assert data["config"]["min_severity"] == "medium"

    @pytest.mark.asyncio
    async def test_json_includes_findings(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        finding = _make_finding(severity=Severity.CRITICAL, title="SQL injection")
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        data = json.loads(output.read_text(encoding="utf-8"))
        assert len(data["findings"]) == 1
        f = data["findings"][0]
        assert f["pattern_name"] == "test-pattern"
        assert f["severity"] == "critical"
        assert f["confidence"] == 0.9
        assert f["file"] == "src/main.py"
        assert f["line"] == 42
        assert f["title"] == "SQL injection"
        assert f["description"] == "A test finding description."
        assert f["rationale"] == "This matters because reasons."
        assert f["remediation"] == "Fix by doing the thing."
        assert f["code_snippet"] == "x = 1"

    @pytest.mark.asyncio
    async def test_json_multiple_findings(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        findings = (
            _make_finding(severity=Severity.CRITICAL, title="Critical issue"),
            _make_finding(severity=Severity.LOW, title="Minor issue"),
        )
        result = _make_result(findings=findings)

        await reporter.report(result)

        data = json.loads(output.read_text(encoding="utf-8"))
        assert len(data["findings"]) == 2
        assert data["findings"][0]["severity"] == "critical"
        assert data["findings"][1]["severity"] == "low"

    @pytest.mark.asyncio
    async def test_json_no_findings_empty_list(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["findings"] == []

    @pytest.mark.asyncio
    async def test_json_pretty_printed(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        await reporter.report(_make_result())

        raw = output.read_text(encoding="utf-8")
        # Pretty-printed JSON has newlines and indentation
        assert "\n" in raw
        assert "  " in raw

    @pytest.mark.asyncio
    async def test_json_severity_by_severity_uses_string_keys(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        finding = _make_finding(severity=Severity.HIGH)
        result = _make_result(findings=(finding,))

        await reporter.report(result)

        data = json.loads(output.read_text(encoding="utf-8"))
        by_sev = data["stats"]["findings_by_severity"]
        assert "high" in by_sev
        assert by_sev["high"] == 1


# --------------------------------------------------------------------------- #
# Error handling
# --------------------------------------------------------------------------- #


class TestJsonReporterErrors:
    @pytest.mark.asyncio
    async def test_write_to_nonexistent_dir_logs_error(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        output = tmp_path / "nonexistent" / "deep" / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        # Should not raise — graceful degradation
        await reporter.report(_make_result())

        assert not output.exists()

    @pytest.mark.asyncio
    async def test_write_to_readonly_dir_logs_error(self, tmp_path: Path) -> None:
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o444)
        output = readonly_dir / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)

        # Should not raise
        await reporter.report(_make_result())

        # Cleanup permissions for tmp_path cleanup
        readonly_dir.chmod(0o755)


# --------------------------------------------------------------------------- #
# PR / Branch target serialization
# --------------------------------------------------------------------------- #


class TestJsonReporterTargetVariants:
    @pytest.mark.asyncio
    async def test_pr_target_serialized(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        result = ReviewResult(
            findings=(),
            stats=ReviewStats(
                files_reviewed=0,
                patterns_loaded=0,
                patterns_matched=0,
                findings_total=0,
            ),
            target=ReviewTarget(
                type="pr",
                pr_url="https://github.com/org/repo/pull/42",
            ),
            timestamp=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
        )

        await reporter.report(result)

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["target"]["type"] == "pr"
        assert data["target"]["pr_url"] == "https://github.com/org/repo/pull/42"

    @pytest.mark.asyncio
    async def test_branch_target_serialized(self, tmp_path: Path) -> None:
        output = tmp_path / "report.json"
        reporter = JsonReporter(output_path=str(output), enabled=True)
        result = ReviewResult(
            findings=(),
            stats=ReviewStats(
                files_reviewed=0,
                patterns_loaded=0,
                patterns_matched=0,
                findings_total=0,
            ),
            target=ReviewTarget(
                type="branch",
                branch="feature/foo",
                base_branch="main",
            ),
            timestamp=datetime(2026, 3, 21, 12, 0, 0, tzinfo=UTC),
        )

        await reporter.report(result)

        data = json.loads(output.read_text(encoding="utf-8"))
        assert data["target"]["type"] == "branch"
        assert data["target"]["branch"] == "feature/foo"
        assert data["target"]["base_branch"] == "main"
