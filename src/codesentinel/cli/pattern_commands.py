"""CLI commands for pattern management (STORY-CS-015)."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.patterns.schema import Pattern
from codesentinel.patterns.validator import validate_pattern, validate_pattern_data

console = Console()

patterns_app = typer.Typer(
    name="patterns",
    help="Manage and inspect architectural patterns.",
    no_args_is_help=True,
)

_EXAMPLE_PATTERN_YAML = """\
apiVersion: v1
kind: Pattern
metadata:
  name: example-custom-pattern
  category: architecture
  severity: medium
  tags:
    - custom
  confidence_threshold: 0.7
spec:
  description: >
    Describe what this pattern checks for.
  rationale: >
    Explain why this pattern matters.
  applies_to:
    include:
      - "**/*.py"
    exclude:
      - "**/test/**"
  detection:
    positive_signals:
      - "signal that indicates a violation"
    negative_signals:
      - "signal that indicates compliance"
  examples:
    correct:
      - description: "Good example"
        code: |
          # correct code here
    incorrect:
      - description: "Bad example"
        code: |
          # incorrect code here
  remediation: >
    Describe how to fix violations of this pattern.
"""


def _load_all_patterns() -> list[Pattern]:
    """Load all builtin patterns."""
    loader = PatternLoader()
    return loader.load_builtin()


# --------------------------------------------------------------------------- #
# patterns list
# --------------------------------------------------------------------------- #


@patterns_app.command("list")
def list_patterns(
    language: str | None = typer.Option(None, "--language", "-l", help="Filter by language"),
    category: str | None = typer.Option(None, "--category", "-c", help="Filter by category"),
    severity: str | None = typer.Option(None, "--severity", "-s", help="Minimum severity to show"),
) -> None:
    """List all loaded patterns with name, category, language, and severity."""
    patterns = _load_all_patterns()
    registry = PatternRegistry(patterns)

    if language:
        patterns = registry.by_language(language)
    if category:
        patterns = [p for p in patterns if p.metadata.category.lower() == category.lower()]
    if severity:
        from codesentinel.core.enums import Severity

        try:
            min_sev = Severity(severity.lower())
        except ValueError:
            typer.echo(f"Error: Invalid severity '{severity}'", err=True)
            raise typer.Exit(code=1) from None
        patterns = [p for p in patterns if p.metadata.severity >= min_sev]

    if not patterns:
        typer.echo("No patterns found matching the given filters.")
        raise typer.Exit(code=0)

    table = Table(title="Loaded Patterns")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Category", style="green")
    table.add_column("Language", style="yellow")
    table.add_column("Severity", style="red")
    table.add_column("Tags")

    for p in sorted(patterns, key=lambda x: x.metadata.name):
        table.add_row(
            p.metadata.name,
            p.metadata.category,
            p.metadata.language or "general",
            p.metadata.severity.value,
            ", ".join(p.metadata.tags) if p.metadata.tags else "",
        )

    console.print(table)


# --------------------------------------------------------------------------- #
# patterns validate
# --------------------------------------------------------------------------- #


@patterns_app.command("validate")
def validate_pattern_file(
    path: str = typer.Argument(..., help="Path to a pattern YAML file"),
) -> None:
    """Validate a pattern YAML file against the schema."""
    file_path = Path(path)
    if not file_path.is_file():
        typer.echo(f"Error: File not found: {path}", err=True)
        raise typer.Exit(code=1)

    try:
        raw = file_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, yaml.YAMLError) as exc:
        typer.echo(f"Error: Cannot read file: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not isinstance(data, dict):
        typer.echo("Error: File does not contain a YAML mapping", err=True)
        raise typer.Exit(code=1)

    errors = validate_pattern_data(data)
    if errors:
        typer.echo("Validation errors:", err=True)
        for err in errors:
            typer.echo(f"  - {err}", err=True)
        raise typer.Exit(code=1)

    # Also run semantic warnings
    pattern = Pattern.model_validate(data)
    warnings = validate_pattern(pattern)

    if warnings:
        typer.echo("Pattern is valid with warnings:")
        for w in warnings:
            typer.echo(f"  - {w}")
    else:
        typer.echo("Pattern is valid. No errors or warnings found.")


# --------------------------------------------------------------------------- #
# patterns show
# --------------------------------------------------------------------------- #


@patterns_app.command("show")
def show_pattern(
    name: str = typer.Argument(..., help="Pattern name to display"),
) -> None:
    """Show full details of a specific pattern."""
    patterns = _load_all_patterns()
    found = [p for p in patterns if p.metadata.name == name]

    if not found:
        typer.echo(f"Error: Pattern '{name}' not found.", err=True)
        raise typer.Exit(code=1)

    pattern = found[0]
    meta = pattern.metadata
    spec = pattern.spec

    # Header
    console.print(Panel(f"[bold cyan]{meta.name}[/bold cyan]", title="Pattern Details"))

    # Metadata table
    meta_table = Table(show_header=False, box=None)
    meta_table.add_column("Field", style="bold")
    meta_table.add_column("Value")
    meta_table.add_row("Category", meta.category)
    meta_table.add_row("Language", meta.language or "general")
    meta_table.add_row("Severity", meta.severity.value)
    meta_table.add_row("Tags", ", ".join(meta.tags) if meta.tags else "none")
    meta_table.add_row("Confidence Threshold", str(meta.confidence_threshold))
    console.print(meta_table)

    # Description
    console.print(f"\n[bold]Description:[/bold]\n{spec.description}")

    if spec.rationale:
        console.print(f"\n[bold]Rationale:[/bold]\n{spec.rationale}")

    # Detection signals
    if spec.detection.positive_signals or spec.detection.negative_signals:
        console.print("\n[bold]Detection Signals:[/bold]")
        if spec.detection.positive_signals:
            console.print("  Positive:")
            for sig in spec.detection.positive_signals:
                console.print(f"    + {sig}")
        if spec.detection.negative_signals:
            console.print("  Negative:")
            for sig in spec.detection.negative_signals:
                console.print(f"    - {sig}")

    # Examples
    if spec.examples.correct or spec.examples.incorrect:
        console.print("\n[bold]Examples:[/bold]")
        for ex in spec.examples.correct:
            console.print(f"  [green]Correct:[/green] {ex.description}")
            console.print(f"    {ex.code.strip()}")
        for ex in spec.examples.incorrect:
            console.print(f"  [red]Incorrect:[/red] {ex.description}")
            console.print(f"    {ex.code.strip()}")

    if spec.remediation:
        console.print(f"\n[bold]Remediation:[/bold]\n{spec.remediation}")

    if spec.references:
        console.print("\n[bold]References:[/bold]")
        for ref in spec.references:
            console.print(f"  - {ref.title}: {ref.url}")


# --------------------------------------------------------------------------- #
# patterns init
# --------------------------------------------------------------------------- #


@patterns_app.command("init")
def init_patterns(
    path: str = typer.Option(".", "--path", "-p", help="Root directory for .codesentinel/"),
) -> None:
    """Create a starter .codesentinel/ directory with an example pattern."""
    root = Path(path)
    patterns_dir = root / ".codesentinel" / "patterns"

    if patterns_dir.exists():
        typer.echo(f"Patterns directory already exists at {patterns_dir}")
        return

    patterns_dir.mkdir(parents=True, exist_ok=True)
    example_file = patterns_dir / "example-custom-pattern.yaml"
    example_file.write_text(_EXAMPLE_PATTERN_YAML, encoding="utf-8")

    typer.echo(f"Created {patterns_dir} with example pattern.")
    typer.echo(f"Edit {example_file} to define your first custom pattern.")
