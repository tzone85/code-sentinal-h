"""Configuration schema, defaults, and loader."""

from codesentinel.config.defaults import default_config
from codesentinel.config.loader import load_config
from codesentinel.config.schema import CodeSentinelConfig

__all__ = [
    "CodeSentinelConfig",
    "default_config",
    "load_config",
]
