"""Unit tests for core/context_builder.py."""

from __future__ import annotations

import pytest

from codesentinel.core.context_builder import ContextBuilder
from codesentinel.core.enums import FileStatus, FileType, Severity
from codesentinel.core.models import ClassifiedFile, DiffHunk, FileDiff
from codesentinel.patterns.schema import (
    Pattern,
    PatternMetadata,
    PatternSpec,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

_HUNK_CONTENT = "+" + "x" * 200  # ~50 tokens


def _make_classified(
    path: str,
    *,
    language: str | None = "python",
    module: str | None = None,
    hunk_content: str = _HUNK_CONTENT,
) -> ClassifiedFile:
    """Create a ClassifiedFile with a single hunk."""
    hunk = DiffHunk(
        old_start=1,
        old_count=0,
        new_start=1,
        new_count=1,
        content=hunk_content,
        added_lines=(hunk_content,),
    )
    return ClassifiedFile(
        diff=FileDiff(
            path=path,
            old_path=None,
            status=FileStatus.MODIFIED,
            hunks=(hunk,),
            language=language,
        ),
        language=language,
        file_type=FileType.SOURCE,
        module=module,
    )


def _make_pattern(
    name: str,
    *,
    severity: Severity = Severity.MEDIUM,
) -> Pattern:
    return Pattern(
        metadata=PatternMetadata(name=name, category="general", severity=severity),
        spec=PatternSpec(description=f"Pattern {name}"),
    )


def _big_file(path: str, *, module: str | None = None, chars: int = 40_000) -> ClassifiedFile:
    """Create a file whose hunk is approximately *chars* characters (~chars//4 tokens)."""
    content = "+" + "A" * (chars - 1)
    return _make_classified(path, module=module, hunk_content=content)


@pytest.fixture()
def builder() -> ContextBuilder:
    return ContextBuilder(max_tokens=100_000)


# --------------------------------------------------------------------------- #
# Token estimation
# --------------------------------------------------------------------------- #


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        b = ContextBuilder()
        assert b._estimate_tokens("") == 0

    def test_four_chars_is_one_token(self) -> None:
        b = ContextBuilder()
        assert b._estimate_tokens("abcd") == 1

    def test_approximation(self) -> None:
        b = ContextBuilder()
        assert b._estimate_tokens("a" * 400) == 100


# --------------------------------------------------------------------------- #
# Basic chunking
# --------------------------------------------------------------------------- #


class TestBasicChunking:
    def test_single_file_single_chunk(self, builder: ContextBuilder) -> None:
        files = [_make_classified("src/main.py", module="src")]
        patterns: dict[str, list[Pattern]] = {
            "src/main.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        assert len(chunks) == 1
        assert len(chunks[0].files) == 1
        assert chunks[0].files[0].path == "src/main.py"

    def test_empty_files_returns_empty(self, builder: ContextBuilder) -> None:
        chunks = builder.build_chunks([], {})
        assert chunks == []

    def test_additional_context_included(self, builder: ContextBuilder) -> None:
        files = [_make_classified("src/main.py", module="src")]
        patterns: dict[str, list[Pattern]] = {"src/main.py": [_make_pattern("p1")]}
        chunks = builder.build_chunks(files, patterns, additional_context="Extra info")
        assert chunks[0].additional_context == "Extra info"


# --------------------------------------------------------------------------- #
# Module grouping
# --------------------------------------------------------------------------- #


class TestModuleGrouping:
    def test_same_module_grouped_together(self, builder: ContextBuilder) -> None:
        files = [
            _make_classified("src/auth/login.py", module="auth"),
            _make_classified("src/auth/logout.py", module="auth"),
        ]
        patterns: dict[str, list[Pattern]] = {
            "src/auth/login.py": [_make_pattern("p1")],
            "src/auth/logout.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        assert len(chunks) == 1
        assert len(chunks[0].files) == 2

    def test_different_modules_separate_chunks(self, builder: ContextBuilder) -> None:
        files = [
            _make_classified("src/auth/login.py", module="auth"),
            _make_classified("src/billing/invoice.py", module="billing"),
        ]
        patterns: dict[str, list[Pattern]] = {
            "src/auth/login.py": [_make_pattern("p1")],
            "src/billing/invoice.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        assert len(chunks) == 2

    def test_none_module_grouped_together(self, builder: ContextBuilder) -> None:
        files = [
            _make_classified("Makefile", module=None),
            _make_classified("README.md", module=None),
        ]
        patterns: dict[str, list[Pattern]] = {
            "Makefile": [_make_pattern("p1")],
            "README.md": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        # Files with no module are grouped into a single "ungrouped" bucket
        assert len(chunks) == 1


# --------------------------------------------------------------------------- #
# Token budget splitting
# --------------------------------------------------------------------------- #


class TestTokenBudgetSplitting:
    def test_group_within_budget_stays_single_chunk(self) -> None:
        builder = ContextBuilder(max_tokens=50_000)
        # Each file ~50 tokens, well within budget
        files = [
            _make_classified("src/auth/a.py", module="auth"),
            _make_classified("src/auth/b.py", module="auth"),
        ]
        patterns: dict[str, list[Pattern]] = {
            "src/auth/a.py": [_make_pattern("p1")],
            "src/auth/b.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        assert len(chunks) == 1

    def test_group_exceeding_budget_splits_by_file(self) -> None:
        # Budget = 5000 tokens = 20_000 chars. Each big file is ~10K tokens.
        builder = ContextBuilder(max_tokens=5_000)
        files = [
            _big_file("src/auth/big_a.py", module="auth", chars=40_000),
            _big_file("src/auth/big_b.py", module="auth", chars=40_000),
        ]
        patterns: dict[str, list[Pattern]] = {
            "src/auth/big_a.py": [_make_pattern("p1")],
            "src/auth/big_b.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        # Each file should be in its own chunk
        assert len(chunks) >= 2

    def test_single_file_never_split(self) -> None:
        # Even if a single file exceeds budget, it stays as one chunk
        builder = ContextBuilder(max_tokens=100)
        files = [_big_file("src/huge.py", module="src", chars=40_000)]
        patterns: dict[str, list[Pattern]] = {
            "src/huge.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        # Single file must never be split
        assert len(chunks) == 1
        assert len(chunks[0].files) == 1

    def test_estimated_tokens_populated(self, builder: ContextBuilder) -> None:
        files = [_make_classified("src/main.py", module="src")]
        patterns: dict[str, list[Pattern]] = {"src/main.py": [_make_pattern("p1")]}
        chunks = builder.build_chunks(files, patterns)
        assert chunks[0].estimated_tokens > 0


# --------------------------------------------------------------------------- #
# Pattern severity ordering and deduplication
# --------------------------------------------------------------------------- #


class TestPatternOrdering:
    def test_patterns_ordered_by_severity_critical_first(self, builder: ContextBuilder) -> None:
        files = [_make_classified("src/main.py", module="src")]
        p_low = _make_pattern("low-rule", severity=Severity.LOW)
        p_critical = _make_pattern("critical-rule", severity=Severity.CRITICAL)
        p_medium = _make_pattern("medium-rule", severity=Severity.MEDIUM)
        patterns: dict[str, list[Pattern]] = {
            "src/main.py": [p_low, p_critical, p_medium],
        }
        chunks = builder.build_chunks(files, patterns)
        chunk_patterns = chunks[0].patterns
        # Critical should come first
        assert chunk_patterns[0].metadata.severity == Severity.CRITICAL
        assert chunk_patterns[-1].metadata.severity == Severity.LOW

    def test_patterns_deduplicated_within_chunk(self, builder: ContextBuilder) -> None:
        files = [
            _make_classified("src/auth/a.py", module="auth"),
            _make_classified("src/auth/b.py", module="auth"),
        ]
        shared_pattern = _make_pattern("shared-rule")
        patterns: dict[str, list[Pattern]] = {
            "src/auth/a.py": [shared_pattern],
            "src/auth/b.py": [shared_pattern],
        }
        chunks = builder.build_chunks(files, patterns)
        assert len(chunks) == 1
        # Pattern should appear only once despite being matched to both files
        assert len(chunks[0].patterns) == 1


# --------------------------------------------------------------------------- #
# Files without matched patterns are excluded
# --------------------------------------------------------------------------- #


class TestNoMatchedFilesReturnsEmpty:
    def test_patterns_for_different_files_returns_empty(self, builder: ContextBuilder) -> None:
        """Files exist but none match the patterns dict → returns []."""
        files = [_make_classified("src/other.py", module="other")]
        # Patterns only reference a file that's not in the files list
        patterns: dict[str, list[Pattern]] = {
            "src/missing.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        assert chunks == []


class TestUnmatchedFiles:
    def test_files_without_patterns_excluded(self, builder: ContextBuilder) -> None:
        files = [
            _make_classified("src/auth/login.py", module="auth"),
            _make_classified("src/auth/util.py", module="auth"),
        ]
        # Only login.py has patterns
        patterns: dict[str, list[Pattern]] = {
            "src/auth/login.py": [_make_pattern("p1")],
        }
        chunks = builder.build_chunks(files, patterns)
        all_paths = [f.path for c in chunks for f in c.files]
        assert "src/auth/login.py" in all_paths
        assert "src/auth/util.py" not in all_paths
