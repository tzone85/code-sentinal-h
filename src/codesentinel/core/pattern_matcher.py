"""Match patterns to classified files based on glob, language, and category rules.

A pattern matches a file when all of these hold:
1. The file path matches at least one ``applies_to.include`` glob.
2. The file path does **not** match any ``applies_to.exclude`` glob.
3. The pattern language equals the file language, or is ``None`` (agnostic).
4. The pattern category is compatible with the file layer (if specified).
"""

from __future__ import annotations

import fnmatch

from codesentinel.core.models import ClassifiedFile
from codesentinel.patterns.schema import Pattern


def _path_matches_glob(path: str, glob: str) -> bool:
    """Check if *path* matches a single glob, handling ``**/`` prefix for root files.

    ``fnmatch`` requires a ``/`` character for patterns like ``**/*``, so
    root-level paths (``Makefile``) would not match.  When a glob starts
    with ``**/`` we also try the stripped suffix so that root files are
    covered.
    """
    if fnmatch.fnmatch(path, glob):
        return True
    if glob.startswith("**/"):
        return fnmatch.fnmatch(path, glob[3:])
    return False


def _path_matches_any(path: str, globs: tuple[str, ...]) -> bool:
    """Return True if *path* matches at least one glob pattern."""
    return any(_path_matches_glob(path, g) for g in globs)


def _language_matches(pattern_lang: str | None, file_lang: str | None) -> bool:
    """Return True when the pattern's language is compatible with the file's."""
    if pattern_lang is None:
        return True
    return pattern_lang == file_lang


class PatternMatcher:
    """Select which patterns apply to which files."""

    def match(
        self,
        files: list[ClassifiedFile],
        patterns: list[Pattern],
    ) -> dict[str, list[Pattern]]:
        """Return a mapping of file path → list of matched patterns.

        Files with zero matches are omitted from the result dict.
        """
        if not files or not patterns:
            return {}

        result: dict[str, list[Pattern]] = {}

        for classified in files:
            path = classified.diff.path
            matched = [
                p
                for p in patterns
                if self._pattern_applies(p, classified)
            ]
            if matched:
                result[path] = matched

        return result

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _pattern_applies(pattern: Pattern, classified: ClassifiedFile) -> bool:
        """Check all four matching criteria."""
        path = classified.diff.path
        applies = pattern.spec.applies_to

        # 1. Must match at least one include glob
        if not _path_matches_any(path, applies.include):
            return False

        # 2. Must not match any exclude glob
        if applies.exclude and _path_matches_any(path, applies.exclude):
            return False

        # 3. Language must be compatible
        return _language_matches(pattern.metadata.language, classified.language)
