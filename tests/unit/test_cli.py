"""Unit tests for cli/main.py using Typer test runner."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from codesentinel.cli.main import app

runner = CliRunner()

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "diffs"


class TestVersionCommand:
    def test_version_prints_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "codesentinel" in result.output


class TestReviewCommandValidation:
    def test_no_target_exits_with_code_2(self) -> None:
        result = runner.invoke(app, ["review"])
        assert result.exit_code == 2
        assert "Provide --diff" in result.output

    def test_dry_run_exits_with_code_0(self) -> None:
        diff_path = str(FIXTURES_DIR / "clean_pr_no_issues.diff")
        result = runner.invoke(app, ["review", "--diff", diff_path, "--dry-run"])
        assert result.exit_code == 0
        assert "Target" in result.output

    def test_missing_diff_file_exits_gracefully(self) -> None:
        # Engine handles missing diff gracefully: logs warning, returns 0 findings
        result = runner.invoke(app, ["review", "--diff", "/nonexistent/file.diff"])
        # Should not crash — exit 0 (no findings) or 2 (config) are both acceptable
        assert result.exit_code in (0, 2, 3)


class TestReviewTargetBuilding:
    def test_diff_target(self) -> None:
        result = runner.invoke(app, ["review", "--diff", "test.diff", "--dry-run"])
        assert result.exit_code == 0
        assert "diff" in result.output

    def test_branch_target(self) -> None:
        result = runner.invoke(
            app, ["review", "--branch", "feature/foo", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "branch" in result.output

    def test_pr_target(self) -> None:
        result = runner.invoke(
            app,
            ["review", "--pr", "https://github.com/org/repo/pull/1", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "pr" in result.output

    def test_staged_target(self) -> None:
        result = runner.invoke(app, ["review", "--staged", "--dry-run"])
        assert result.exit_code == 0
        assert "staged" in result.output
