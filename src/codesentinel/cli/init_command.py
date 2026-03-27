"""CLI init command for project bootstrapping (STORY-CS-015)."""

from __future__ import annotations

from pathlib import Path

import typer
import yaml

_VALID_PROVIDERS = ("claude", "openai", "ollama")

_DEFAULT_API_KEY_VARS = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "ollama": "",
}

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


def init_project(
    path: str = typer.Option(".", "--path", "-p", help="Root directory for initialization"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Use defaults without prompting"
    ),
) -> None:
    """Initialize a CodeSentinel project with config and starter patterns."""
    root = Path(path)
    config_file = root / ".codesentinel.yaml"
    patterns_dir = root / ".codesentinel" / "patterns"

    # Check for existing config
    if config_file.exists():
        if non_interactive:
            typer.echo(f"Config already exists at {config_file}, overwriting.")
        else:
            typer.echo(f"Config already exists at {config_file}.")
            overwrite = typer.prompt("Overwrite? (y/n)", default="n")
            if overwrite.lower() != "y":
                typer.echo("Aborted.")
                raise typer.Exit(code=0)

    if non_interactive:
        provider = "claude"
        api_key_var = _DEFAULT_API_KEY_VARS["claude"]
        pattern_sources: list[str] = []
    else:
        # Interactive prompts
        provider = typer.prompt(
            "LLM provider (claude/openai/ollama)",
            default="claude",
        )
        if provider not in _VALID_PROVIDERS:
            typer.echo(f"Warning: Unknown provider '{provider}', using anyway.")

        default_key_var = _DEFAULT_API_KEY_VARS.get(provider, "")
        api_key_var = typer.prompt(
            "API key environment variable",
            default=default_key_var,
        )

        raw_sources = typer.prompt(
            "Additional pattern directories (comma-separated, empty for none)",
            default="",
        )
        pattern_sources = [s.strip() for s in raw_sources.split(",") if s.strip()]

    # Build config dict
    config_data: dict[str, object] = {
        "version": "1.0",
        "llm": {
            "provider": provider,
            "api_key_env": api_key_var,
        },
        "patterns": {
            "builtin": {"enabled": True},
            "local": [".codesentinel/patterns", *pattern_sources],
        },
        "review": {
            "mode": "coaching",
            "min_severity": "medium",
        },
    }

    # Write config file
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        yaml.dump(config_data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )

    # Create patterns directory with example
    patterns_dir.mkdir(parents=True, exist_ok=True)
    example_file = patterns_dir / "example-custom-pattern.yaml"
    if not example_file.exists():
        example_file.write_text(_EXAMPLE_PATTERN_YAML, encoding="utf-8")

    typer.echo(f"Created {config_file}")
    typer.echo(f"Created {patterns_dir} with example pattern.")
    typer.echo("Run 'codesentinel config show' to verify your configuration.")
