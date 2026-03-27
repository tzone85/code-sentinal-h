"""Core data models for CodeSentinel.

All models are frozen dataclasses to enforce immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from codesentinel.core.enums import FileStatus, FileType, Severity

if TYPE_CHECKING:
    from codesentinel.patterns.schema import Pattern


# --------------------------------------------------------------------------- #
# Diff models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DiffHunk:
    """A single hunk within a file diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    content: str
    added_lines: tuple[str, ...] = ()
    removed_lines: tuple[str, ...] = ()
    context_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileDiff:
    """Diff information for a single file."""

    path: str
    old_path: str | None
    status: FileStatus
    hunks: tuple[DiffHunk, ...] = ()
    language: str | None = None
    is_binary: bool = False

    @property
    def added_line_count(self) -> int:
        return sum(len(h.added_lines) for h in self.hunks)

    @property
    def removed_line_count(self) -> int:
        return sum(len(h.removed_lines) for h in self.hunks)


@dataclass(frozen=True)
class DiffStats:
    """Aggregate statistics for a parsed diff."""

    files_changed: int
    additions: int
    deletions: int
    binary_files: int = 0


@dataclass(frozen=True)
class ParsedDiff:
    """Complete parsed diff containing all file diffs and stats."""

    files: tuple[FileDiff, ...]
    stats: DiffStats


# --------------------------------------------------------------------------- #
# SCM models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PRInfo:
    """Pull request / merge request metadata."""

    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    url: str
    diff_url: str


# --------------------------------------------------------------------------- #
# Review pipeline models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReviewTarget:
    """Describes what to review (PR, branch diff, or diff file)."""

    type: str
    pr_url: str | None = None
    branch: str | None = None
    base_branch: str | None = None
    diff_path: str | None = None
    repo_path: str | None = None


@dataclass(frozen=True)
class Finding:
    """A single review finding from the LLM."""

    pattern_name: str
    severity: Severity
    confidence: float
    file: str
    line: int
    title: str
    description: str
    rationale: str
    remediation: str
    code_snippet: str = ""


@dataclass(frozen=True)
class ReviewStats:
    """Statistics for a completed review."""

    files_reviewed: int
    patterns_loaded: int
    patterns_matched: int
    findings_total: int
    findings_by_severity: dict[Severity, int] = field(
        default_factory=dict,
    )
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    duration_ms: int = 0


@dataclass(frozen=True)
class ReviewResult:
    """Complete result of a review run."""

    findings: tuple[Finding, ...]
    stats: ReviewStats
    target: ReviewTarget
    config: dict[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


# --------------------------------------------------------------------------- #
# LLM models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LLMResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class ReviewChunk:
    """A chunk of review context to send to the LLM."""

    files: tuple[FileDiff, ...]
    patterns: tuple[Pattern, ...] = ()
    additional_context: str = ""
    estimated_tokens: int = 0


# --------------------------------------------------------------------------- #
# Classification models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ClassifiedFile:
    """A file diff enriched with classification metadata."""

    diff: FileDiff
    language: str | None
    file_type: FileType
    module: str | None = None
    layer: str | None = None
    framework_hints: tuple[str, ...] = ()
