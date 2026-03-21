"""Unit tests for action/entrypoint.py."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from action.entrypoint import (
    _build_pr_identifier,
    _determine_fail_on_severity,
    _get_input,
    _read_pr_number,
    _select_llm_provider,
    _set_github_output,
    main,
)

from codesentinel.core.enums import Severity

# ------------------------------------------------------------------ #
# _read_pr_number
# ------------------------------------------------------------------ #


class TestReadPRNumber:
    def test_reads_pr_number_from_event_payload(self, tmp_path: Path) -> None:
        event = {"pull_request": {"number": 42}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        assert _read_pr_number(str(event_path)) == 42

    def test_returns_none_when_no_pr_key(self, tmp_path: Path) -> None:
        event = {"push": {"ref": "refs/heads/main"}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        assert _read_pr_number(str(event_path)) is None

    def test_returns_none_when_file_missing(self) -> None:
        assert _read_pr_number("/nonexistent/path.json") is None

    def test_returns_none_when_invalid_json(self, tmp_path: Path) -> None:
        event_path = tmp_path / "event.json"
        event_path.write_text("not valid json")

        assert _read_pr_number(str(event_path)) is None


# ------------------------------------------------------------------ #
# _build_pr_identifier
# ------------------------------------------------------------------ #


class TestBuildPRIdentifier:
    def test_builds_identifier_from_repo_and_number(self) -> None:
        result = _build_pr_identifier("owner/repo", 42)
        assert result == "owner/repo#42"

    def test_returns_none_when_no_pr_number(self) -> None:
        assert _build_pr_identifier("owner/repo", None) is None

    def test_returns_none_when_no_repository(self) -> None:
        assert _build_pr_identifier("", 42) is None


# ------------------------------------------------------------------ #
# _select_llm_provider
# ------------------------------------------------------------------ #


class TestSelectLLMProvider:
    def test_selects_claude_when_anthropic_key_set(self) -> None:
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-key"}):
            provider = _select_llm_provider("claude")
            assert provider.name == "claude"

    def test_selects_openai_when_openai_key_set(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}):
            provider = _select_llm_provider("openai")
            assert provider.name == "openai"

    def test_raises_when_no_api_key(self) -> None:
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with patch.dict(os.environ, env, clear=True), pytest.raises(SystemExit):
            _select_llm_provider("claude")


# ------------------------------------------------------------------ #
# _determine_fail_on_severity
# ------------------------------------------------------------------ #


class TestDetermineFailOnSeverity:
    def test_valid_severity_string(self) -> None:
        assert _determine_fail_on_severity("critical") == Severity.CRITICAL
        assert _determine_fail_on_severity("high") == Severity.HIGH
        assert _determine_fail_on_severity("medium") == Severity.MEDIUM

    def test_defaults_to_critical_on_invalid(self) -> None:
        assert _determine_fail_on_severity("invalid") == Severity.CRITICAL


# ------------------------------------------------------------------ #
# _set_github_output
# ------------------------------------------------------------------ #


class TestSetGithubOutput:
    def test_writes_to_github_output_file(self, tmp_path: Path) -> None:
        output_file = tmp_path / "output.txt"
        with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output_file)}):
            _set_github_output("findings_count", "5")
            _set_github_output("critical_count", "1")

        content = output_file.read_text()
        assert "findings_count=5" in content
        assert "critical_count=1" in content

    def test_no_crash_when_github_output_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
        with patch.dict(os.environ, env, clear=True):
            _set_github_output("key", "value")  # should not raise


# ------------------------------------------------------------------ #
# main (integration-style unit tests with mocks)
# ------------------------------------------------------------------ #


class TestMain:
    def _setup_env(self, tmp_path: Path) -> dict[str, str]:
        """Set up minimal GitHub Action environment."""
        event = {"pull_request": {"number": 7}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        output_file = tmp_path / "github_output.txt"
        output_file.write_text("")

        return {
            "INPUT_ANTHROPIC_API_KEY": "sk-test-key",
            "INPUT_GITHUB_TOKEN": "ghp-test-token",
            "INPUT_CONFIG_PATH": ".codesentinel.yaml",
            "INPUT_MIN_SEVERITY": "medium",
            "INPUT_FAIL_ON": "critical",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output_file),
            "ANTHROPIC_API_KEY": "sk-test-key",
        }

    @pytest.mark.asyncio
    async def test_main_sets_outputs_on_success(self, tmp_path: Path) -> None:
        env = self._setup_env(tmp_path)

        mock_result = MagicMock()
        mock_result.findings = ()
        mock_result.stats.findings_total = 0
        mock_result.stats.findings_by_severity = {}

        mock_engine = MagicMock()
        mock_engine.review = AsyncMock(return_value=mock_result)
        mock_engine.compute_exit_code = MagicMock(return_value=0)

        with (
            patch.dict(os.environ, env, clear=False),
            patch("action.entrypoint._create_engine", return_value=mock_engine),
        ):
            exit_code = await main()

        assert exit_code == 0
        output_content = (tmp_path / "github_output.txt").read_text()
        assert "findings_count=0" in output_content

    @pytest.mark.asyncio
    async def test_main_returns_nonzero_when_findings_exceed_threshold(
        self, tmp_path: Path
    ) -> None:
        env = self._setup_env(tmp_path)

        mock_result = MagicMock()
        mock_result.findings = (MagicMock(severity=Severity.CRITICAL),)
        mock_result.stats.findings_total = 1
        mock_result.stats.findings_by_severity = {Severity.CRITICAL: 1}

        mock_engine = MagicMock()
        mock_engine.review = AsyncMock(return_value=mock_result)
        mock_engine.compute_exit_code = MagicMock(return_value=1)

        with (
            patch.dict(os.environ, env, clear=False),
            patch("action.entrypoint._create_engine", return_value=mock_engine),
        ):
            exit_code = await main()

        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_main_exits_when_no_pr(self, tmp_path: Path) -> None:
        event = {"push": {}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        output_file = tmp_path / "github_output.txt"
        output_file.write_text("")

        env = {
            "INPUT_ANTHROPIC_API_KEY": "sk-test-key",
            "INPUT_GITHUB_TOKEN": "ghp-test-token",
            "INPUT_CONFIG_PATH": ".codesentinel.yaml",
            "INPUT_MIN_SEVERITY": "medium",
            "INPUT_FAIL_ON": "critical",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output_file),
            "ANTHROPIC_API_KEY": "sk-test-key",
        }

        with patch.dict(os.environ, env, clear=False):
            exit_code = await main()

        # Should exit with error code when no PR detected
        assert exit_code == 2


# ------------------------------------------------------------------ #
# _get_input
# ------------------------------------------------------------------ #


class TestGetInput:
    def test_reads_input_from_env(self) -> None:
        with patch.dict(os.environ, {"INPUT_MY_KEY": "my_value"}):
            assert _get_input("my_key") == "my_value"

    def test_strips_whitespace(self) -> None:
        with patch.dict(os.environ, {"INPUT_MY_KEY": "  value  "}):
            assert _get_input("my_key") == "value"

    def test_returns_default_when_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "INPUT_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert _get_input("missing", "fallback") == "fallback"

    def test_returns_empty_string_by_default(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "INPUT_MISSING"}
        with patch.dict(os.environ, env, clear=True):
            assert _get_input("missing") == ""


# ------------------------------------------------------------------ #
# main — error paths
# ------------------------------------------------------------------ #


class TestMainErrorPaths:
    def _setup_env(self, tmp_path: Path) -> dict[str, str]:
        event = {"pull_request": {"number": 7}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        output_file = tmp_path / "github_output.txt"
        output_file.write_text("")

        return {
            "INPUT_ANTHROPIC_API_KEY": "sk-test-key",
            "INPUT_GITHUB_TOKEN": "ghp-test-token",
            "INPUT_CONFIG_PATH": ".codesentinel.yaml",
            "INPUT_MIN_SEVERITY": "medium",
            "INPUT_FAIL_ON": "critical",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output_file),
            "ANTHROPIC_API_KEY": "sk-test-key",
        }

    @pytest.mark.asyncio
    async def test_engine_creation_failure_returns_2(self, tmp_path: Path) -> None:
        env = self._setup_env(tmp_path)

        with (
            patch.dict(os.environ, env, clear=False),
            patch(
                "action.entrypoint._create_engine",
                side_effect=RuntimeError("config error"),
            ),
        ):
            exit_code = await main()

        assert exit_code == 2

    @pytest.mark.asyncio
    async def test_review_failure_returns_3(self, tmp_path: Path) -> None:
        env = self._setup_env(tmp_path)

        mock_engine = MagicMock()
        mock_engine.review = AsyncMock(side_effect=RuntimeError("LLM failed"))

        with (
            patch.dict(os.environ, env, clear=False),
            patch("action.entrypoint._create_engine", return_value=mock_engine),
        ):
            exit_code = await main()

        assert exit_code == 3

    @pytest.mark.asyncio
    async def test_openai_key_selects_openai_provider(self, tmp_path: Path) -> None:
        event = {"pull_request": {"number": 7}}
        event_path = tmp_path / "event.json"
        event_path.write_text(json.dumps(event))

        output_file = tmp_path / "github_output.txt"
        output_file.write_text("")

        env = {
            "INPUT_OPENAI_API_KEY": "sk-openai-test",
            "INPUT_ANTHROPIC_API_KEY": "",
            "INPUT_GITHUB_TOKEN": "ghp-test-token",
            "INPUT_CONFIG_PATH": ".codesentinel.yaml",
            "INPUT_MIN_SEVERITY": "medium",
            "INPUT_FAIL_ON": "critical",
            "GITHUB_EVENT_PATH": str(event_path),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_OUTPUT": str(output_file),
            "OPENAI_API_KEY": "sk-openai-test",
        }

        mock_result = MagicMock()
        mock_result.findings = ()
        mock_result.stats.findings_total = 0
        mock_result.stats.findings_by_severity = {}

        mock_engine = MagicMock()
        mock_engine.review = AsyncMock(return_value=mock_result)
        mock_engine.compute_exit_code = MagicMock(return_value=0)

        with (
            patch.dict(os.environ, env, clear=False),
            patch("action.entrypoint._create_engine", return_value=mock_engine),
        ):
            exit_code = await main()

        assert exit_code == 0
