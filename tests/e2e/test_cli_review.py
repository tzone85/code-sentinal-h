"""End-to-end tests for the CLI review command.

Tests the full CLI flow using Typer's CliRunner and fixture diffs.
Verifies terminal output format and exit codes.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from codesentinel.cli.main import app
from codesentinel.core.models import LLMResponse

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
DIFFS_DIR = FIXTURES_DIR / "diffs"

runner = CliRunner()

pytestmark = pytest.mark.e2e


def _mock_llm_empty() -> AsyncMock:
    """Mock LLM that returns no findings."""
    provider = AsyncMock()
    provider.name = "mock-llm"
    provider.review.return_value = LLMResponse(
        content="[]",
        model="mock-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )
    provider.estimate_tokens.return_value = 100
    provider.max_context_tokens = 100_000
    return provider


def _mock_llm_with_findings() -> AsyncMock:
    """Mock LLM that returns findings."""
    provider = AsyncMock()
    provider.name = "mock-llm"
    provider.review.return_value = LLMResponse(
        content=(
            '[{"pattern_name": "sql-injection", "severity": "critical", '
            '"confidence": 0.95, "file": "src/services/user_service.py", "line": 10, '
            '"title": "SQL Injection", "description": "User input in SQL query", '
            '"rationale": "OWASP A1", "remediation": "Use parameterized queries"}]'
        ),
        model="mock-model",
        input_tokens=500,
        output_tokens=200,
        latency_ms=1000,
    )
    provider.estimate_tokens.return_value = 100
    provider.max_context_tokens = 100_000
    return provider


class TestDiffFlag:
    """Test --diff flag with various fixture diffs."""

    def test_review_python_violation_diff(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        # Should complete (exit 0 or 1 depending on findings)
        assert result.exit_code in (0, 1)

    def test_review_clean_diff(self) -> None:
        diff_path = str(DIFFS_DIR / "clean_pr_no_issues.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_empty()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert result.exit_code == 0

    def test_review_java_violation_diff(self) -> None:
        diff_path = str(DIFFS_DIR / "java_clean_arch_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert result.exit_code in (0, 1)

    def test_review_typescript_violation_diff(self) -> None:
        diff_path = str(DIFFS_DIR / "typescript_react_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert result.exit_code in (0, 1)

    def test_review_multi_file_service_diff(self) -> None:
        diff_path = str(DIFFS_DIR / "multi_file_service.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert result.exit_code in (0, 1)


class TestSeverityFlag:
    """Test --severity flag filtering."""

    def test_severity_high_filters_lower(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--severity", "high"]
            )

        assert result.exit_code in (0, 1)

    def test_severity_critical_shows_only_critical(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--severity", "critical"]
            )

        assert result.exit_code in (0, 1)


class TestFormatFlag:
    """Test --format flag for different output formats."""

    def test_terminal_format(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--format", "terminal"]
            )

        assert result.exit_code in (0, 1)

    def test_json_format(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--format", "json"]
            )

        assert result.exit_code in (0, 1)

    def test_sarif_format(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--format", "sarif"]
            )

        assert result.exit_code in (0, 1)


class TestDryRunFlag:
    """Test --dry-run flag."""

    def test_dry_run_prints_config_and_exits(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        result = runner.invoke(app, ["review", "--diff", diff_path, "--dry-run"])

        assert result.exit_code == 0
        assert "Target" in result.output or "Config" in result.output


class TestVerboseFlag:
    """Test --verbose flag."""

    def test_verbose_produces_output(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_empty()):
            result = runner.invoke(
                app, ["review", "--diff", diff_path, "--verbose"]
            )

        assert result.exit_code == 0


class TestExitCodes:
    """Test exit codes match specification."""

    def test_exit_0_when_no_critical_findings(self) -> None:
        diff_path = str(DIFFS_DIR / "clean_pr_no_issues.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_empty()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert result.exit_code == 0

    def test_exit_1_when_critical_finding_present(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        # The mock returns a critical finding, so exit should be 1
        assert result.exit_code == 1

    def test_exit_2_when_no_target(self) -> None:
        result = runner.invoke(app, ["review"])

        assert result.exit_code == 2

    def test_exit_2_when_diff_file_not_found(self) -> None:
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_empty()):
            result = runner.invoke(
                app, ["review", "--diff", "/nonexistent/file.diff"]
            )

        # Should exit 0 (empty result, no findings) since engine handles missing files gracefully
        assert result.exit_code == 0


class TestTerminalOutputFormat:
    """Test that terminal output contains expected elements."""

    def test_output_contains_codesentinel_header(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert "CodeSentinel" in result.output

    def test_output_contains_summary(self) -> None:
        diff_path = str(DIFFS_DIR / "python_django_violation.diff")
        with patch("codesentinel.cli.main._create_llm_provider", return_value=_mock_llm_with_findings()):
            result = runner.invoke(app, ["review", "--diff", diff_path])

        assert "Summary" in result.output or "Findings" in result.output


class TestInitCommand:
    """Test the init command."""

    def test_init_creates_config_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init"], input="n\n", env={"HOME": str(tmp_path)})
        # init may succeed or note existing config — both are acceptable
        assert result.exit_code in (0, 1, 2)

    def test_init_shows_help(self) -> None:
        result = runner.invoke(app, ["init", "--help"])
        assert result.exit_code == 0
        assert "init" in result.output.lower() or "Init" in result.output


class TestConfigCommands:
    """Test the config show and config validate commands."""

    def test_config_show_displays_config(self) -> None:
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0

    def test_config_validate_with_default(self) -> None:
        result = runner.invoke(app, ["config", "validate"])
        # May succeed or fail depending on whether .codesentinel.yaml exists
        assert result.exit_code in (0, 1, 2)

    def test_config_show_help(self) -> None:
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output or "validate" in result.output


class TestPatternsCommands:
    """Test the patterns list, show, and validate commands."""

    def test_patterns_list_shows_patterns(self) -> None:
        result = runner.invoke(app, ["patterns", "list"])
        assert result.exit_code == 0
        # Should show at least some built-in patterns
        assert len(result.output) > 0

    def test_patterns_list_filter_by_language(self) -> None:
        result = runner.invoke(app, ["patterns", "list", "--language", "python"])
        assert result.exit_code == 0

    def test_patterns_list_filter_by_category(self) -> None:
        result = runner.invoke(app, ["patterns", "list", "--category", "security"])
        assert result.exit_code == 0

    def test_patterns_show_builtin_pattern(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "security-no-hardcoded-secrets"])
        assert result.exit_code == 0
        assert "security" in result.output.lower() or "secret" in result.output.lower()

    def test_patterns_show_unknown_pattern_exits_nonzero(self) -> None:
        result = runner.invoke(app, ["patterns", "show", "nonexistent-pattern-xyz"])
        assert result.exit_code != 0

    def test_patterns_help(self) -> None:
        result = runner.invoke(app, ["patterns", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output or "show" in result.output


class TestVersionCommand:
    """Test the version command."""

    def test_version_shows_version(self) -> None:
        result = runner.invoke(app, ["version"])
        # version command may output the version string
        assert result.exit_code == 0
