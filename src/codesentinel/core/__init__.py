"""Core components: data models, diff parsing, pattern matching, context building."""

from codesentinel.core.diff_parser import LANGUAGE_MAP, DiffParser
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
    "LANGUAGE_MAP",
    "ClassifiedFile",
    "CodeSentinelError",
    "ConfigError",
    "DiffHunk",
    "DiffParseError",
    "DiffParser",
    "DiffStats",
    "FileDiff",
    "FileStatus",
    "FileType",
    "Finding",
    "LLMError",
    "LLMResponse",
    "PRInfo",
    "ParsedDiff",
    "PatternError",
    "ReviewChunk",
    "ReviewResult",
    "ReviewStats",
    "ReviewTarget",
    "SCMError",
    "Severity",
]
