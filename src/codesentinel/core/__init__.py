"""Core components: data models, diff parsing, pattern matching, context building."""

from codesentinel.core.enums import FileStatus, FileType, Severity
from codesentinel.core.exceptions import (
    CodeSentinelError,
    ConfigError,
    DiffParseError,
    LLMError,
    PatternError,
    SCMError,
)
from codesentinel.core.models import (
    ClassifiedFile,
    DiffHunk,
    DiffStats,
    FileDiff,
    Finding,
    LLMResponse,
    ParsedDiff,
    PRInfo,
    ReviewChunk,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)

__all__ = [
    "ClassifiedFile",
    "CodeSentinelError",
    "ConfigError",
    "DiffHunk",
    "DiffParseError",
    "DiffStats",
    "FileDiff",
    "FileStatus",
    "FileType",
    "Finding",
    "LLMError",
    "LLMResponse",
    "ParsedDiff",
    "PRInfo",
    "PatternError",
    "ReviewChunk",
    "ReviewResult",
    "ReviewStats",
    "ReviewTarget",
    "SCMError",
    "Severity",
]
