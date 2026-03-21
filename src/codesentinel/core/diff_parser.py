"""Regex-based parser for unified diff format.

Parses raw unified diff text into structured ParsedDiff objects,
handling Git extended diff headers, renames, binary files, mode changes,
and /dev/null paths for file additions/deletions.
"""

from __future__ import annotations

import re
from pathlib import Path

from codesentinel.core.enums import FileStatus
from codesentinel.core.exceptions import DiffParseError
from codesentinel.core.models import DiffHunk, DiffStats, FileDiff, ParsedDiff

# --------------------------------------------------------------------------- #
# Language detection map (Appendix A)
# --------------------------------------------------------------------------- #

LANGUAGE_MAP: dict[str, str] = {
    # Java / JVM
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".groovy": "groovy",
    ".gradle": "groovy",
    ".clj": "clojure",
    # Python
    ".py": "python",
    ".pyi": "python",
    ".pyx": "python",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".vue": "vue",
    ".svelte": "svelte",
    # Go
    ".go": "go",
    # Rust
    ".rs": "rust",
    # C / C++
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    # C#
    ".cs": "csharp",
    # Ruby
    ".rb": "ruby",
    ".erb": "ruby",
    ".rake": "ruby",
    ".gemspec": "ruby",
    # PHP
    ".php": "php",
    # Swift / Objective-C
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-c",
    # Shell
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".fish": "shell",
    # Config / Data
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "dotenv",
    ".properties": "properties",
    # Markup / Docs
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".tex": "latex",
    ".adoc": "asciidoc",
    # SQL
    ".sql": "sql",
    # Dart / Flutter
    ".dart": "dart",
    # Elixir / Erlang
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    # Haskell
    ".hs": "haskell",
    # Lua
    ".lua": "lua",
    # R
    ".r": "r",
    ".R": "r",
    # Perl
    ".pl": "perl",
    ".pm": "perl",
    # Docker / CI
    ".dockerfile": "dockerfile",
    # Protobuf
    ".proto": "protobuf",
    # GraphQL
    ".graphql": "graphql",
    ".gql": "graphql",
    # Terraform / HCL
    ".tf": "terraform",
    ".hcl": "hcl",
    # Nix
    ".nix": "nix",
    # Zig
    ".zig": "zig",
}

# --------------------------------------------------------------------------- #
# Regex patterns for diff parsing
# --------------------------------------------------------------------------- #

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")
_OLD_FILE_RE = re.compile(r"^--- (?:a/(.+)|(/dev/null))$")
_NEW_FILE_RE = re.compile(r"^\+\+\+ (?:b/(.+)|(/dev/null))$")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)
_RENAME_FROM_RE = re.compile(r"^rename from (.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (.+)$")
_BINARY_RE = re.compile(r"^Binary files .* differ$")
_OLD_MODE_RE = re.compile(r"^old mode \d+$")
_NEW_MODE_RE = re.compile(r"^new mode \d+$")
_SIMILARITY_RE = re.compile(r"^similarity index \d+%$")
_INDEX_RE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+")
_NEW_FILE_MODE_RE = re.compile(r"^new file mode \d+$")
_DELETED_FILE_MODE_RE = re.compile(r"^deleted file mode \d+$")


def _detect_language(path: str) -> str | None:
    """Detect language from file extension using LANGUAGE_MAP."""
    suffix = Path(path).suffix.lower()
    # Special case: Dockerfile has no extension
    if Path(path).name.lower() in ("dockerfile", "dockerfile.dev", "dockerfile.prod"):
        return "dockerfile"
    if Path(path).name.lower() == "makefile":
        return "makefile"
    return LANGUAGE_MAP.get(suffix)


def _parse_hunk_lines(
    lines: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Categorise hunk body lines into added, removed, and context."""
    added: list[str] = []
    removed: list[str] = []
    context: list[str] = []
    for line in lines:
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith(" "):
            context.append(line[1:])
        elif line.startswith("\\"):
            # "\ No newline at end of file" — metadata, skip
            continue
    return tuple(added), tuple(removed), tuple(context)


class DiffParser:
    """Parses unified diff text into structured ParsedDiff objects."""

    def parse(self, raw_diff: str) -> ParsedDiff:
        """Parse a raw unified diff string into a ParsedDiff.

        Args:
            raw_diff: The full unified diff text.

        Returns:
            A ParsedDiff containing all parsed file diffs and aggregate stats.

        Raises:
            DiffParseError: When the diff text is fundamentally malformed.
        """
        if not raw_diff or not raw_diff.strip():
            return ParsedDiff(
                files=(),
                stats=DiffStats(files_changed=0, additions=0, deletions=0),
            )

        lines = raw_diff.splitlines()
        file_diffs = self._parse_file_diffs(lines)
        stats = self._compute_stats(file_diffs)
        return ParsedDiff(files=tuple(file_diffs), stats=stats)

    def parse_file(self, path: str) -> ParsedDiff:
        """Parse a diff file from disk.

        Args:
            path: Path to a unified diff file.

        Returns:
            A ParsedDiff for the file contents.

        Raises:
            DiffParseError: When the file cannot be read or parsed.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise DiffParseError(f"Diff file not found: {path}")
        try:
            raw = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise DiffParseError(f"Cannot read diff file: {path}") from exc
        return self.parse(raw)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _parse_file_diffs(self, lines: list[str]) -> list[FileDiff]:
        """Split the diff into per-file sections and parse each one."""
        file_sections = self._split_into_file_sections(lines)
        return [self._parse_single_file(section) for section in file_sections]

    def _split_into_file_sections(self, lines: list[str]) -> list[list[str]]:
        """Split diff lines into sections, one per file."""
        sections: list[list[str]] = []
        current: list[str] = []

        for line in lines:
            if _DIFF_HEADER_RE.match(line):
                if current:
                    sections.append(current)
                current = [line]
            elif current:
                current.append(line)

        if current:
            sections.append(current)

        return sections

    def _parse_single_file(self, lines: list[str]) -> FileDiff:
        """Parse a single file section from the diff."""
        header_match = _DIFF_HEADER_RE.match(lines[0])
        if not header_match:
            raise DiffParseError(f"Invalid diff header: {lines[0]}")

        git_old_path = header_match.group(1)
        git_new_path = header_match.group(2)

        # Parse extended headers
        old_path: str | None = None
        new_path: str | None = None
        rename_from: str | None = None
        rename_to: str | None = None
        is_binary = False
        is_new_file = False
        is_deleted = False

        hunk_start_idx = len(lines)  # default: no hunks

        for i, line in enumerate(lines[1:], start=1):
            if _HUNK_HEADER_RE.match(line):
                hunk_start_idx = i
                break

            old_match = _OLD_FILE_RE.match(line)
            if old_match:
                old_path = old_match.group(1)  # None if /dev/null
                continue

            new_match = _NEW_FILE_RE.match(line)
            if new_match:
                new_path = new_match.group(1)  # None if /dev/null
                continue

            rename_from_match = _RENAME_FROM_RE.match(line)
            if rename_from_match:
                rename_from = rename_from_match.group(1)
                continue

            rename_to_match = _RENAME_TO_RE.match(line)
            if rename_to_match:
                rename_to = rename_to_match.group(1)
                continue

            if _BINARY_RE.match(line):
                is_binary = True
                continue

            if _NEW_FILE_MODE_RE.match(line):
                is_new_file = True
                continue

            if _DELETED_FILE_MODE_RE.match(line):
                is_deleted = True
                continue

            # Skip other extended headers (index, mode, similarity)
            if (
                _OLD_MODE_RE.match(line)
                or _NEW_MODE_RE.match(line)
                or _SIMILARITY_RE.match(line)
                or _INDEX_RE.match(line)
            ):
                continue

        # Determine file status and resolved paths
        status, resolved_path, resolved_old_path = self._resolve_file_info(
            git_old_path=git_old_path,
            git_new_path=git_new_path,
            old_path=old_path,
            new_path=new_path,
            rename_from=rename_from,
            rename_to=rename_to,
            is_new_file=is_new_file,
            is_deleted=is_deleted,
            is_binary=is_binary,
        )

        # Parse hunks
        hunks = self._parse_hunks(lines[hunk_start_idx:]) if hunk_start_idx < len(lines) else ()

        language = _detect_language(resolved_path) if not is_binary else None

        return FileDiff(
            path=resolved_path,
            old_path=resolved_old_path,
            status=status,
            hunks=hunks,
            language=language,
            is_binary=is_binary,
        )

    def _resolve_file_info(
        self,
        *,
        git_old_path: str,
        git_new_path: str,
        old_path: str | None,
        new_path: str | None,
        rename_from: str | None,
        rename_to: str | None,
        is_new_file: bool,
        is_deleted: bool,
        is_binary: bool,
    ) -> tuple[FileStatus, str, str | None]:
        """Determine file status, path, and old_path from parsed headers.

        Returns:
            (status, resolved_path, resolved_old_path)
        """
        # Rename detection
        if rename_from and rename_to:
            return FileStatus.RENAMED, rename_to, rename_from

        # File addition: old side is /dev/null
        if old_path is None and new_path is not None:
            return FileStatus.ADDED, new_path, None

        if is_new_file and not is_deleted:
            return FileStatus.ADDED, new_path or git_new_path, None

        # File deletion: new side is /dev/null
        if new_path is None and old_path is not None:
            return FileStatus.DELETED, old_path, None

        if is_deleted and not is_new_file:
            return FileStatus.DELETED, old_path or git_old_path, None

        # Binary file with no --- / +++ lines
        if is_binary and old_path is None and new_path is None:
            return FileStatus.MODIFIED, git_new_path, None

        # Normal modification
        resolved = new_path or git_new_path
        return FileStatus.MODIFIED, resolved, None

    def _parse_hunks(self, lines: list[str]) -> tuple[DiffHunk, ...]:
        """Parse all hunks from the remaining lines of a file section."""
        hunks: list[DiffHunk] = []
        current_header: re.Match[str] | None = None
        current_body: list[str] = []

        for line in lines:
            header_match = _HUNK_HEADER_RE.match(line)
            if header_match:
                if current_header is not None:
                    hunks.append(self._build_hunk(current_header, current_body))
                current_header = header_match
                current_body = []
            elif current_header is not None:
                current_body.append(line)

        # Finalize last hunk
        if current_header is not None:
            hunks.append(self._build_hunk(current_header, current_body))

        return tuple(hunks)

    @staticmethod
    def _build_hunk(header: re.Match[str], body_lines: list[str]) -> DiffHunk:
        """Construct a DiffHunk from a parsed header match and body lines."""
        old_start = int(header.group(1))
        old_count = int(header.group(2)) if header.group(2) is not None else 1
        new_start = int(header.group(3))
        new_count = int(header.group(4)) if header.group(4) is not None else 1

        added, removed, context = _parse_hunk_lines(body_lines)

        return DiffHunk(
            old_start=old_start,
            old_count=old_count,
            new_start=new_start,
            new_count=new_count,
            content="\n".join(body_lines),
            added_lines=added,
            removed_lines=removed,
            context_lines=context,
        )

    @staticmethod
    def _compute_stats(file_diffs: list[FileDiff]) -> DiffStats:
        """Compute aggregate stats from parsed file diffs."""
        additions = sum(f.added_line_count for f in file_diffs)
        deletions = sum(f.removed_line_count for f in file_diffs)
        binary_count = sum(1 for f in file_diffs if f.is_binary)
        return DiffStats(
            files_changed=len(file_diffs),
            additions=additions,
            deletions=deletions,
            binary_files=binary_count,
        )
