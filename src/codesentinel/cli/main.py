"""CLI application for CodeSentinel using Typer."""

from __future__ import annotations

import asyncio
import logging

import typer

import codesentinel
from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import Severity
from codesentinel.core.exceptions import CodeSentinelError, ConfigError
from codesentinel.core.models import ReviewTarget
from codesentinel.llm.base import LLMProvider
from codesentinel.llm.claude import ClaudeProvider
from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.reporters.terminal import TerminalReporter

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="codesentinel",
    help="AI-powered code review tool that enforces architectural patterns.",
    no_args_is_help=True,
)

_SEVERITY_CHOICES = [s.value for s in Severity]
_FORMAT_CHOICES = ["terminal", "json", "sarif"]


# --------------------------------------------------------------------------- #
# review command
# --------------------------------------------------------------------------- #


@app.command()
def review(
    diff: str | None = typer.Option(None, "--diff", help="Path to a diff file"),
    branch: str | None = typer.Option(None, "--branch", help="Branch to diff"),
    base: str = typer.Option("main", "--base", help="Base branch for comparison"),
    pr: str | None = typer.Option(None, "--pr", help="Pull request URL"),
    staged: bool = typer.Option(False, "--staged", help="Review staged changes"),
    repo: str = typer.Option(".", "--repo", help="Repository path"),
    config_path: str = typer.Option(
        ".codesentinel.yaml", "--config", help="Config file path"
    ),
    severity: str = typer.Option(
        "medium", "--severity", help="Minimum severity to report"
    ),
    fmt: str = typer.Option("terminal", "--format", help="Output format"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show config without running"),
) -> None:
    """Review code changes against architectural patterns."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Build review target
    target = _build_target(
        diff=diff, branch=branch, base=base, pr=pr, staged=staged, repo=repo
    )
    if target is None:
        typer.echo(
            "Error: Provide --diff, --branch, --pr, or --staged.", err=True
        )
        raise typer.Exit(code=2)

    # Build config
    config = _build_config(severity=severity, config_path=config_path)

    if dry_run:
        typer.echo(f"Target: {target}")
        typer.echo(f"Config: {config}")
        raise typer.Exit(code=0)

    # Load patterns
    loader = PatternLoader()
    patterns = loader.load_builtin()
    registry = PatternRegistry(patterns)

    # Create LLM provider
    try:
        llm_provider: LLMProvider = ClaudeProvider()
    except ConfigError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    # Create reporters
    reporters = _build_reporters(fmt=fmt, verbose=verbose)

    # Create engine and run
    engine = ReviewEngine(
        config=config,
        llm_provider=llm_provider,
        scm_provider=None,
        pattern_registry=registry,
        reporters=reporters,
    )

    try:
        result = asyncio.run(engine.review(target))
    except CodeSentinelError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        typer.echo(f"Runtime error: {exc}", err=True)
        raise typer.Exit(code=3) from exc

    exit_code = engine.compute_exit_code(result)
    raise typer.Exit(code=exit_code)


# --------------------------------------------------------------------------- #
# version command
# --------------------------------------------------------------------------- #


@app.command()
def version() -> None:
    """Print CodeSentinel version and exit."""
    typer.echo(f"codesentinel {codesentinel.__version__}")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _build_target(
    *,
    diff: str | None,
    branch: str | None,
    base: str,
    pr: str | None,
    staged: bool,
    repo: str,
) -> ReviewTarget | None:
    """Build a ReviewTarget from CLI options."""
    if diff:
        return ReviewTarget(type="diff", diff_path=diff, repo_path=repo)
    if pr:
        return ReviewTarget(type="pr", pr_url=pr, repo_path=repo)
    if branch:
        return ReviewTarget(
            type="branch", branch=branch, base_branch=base, repo_path=repo
        )
    if staged:
        return ReviewTarget(type="staged", repo_path=repo, base_branch=base)
    return None


def _build_config(*, severity: str, config_path: str) -> dict[str, object]:
    """Build a configuration dict from CLI options and config file."""
    # TODO: load from .codesentinel.yaml via config loader (STORY-CS-013)
    return {
        "mode": "coaching",
        "min_severity": severity,
        "min_confidence": 0.7,
        "max_findings": 15,
        "fail_on": "critical",
    }


def _build_reporters(*, fmt: str, verbose: bool) -> list[object]:
    """Create the appropriate reporters based on output format."""
    if fmt == "terminal":
        return [TerminalReporter(verbose=verbose)]
    # TODO: JSON and SARIF reporters (STORY-CS-021, STORY-CS-023)
    return [TerminalReporter(verbose=verbose)]
