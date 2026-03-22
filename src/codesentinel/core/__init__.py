"""Core components: data models, diff parsing, pattern matching, context building."""

from codesentinel.core.context_builder import ContextBuilder
from codesentinel.core.diff_parser import LANGUAGE_MAP, DiffParser
from codesentinel.core.engine import ReviewEngine
from codesentinel.core.enums import FileStatus, FileType, Severity
from codesentinel.core.exceptions import (
    CodeSentinelError,
    ConfigError,
    DiffParseError,
    LLMError,
    PatternError,
    SCMError,
)
from codesentinel.core.file_classifier import FileClassifier
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
from codesentinel.core.pattern_matcher import PatternMatcher

__all__ = [
    "LANGUAGE_MAP",
    "ClassifiedFile",
    "CodeSentinelError",
    "ConfigError",
    "ContextBuilder",
    "DiffHunk",
    "DiffParseError",
    "DiffParser",
    "DiffStats",
    "FileClassifier",
    "FileDiff",
    "FileStatus",
    "FileType",
    "Finding",
    "LLMError",
    "LLMResponse",
    "PRInfo",
    "ParsedDiff",
    "PatternError",
    "PatternMatcher",
    "ReviewChunk",
    "ReviewEngine",
    "ReviewResult",
    "ReviewStats",
    "ReviewTarget",
    "SCMError",
    "Severity",
]
