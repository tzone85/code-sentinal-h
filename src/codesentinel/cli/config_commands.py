"""CLI commands for configuration management (STORY-CS-015)."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from codesentinel.config.loader import load_config
from codesentinel.config.schema import CodeSentinelConfig
from codesentinel.core.exceptions import ConfigError

console = Console()

config_app = typer.Typer(
    name="config",
    help="Manage and inspect configuration.",
    no_args_is_help=True,
)


def _load_or_default(config_path: str) -> CodeSentinelConfig:
    """Load config from path, falling back to defaults if file missing."""
    try:
        return load_config(config_path)
    except ConfigError:
        return CodeSentinelConfig()


def _render_config_tree(config: CodeSentinelConfig) -> Tree:
    """Build a Rich Tree representation of the config."""
    data = config.model_dump()
    tree = Tree("[bold]CodeSentinel Configuration[/bold]")
    _add_dict_to_tree(tree, data)
    return tree


def _add_dict_to_tree(tree: Tree, data: dict[str, object], depth: int = 0) -> None:
    """Recursively add dict entries to a Rich Tree."""
    for key, value in data.items():
        if isinstance(value, dict):
            branch = tree.add(f"[bold cyan]{key}[/bold cyan]")
            _add_dict_to_tree(branch, value, depth + 1)
        elif isinstance(value, (list, tuple)):
            if not value:
                tree.add(f"[bold cyan]{key}:[/bold cyan] []")
            else:
                branch = tree.add(f"[bold cyan]{key}[/bold cyan]")
                for item in value:
                    if isinstance(item, dict):
                        sub = branch.add("")
                        _add_dict_to_tree(sub, item, depth + 1)
                    else:
                        branch.add(str(item))
        else:
            tree.add(f"[bold cyan]{key}:[/bold cyan] {value}")


# --------------------------------------------------------------------------- #
# config show
# --------------------------------------------------------------------------- #


@config_app.command("show")
def show_config(
    config: str = typer.Option(
        ".codesentinel.yaml", "--config", "-c", help="Config file path"
    ),
) -> None:
    """Show resolved configuration after merging all sources."""
    cfg = _load_or_default(config)
    tree = _render_config_tree(cfg)
    console.print(Panel(tree, title="Resolved Configuration"))


# --------------------------------------------------------------------------- #
# config validate
# --------------------------------------------------------------------------- #


@config_app.command("validate")
def validate_config(
    config: str = typer.Option(
        ".codesentinel.yaml", "--config", "-c", help="Config file path"
    ),
) -> None:
    """Validate configuration file and report any errors."""
    try:
        cfg = load_config(config)
        typer.echo("Configuration is valid.")
        typer.echo(f"  Version: {cfg.version}")
        typer.echo(f"  LLM Provider: {cfg.llm.provider}")
        typer.echo(f"  Review Mode: {cfg.review.mode}")
    except ConfigError as exc:
        typer.echo(f"Configuration validation failed:\n  {exc}", err=True)
        raise typer.Exit(code=1) from exc
