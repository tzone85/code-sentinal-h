"""Unit tests for cli/main.py using Typer test runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from codesentinel.cli.main import (
    _build_config,
    _build_reporters,
    _build_scm_provider,
    _create_llm_provider,
    app,
)
from codesentinel.config.schema import CodeSentinelConfig
from codesentinel.reporters.json_reporter import JsonReporter
from codesentinel.reporters.terminal import TerminalReporter

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
        result = runner.invoke(app, ["review", "--branch", "feature/foo", "--dry-run"])
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


# --------------------------------------------------------------------------- #
# Reporter building (STORY-CS-021)
# --------------------------------------------------------------------------- #


class TestBuildReporters:
    def test_terminal_format_returns_terminal_reporter(self) -> None:
        reporters = _build_reporters(fmt="terminal", verbose=False, config=CodeSentinelConfig())
        assert len(reporters) == 1
        assert isinstance(reporters[0], TerminalReporter)

    def test_json_format_returns_json_reporter(self) -> None:
        reporters = _build_reporters(fmt="json", verbose=False, config=CodeSentinelConfig())
        assert any(isinstance(r, JsonReporter) for r in reporters)

    def test_json_format_includes_no_terminal(self) -> None:
        reporters = _build_reporters(fmt="json", verbose=False, config=CodeSentinelConfig())
        assert not any(isinstance(r, TerminalReporter) for r in reporters)

    def test_unknown_format_falls_back_to_terminal(self) -> None:
        reporters = _build_reporters(fmt="unknown", verbose=False, config=CodeSentinelConfig())
        assert len(reporters) == 1
        assert isinstance(reporters[0], TerminalReporter)

    def test_verbose_passed_to_terminal_reporter(self) -> None:
        reporters = _build_reporters(fmt="terminal", verbose=True, config=CodeSentinelConfig())
        assert len(reporters) == 1
        reporter = reporters[0]
        assert isinstance(reporter, TerminalReporter)
        assert reporter._verbose is True


# --------------------------------------------------------------------------- #
# Config building with config loader (STORY-CS-021)
# --------------------------------------------------------------------------- #


class TestBuildConfig:
    def test_returns_dict_with_severity(self) -> None:
        cs_config = CodeSentinelConfig()
        config = _build_config(severity="high", cs_config=cs_config)
        assert config["min_severity"] == "high"

    def test_returns_dict_with_defaults(self) -> None:
        cs_config = CodeSentinelConfig()
        config = _build_config(severity="medium", cs_config=cs_config)
        assert "mode" in config
        assert "fail_on" in config

    def test_fail_on_uses_config_severity(self) -> None:
        cs_config = CodeSentinelConfig()
        config = _build_config(severity="medium", cs_config=cs_config)
        assert config["fail_on"] == cs_config.review.min_severity

    def test_severity_override_applies(self) -> None:
        cs_config = CodeSentinelConfig()
        config = _build_config(severity="critical", cs_config=cs_config)
        assert config["min_severity"] == "critical"

    def test_additional_context_included(self, tmp_path: Path) -> None:
        ctx_file = tmp_path / "context.txt"
        ctx_file.write_text("extra context", encoding="utf-8")
        from codesentinel.config.schema import AdditionalContext, ReviewConfig
        review = ReviewConfig(additional_context=(AdditionalContext(path=str(ctx_file)),))
        cs_config = CodeSentinelConfig(review=review)
        config = _build_config(severity="medium", cs_config=cs_config)
        assert "extra context" in config["additional_context"]


# --------------------------------------------------------------------------- #
# SCM provider building (STORY-CS-021)
# --------------------------------------------------------------------------- #


class TestBuildSCMProvider:
    def test_diff_target_returns_none(self) -> None:
        provider = _build_scm_provider(target_type="diff", pr_url=None, repo_path=".")
        assert provider is None

    def test_branch_target_returns_local_git(self) -> None:
        from codesentinel.scm.local_git import LocalGitSCM

        provider = _build_scm_provider(target_type="branch", pr_url=None, repo_path=".")
        assert isinstance(provider, LocalGitSCM)

    def test_staged_target_returns_local_git(self) -> None:
        from codesentinel.scm.local_git import LocalGitSCM

        provider = _build_scm_provider(target_type="staged", pr_url=None, repo_path=".")
        assert isinstance(provider, LocalGitSCM)

    def test_pr_target_with_token_returns_github_scm(self) -> None:
        from codesentinel.scm.github import GitHubSCM

        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            provider = _build_scm_provider(
                target_type="pr",
                pr_url="https://github.com/org/repo/pull/1",
                repo_path=".",
            )
        assert isinstance(provider, GitHubSCM)

    def test_pr_target_without_token_returns_none(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            provider = _build_scm_provider(
                target_type="pr",
                pr_url="https://github.com/org/repo/pull/1",
                repo_path=".",
            )
        assert provider is None


# --------------------------------------------------------------------------- #
# LLM provider selection (STORY-CS-021)
# --------------------------------------------------------------------------- #


class TestCreateLLMProvider:
    def test_claude_provider_created(self) -> None:
        from codesentinel.llm.claude import ClaudeProvider

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            provider = _create_llm_provider(CodeSentinelConfig())
        assert isinstance(provider, ClaudeProvider)

    def test_openai_provider_created(self) -> None:
        from codesentinel.llm.openai_provider import OpenAIProvider

        config = CodeSentinelConfig(llm={"provider": "openai"})
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            provider = _create_llm_provider(config)
        assert isinstance(provider, OpenAIProvider)

    def test_ollama_provider_created(self) -> None:
        from codesentinel.llm.ollama import OllamaProvider

        config = CodeSentinelConfig(llm={"provider": "ollama"})
        provider = _create_llm_provider(config)
        assert isinstance(provider, OllamaProvider)
