"""Configuration loader with 3-tier merge priority.

Loading priority (highest to lowest):
    1. Repository-level  ``.codesentinel.yaml``
    2. User-level        ``~/.config/codesentinel/config.yaml``
       (or ``CODESENTINEL_USER_CONFIG`` env-var override)
    3. Built-in defaults (defined in :mod:`codesentinel.config.schema`)

Values are **deep-merged** — a repo config that sets ``llm.provider``
keeps the user-level ``llm.temperature`` intact.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from codesentinel.config.schema import CodeSentinelConfig
from codesentinel.core.exceptions import ConfigError

logger = logging.getLogger(__name__)

_DEFAULT_USER_CONFIG = Path.home() / ".config" / "codesentinel" / "config.yaml"


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def load_config(path: str | Path) -> CodeSentinelConfig:
    """Load and merge configuration from all available sources.

    Args:
        path: Path to the repo-level config file (e.g. ``.codesentinel.yaml``).

    Returns:
        A fully validated, frozen :class:`CodeSentinelConfig`.

    Raises:
        ConfigError: On invalid YAML syntax or Pydantic validation failure.
    """
    merged: dict[str, Any] = {}

    # Layer 3 — built-in defaults are handled by Pydantic field defaults,
    # so the base dict starts empty.

    # Layer 2 — user config
    user_path = _resolve_user_config_path()
    user_data = _read_yaml(user_path, label="user")
    if user_data is not None:
        merged = merge_dicts(merged, user_data)

    # Layer 1 — repo config (highest priority)
    repo_data = _read_yaml(Path(path), label="repo")
    if repo_data is not None:
        merged = merge_dicts(merged, repo_data)

    return _validate(merged)


# --------------------------------------------------------------------------- #
# Deep merge
# --------------------------------------------------------------------------- #


def merge_dicts(
    base: dict[str, Any],
    override: dict[str, Any],
) -> dict[str, Any]:
    """Recursively merge *override* into *base* without mutating either.

    - Dict values are merged recursively.
    - Non-dict values in *override* replace the *base* value.
    - Keys present only in *base* are preserved.
    """
    result: dict[str, Any] = {}
    all_keys = set(base) | set(override)
    for key in all_keys:
        base_val = base.get(key)
        over_val = override.get(key)

        if key not in override:
            result[key] = _deep_copy_value(base_val)
        elif key not in base:
            result[key] = _deep_copy_value(over_val)
        elif isinstance(base_val, dict) and isinstance(over_val, dict):
            result[key] = merge_dicts(base_val, over_val)
        else:
            result[key] = _deep_copy_value(over_val)

    return result


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _deep_copy_value(val: Any) -> Any:
    """Return a shallow-safe copy of a value (deep-copy dicts)."""
    if isinstance(val, dict):
        return {k: _deep_copy_value(v) for k, v in val.items()}
    if isinstance(val, list):
        return list(val)
    return val


def _resolve_user_config_path() -> Path:
    """Determine the user-level config file path."""
    env_override = os.environ.get("CODESENTINEL_USER_CONFIG")
    if env_override:
        return Path(env_override)
    return _DEFAULT_USER_CONFIG


def _read_yaml(path: Path, *, label: str) -> dict[str, Any] | None:
    """Read a YAML file and return its contents as a dict, or None.

    Returns ``None`` when the file does not exist (graceful miss).

    Raises:
        ConfigError: When the file exists but contains invalid YAML or
            is not a mapping at the top level.
    """
    if not path.is_file():
        logger.info("No %s config file found at %s — skipping", label, path)
        return None

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read {label} config at {path}: {exc}") from exc

    if not raw.strip():
        logger.info("Empty %s config at %s — using defaults", label, path)
        return None

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {label} config at {path}: {exc}") from exc

    if data is None:
        return None

    if not isinstance(data, dict):
        raise ConfigError(f"{label.capitalize()} config at {path} must be a YAML mapping, got {type(data).__name__}")

    return data  # type: ignore[return-value]


def _validate(data: dict[str, Any]) -> CodeSentinelConfig:
    """Validate the merged dict through Pydantic."""
    try:
        return CodeSentinelConfig(**data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid configuration: {exc}") from exc
