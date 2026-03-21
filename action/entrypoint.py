"""GitHub Action entrypoint for CodeSentinel.

Reads inputs from GitHub Action environment variables, runs the review
engine against a pull request, and sets action outputs.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from codesentinel.config.loader import load_config
from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import Severity
from codesentinel.core.models import ReviewResult, ReviewTarget
from codesentinel.llm.base import LLMProvider
from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.reporters.terminal import TerminalReporter
from codesentinel.scm.github import GitHubSCM

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Input reading
# ------------------------------------------------------------------ #


def _get_input(name: str, default: str = "") -> str:
    """Read a GitHub Action input from the INPUT_* environment variable."""
    return os.environ.get(f"INPUT_{name.upper()}", default).strip()


def _read_pr_number(event_path: str) -> int | None:
    """Extract the PR number from the GitHub event JSON payload."""
    try:
        with open(event_path, encoding="utf-8") as f:
            event = json.load(f)
    except (OSError, json.JSONDecodeError, TypeError):
        logger.warning("Cannot read GitHub event file at %s", event_path)
        return None

    pr_data = event.get("pull_request")
    if not isinstance(pr_data, dict):
        return None
    number = pr_data.get("number")
    return int(number) if number is not None else None


def _build_pr_identifier(repository: str, pr_number: int | None) -> str | None:
    """Build a PR identifier string like 'owner/repo#123'."""
    if not repository or pr_number is None:
        return None
    return f"{repository}#{pr_number}"


# ------------------------------------------------------------------ #
# Provider selection
# ------------------------------------------------------------------ #


def _select_llm_provider(provider_name: str) -> LLMProvider:
    """Create the appropriate LLM provider based on config and available keys."""
    if provider_name == "openai" and os.environ.get("OPENAI_API_KEY"):
        from codesentinel.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()

    if os.environ.get("ANTHROPIC_API_KEY"):
        from codesentinel.llm.claude import ClaudeProvider

        return ClaudeProvider()

    if os.environ.get("OPENAI_API_KEY"):
        from codesentinel.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()

    print("::error::No LLM API key provided. Set anthropic_api_key or openai_api_key.")
    sys.exit(1)


# ------------------------------------------------------------------ #
# Severity / output helpers
# ------------------------------------------------------------------ #


def _determine_fail_on_severity(fail_on_str: str) -> Severity:
    """Convert a severity string to a Severity enum, defaulting to CRITICAL."""
    try:
        return Severity(fail_on_str.lower())
    except ValueError:
        logger.warning("Unknown fail_on value %r — defaulting to critical", fail_on_str)
        return Severity.CRITICAL


def _set_github_output(key: str, value: str) -> None:
    """Write a key=value pair to the GitHub Actions output file."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        logger.debug("GITHUB_OUTPUT not set — skipping output %s=%s", key, value)
        return
    try:
        with open(output_path, "a", encoding="utf-8") as f:
            f.write(f"{key}={value}\n")
    except OSError:
        logger.warning("Cannot write to GITHUB_OUTPUT at %s", output_path)


# ------------------------------------------------------------------ #
# Engine factory (seam for testing)
# ------------------------------------------------------------------ #


def _create_engine(
    *,
    config_path: str,
    llm_provider: LLMProvider,
    github_token: str,
    pr_identifier: str,
    min_severity: str,
    fail_on: str,
    patterns_repo: str,
    patterns_path: str,
) -> ReviewEngine:
    """Build a fully configured ReviewEngine."""
    config_obj = load_config(config_path)

    config_dict: dict[str, object] = {
        "mode": config_obj.review.mode,
        "min_severity": min_severity,
        "min_confidence": config_obj.review.min_confidence,
        "max_findings": config_obj.review.max_findings,
        "fail_on": fail_on,
    }

    # Load patterns
    loader = PatternLoader()
    patterns = loader.load_builtin()
    if patterns_repo:
        remote_patterns = loader.load_remote(
            repo=patterns_repo,
            path=patterns_path,
        )
        patterns = patterns + remote_patterns
    registry = PatternRegistry(patterns)

    # SCM and reporters
    scm = GitHubSCM(token=github_token)

    reporters: list[object] = [TerminalReporter(verbose=True)]

    if config_obj.reporters.github.enabled:
        from codesentinel.reporters.github_pr import GitHubPRReporter

        reporters.append(
            GitHubPRReporter(config=config_obj.reporters.github, scm=scm)
        )

    return ReviewEngine(
        config=config_dict,
        llm_provider=llm_provider,
        scm_provider=scm,
        pattern_registry=registry,
        reporters=reporters,
    )


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #


async def main() -> int:
    """Run the CodeSentinel review and return an exit code."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Read inputs
    anthropic_key = _get_input("anthropic_api_key")
    openai_key = _get_input("openai_api_key")
    github_token = _get_input("github_token")
    config_path = _get_input("config_path", ".codesentinel.yaml")
    patterns_repo = _get_input("patterns_repo")
    patterns_path = _get_input("patterns_path", "patterns")
    min_severity = _get_input("min_severity", "medium")
    fail_on = _get_input("fail_on", "critical")

    # Set API keys into environment for provider constructors
    if anthropic_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_key
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key

    # Read PR info from event payload
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    pr_number = _read_pr_number(event_path)
    pr_identifier = _build_pr_identifier(repository, pr_number)

    if not pr_identifier:
        print("::warning::No pull request detected — skipping review.")
        _set_github_output("findings_count", "0")
        _set_github_output("critical_count", "0")
        _set_github_output("report_path", "")
        return 2

    # Select LLM provider
    provider_name = "claude" if anthropic_key else "openai"
    llm_provider = _select_llm_provider(provider_name)

    # Create engine
    try:
        engine = _create_engine(
            config_path=config_path,
            llm_provider=llm_provider,
            github_token=github_token,
            pr_identifier=pr_identifier,
            min_severity=min_severity,
            fail_on=fail_on,
            patterns_repo=patterns_repo,
            patterns_path=patterns_path,
        )
    except Exception as exc:
        print(f"::error::Failed to initialize review engine: {exc}")
        return 2

    # Run review
    target = ReviewTarget(type="pr", pr_url=pr_identifier)
    try:
        result: ReviewResult = await engine.review(target)
    except Exception as exc:
        print(f"::error::Review failed: {exc}")
        return 3

    # Set outputs
    critical_count = result.stats.findings_by_severity.get(Severity.CRITICAL, 0)
    _set_github_output("findings_count", str(result.stats.findings_total))
    _set_github_output("critical_count", str(critical_count))
    _set_github_output("report_path", "")

    # Determine exit code
    exit_code = engine.compute_exit_code(result)

    if exit_code == 0:
        print(f"CodeSentinel: {result.stats.findings_total} finding(s), none at fail threshold.")
    else:
        print(
            f"::error::CodeSentinel: {result.stats.findings_total} finding(s), "
            f"{critical_count} critical. Review required."
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
