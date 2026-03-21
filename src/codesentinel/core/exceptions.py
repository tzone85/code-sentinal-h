"""Exception hierarchy for CodeSentinel."""


class CodeSentinelError(Exception):
    """Base exception for all CodeSentinel errors."""


class ConfigError(CodeSentinelError):
    """Raised when configuration is invalid or missing."""


class PatternError(CodeSentinelError):
    """Raised when a pattern fails to load or validate."""


class SCMError(CodeSentinelError):
    """Raised when a source control operation fails."""


class LLMError(CodeSentinelError):
    """Raised when an LLM provider call fails."""


class DiffParseError(CodeSentinelError):
    """Raised when a diff cannot be parsed."""
