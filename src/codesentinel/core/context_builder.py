"""Build LLM-ready review chunks from classified files and matched patterns.

Groups files by module, estimates token usage, and splits oversized groups
while guaranteeing that a single file is never split across chunks.
"""

from __future__ import annotations

from collections import defaultdict

from codesentinel.core.models import ClassifiedFile, FileDiff, ReviewChunk
from codesentinel.patterns.schema import Pattern

# Approximate overhead per chunk for system prompt and response buffer.
_OVERHEAD_TOKENS = 2_000


class ContextBuilder:
    """Assemble review chunks that fit within an LLM token budget."""

    def __init__(self, max_tokens: int = 100_000) -> None:
        self._max_tokens = max_tokens

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def build_chunks(
        self,
        files: list[ClassifiedFile],
        matched_patterns: dict[str, list[Pattern]],
        additional_context: str = "",
    ) -> list[ReviewChunk]:
        """Create review chunks from classified files and their matched patterns.

        Strategy:
        1. Keep only files that have at least one matched pattern.
        2. Group kept files by module (``None`` → shared bucket).
        3. Collect unique patterns per group, ordered by severity.
        4. Split groups that exceed the token budget by file.
        5. Never split a single file across chunks.
        """
        if not files:
            return []

        # 1. Filter to files with matched patterns
        relevant = [f for f in files if f.diff.path in matched_patterns]
        if not relevant:
            return []

        # 2. Group by module
        groups = self._group_by_module(relevant)

        # 3-5. Build chunks from each group
        chunks: list[ReviewChunk] = []
        for group_files in groups.values():
            group_chunks = self._build_group_chunks(
                group_files,
                matched_patterns,
                additional_context,
            )
            chunks.extend(group_chunks)

        return chunks

    # ------------------------------------------------------------------ #
    # Token estimation
    # ------------------------------------------------------------------ #

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Approximate token count at ~4 characters per token."""
        return len(text) // 4

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _group_by_module(
        files: list[ClassifiedFile],
    ) -> dict[str | None, list[ClassifiedFile]]:
        """Group files by their module field."""
        groups: dict[str | None, list[ClassifiedFile]] = defaultdict(list)
        for f in files:
            groups[f.module].append(f)
        return dict(groups)

    def _build_group_chunks(
        self,
        group_files: list[ClassifiedFile],
        matched_patterns: dict[str, list[Pattern]],
        additional_context: str,
    ) -> list[ReviewChunk]:
        """Build one or more chunks for a single module group.

        If the group fits within budget, return a single chunk.
        Otherwise, split by file — each file becomes its own chunk.
        """
        # Collect and deduplicate patterns for the group
        all_patterns = self._collect_patterns(group_files, matched_patterns)

        # Estimate total tokens for the whole group
        total_tokens = self._estimate_group_tokens(
            group_files, all_patterns, additional_context
        )

        if total_tokens <= self._max_tokens:
            return [
                self._make_chunk(
                    [f.diff for f in group_files],
                    all_patterns,
                    additional_context,
                    total_tokens,
                )
            ]

        # Split by file
        chunks: list[ReviewChunk] = []
        for classified in group_files:
            file_patterns = self._collect_patterns([classified], matched_patterns)
            tokens = self._estimate_group_tokens(
                [classified], file_patterns, additional_context
            )
            chunks.append(
                self._make_chunk(
                    [classified.diff],
                    file_patterns,
                    additional_context,
                    tokens,
                )
            )
        return chunks

    @staticmethod
    def _collect_patterns(
        files: list[ClassifiedFile],
        matched_patterns: dict[str, list[Pattern]],
    ) -> list[Pattern]:
        """Collect unique patterns for a set of files, ordered by severity (critical first)."""
        seen_names: set[str] = set()
        unique: list[Pattern] = []
        for f in files:
            for p in matched_patterns.get(f.diff.path, []):
                if p.metadata.name not in seen_names:
                    seen_names.add(p.metadata.name)
                    unique.append(p)

        return sorted(unique, key=lambda p: p.metadata.severity.weight, reverse=True)

    def _estimate_group_tokens(
        self,
        files: list[ClassifiedFile],
        patterns: list[Pattern],
        additional_context: str,
    ) -> int:
        """Estimate total tokens for a chunk: diffs + patterns + context + overhead."""
        diff_text = "\n".join(
            hunk.content for f in files for hunk in f.diff.hunks
        )
        pattern_text = "\n".join(p.spec.description for p in patterns)
        total_text = diff_text + pattern_text + additional_context
        return self._estimate_tokens(total_text) + _OVERHEAD_TOKENS

    @staticmethod
    def _make_chunk(
        file_diffs: list[FileDiff],
        patterns: list[Pattern],
        additional_context: str,
        estimated_tokens: int,
    ) -> ReviewChunk:
        """Construct an immutable ReviewChunk."""
        return ReviewChunk(
            files=tuple(file_diffs),
            patterns=tuple(patterns),
            additional_context=additional_context,
            estimated_tokens=estimated_tokens,
        )
