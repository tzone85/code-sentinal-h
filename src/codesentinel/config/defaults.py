"""Built-in default configuration for CodeSentinel.

Every field default lives in the Pydantic schema itself.  This module
simply exposes a convenience factory so callers can write::

    cfg = default_config()

instead of importing the schema model directly.
"""

from __future__ import annotations

from codesentinel.config.schema import CodeSentinelConfig


def default_config() -> CodeSentinelConfig:
    """Return a fresh ``CodeSentinelConfig`` populated entirely from defaults."""
    return CodeSentinelConfig()
