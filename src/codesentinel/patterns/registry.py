"""In-memory pattern registry with filtering and querying."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

from codesentinel.core.enums import Severity
from codesentinel.patterns.schema import Pattern


def _glob_match(file_path: str, pattern: str) -> bool:
    """Match a file path against a glob pattern, supporting ``**``."""
    # Fast path: literal **/* means "any file at any depth"
    if pattern == "**/*":
        return True
    # Use PurePosixPath.match for patterns with **
    if "**" in pattern:
        return PurePosixPath(file_path).match(pattern)
    return fnmatch(file_path, pattern)


class PatternRegistry:
    """Queryable registry of loaded patterns."""

    def __init__(self, patterns: list[Pattern] | None = None) -> None:
        self._patterns: tuple[Pattern, ...] = tuple(patterns or [])

    def load(self, patterns: list[Pattern]) -> None:
        """Replace all registered patterns."""
        self._patterns = tuple(patterns)

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def all(self) -> list[Pattern]:
        """Return all registered patterns."""
        return list(self._patterns)

    def by_language(self, language: str) -> list[Pattern]:
        """Return patterns matching a specific language (or language-agnostic)."""
        lang_lower = language.lower()
        return [
            p
            for p in self._patterns
            if p.metadata.language is None or p.metadata.language.lower() == lang_lower
        ]

    def by_category(self, category: str) -> list[Pattern]:
        """Return patterns matching a specific category."""
        cat_lower = category.lower()
        return [p for p in self._patterns if p.metadata.category.lower() == cat_lower]

    def by_severity(self, min_severity: Severity) -> list[Pattern]:
        """Return patterns at or above a minimum severity level."""
        return [p for p in self._patterns if p.metadata.severity >= min_severity]

    def by_tags(self, tags: list[str]) -> list[Pattern]:
        """Return patterns that have at least one of the given tags."""
        tag_set = {t.lower() for t in tags}
        return [
            p
            for p in self._patterns
            if tag_set & {t.lower() for t in p.metadata.tags}
        ]

    def for_file(self, file_path: str, language: str | None = None) -> list[Pattern]:
        """Return patterns applicable to a specific file.

        A pattern matches if:
        1. file_path matches any applies_to.include glob
        2. file_path does NOT match any applies_to.exclude glob
        3. pattern language matches file language (or pattern is language-agnostic)
        """
        matched: list[Pattern] = []
        for pattern in self._patterns:
            applies = pattern.spec.applies_to

            # Check include globs
            included = any(_glob_match(file_path, glob) for glob in applies.include)
            if not included:
                continue

            # Check exclude globs
            excluded = any(_glob_match(file_path, glob) for glob in applies.exclude)
            if excluded:
                continue

            # Check language match
            if (
                pattern.metadata.language is not None
                and language is not None
                and pattern.metadata.language.lower() != language.lower()
            ):
                continue

            matched.append(pattern)
        return matched

    def stats(self) -> dict[str, object]:
        """Return summary statistics about registered patterns."""
        severity_counts: dict[str, int] = {}
        language_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}

        for p in self._patterns:
            sev = p.metadata.severity.value
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

            lang = p.metadata.language or "general"
            language_counts[lang] = language_counts.get(lang, 0) + 1

            cat = p.metadata.category
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "total": len(self._patterns),
            "by_severity": severity_counts,
            "by_language": language_counts,
            "by_category": category_counts,
        }
