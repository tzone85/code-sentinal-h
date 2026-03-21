"""Classify changed files by language, type, and architectural layer.

Enriches FileDiff objects with metadata used by the pattern matcher
to select relevant patterns for review.
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from codesentinel.core.diff_parser import LANGUAGE_MAP
from codesentinel.core.enums import FileType
from codesentinel.core.models import ClassifiedFile, FileDiff

# --------------------------------------------------------------------------- #
# File type classification patterns (Appendix B)
# --------------------------------------------------------------------------- #

FILE_TYPE_PATTERNS: dict[FileType, list[str]] = {
    FileType.TEST: [
        "**/test/**",
        "**/tests/**",
        "**/*_test.*",
        "**/*Test.*",
        "**/*.test.*",
        "**/*.spec.*",
    ],
    FileType.CONFIG: [
        "**/*.yaml",
        "**/*.yml",
        "**/*.json",
        "**/*.toml",
        "**/Dockerfile*",
        "**/docker-compose*",
    ],
    FileType.MIGRATION: [
        "**/migrations/**",
        "**/migrate/**",
        "**/flyway/**",
    ],
    FileType.DOCS: [
        "**/*.md",
        "**/*.rst",
        "**/docs/**",
    ],
    FileType.CI: [
        "**/.github/**",
        "**/.gitlab-ci*",
        "**/Jenkinsfile",
    ],
}

# --------------------------------------------------------------------------- #
# Architectural layer detection heuristics (Appendix C)
# --------------------------------------------------------------------------- #

LAYER_PATTERNS: dict[str, list[str]] = {
    "domain": [
        "**/domain/**",
        "**/model/**",
        "**/models/**",
        "**/entity/**",
        "**/aggregate/**",
        "**/event/**",
    ],
    "application": [
        "**/application/**",
        "**/service/**",
        "**/services/**",
        "**/usecase/**",
        "**/command/**",
        "**/handler/**",
    ],
    "infrastructure": [
        "**/infrastructure/**",
        "**/infra/**",
        "**/adapter/**",
        "**/persistence/**",
        "**/external/**",
    ],
    "presentation": [
        "**/controller/**",
        "**/api/**",
        "**/rest/**",
        "**/components/**",
        "**/pages/**",
        "**/views/**",
    ],
}

# --------------------------------------------------------------------------- #
# Framework detection heuristics
# --------------------------------------------------------------------------- #

_FRAMEWORK_PATH_HINTS: dict[str, list[str]] = {
    "spring-boot": [
        "**/src/main/java/**",
        "**/src/main/kotlin/**",
        "**/application.properties",
        "**/application.yml",
    ],
    "django": [
        "**/manage.py",
        "**/wsgi.py",
        "**/asgi.py",
        "**/urls.py",
        "**/admin.py",
        "**/apps.py",
    ],
    "fastapi": [
        "**/main.py",
        "**/routers/**",
        "**/dependencies.py",
    ],
    "react": [
        "**/components/**/*.tsx",
        "**/components/**/*.jsx",
        "**/*.tsx",
        "**/*.jsx",
    ],
    "nestjs": [
        "**/*.module.ts",
        "**/*.controller.ts",
        "**/*.service.ts",
    ],
    "nextjs": [
        "**/pages/**/*.tsx",
        "**/app/**/*.tsx",
        "**/next.config.*",
    ],
}


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Check if a path matches any of the given glob patterns."""
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _detect_language(path: str) -> str | None:
    """Detect programming language from file extension."""
    suffix = PurePosixPath(path).suffix.lower()
    return LANGUAGE_MAP.get(suffix)


def _detect_file_type(path: str) -> FileType:
    """Classify file type from path patterns. SOURCE is the default fallback."""
    for file_type, patterns in FILE_TYPE_PATTERNS.items():
        if _matches_any(path, patterns):
            return file_type
    return FileType.SOURCE


def _detect_layer(path: str) -> str | None:
    """Detect architectural layer from path conventions."""
    for layer, patterns in LAYER_PATTERNS.items():
        if _matches_any(path, patterns):
            return layer
    return None


def _detect_module(path: str) -> str | None:
    """Extract module/package name from path.

    Uses the first meaningful directory segment after common prefixes
    like src/, app/, lib/, etc.
    """
    parts = PurePosixPath(path).parts
    skip_prefixes = {"src", "main", "java", "kotlin", "python", "lib", "app", "pkg", "internal"}

    for i, part in enumerate(parts):
        if part in skip_prefixes:
            continue
        if part.startswith("."):
            continue
        # Skip the filename itself
        if i == len(parts) - 1:
            break
        return part
    return None


def _detect_frameworks(path: str, language: str | None) -> tuple[str, ...]:
    """Detect framework hints from path patterns and language."""
    hints: list[str] = []
    for framework, patterns in _FRAMEWORK_PATH_HINTS.items():
        if _matches_any(path, patterns):
            hints.append(framework)

    # Language-based hints as fallback
    if not hints and language:
        language_framework_map: dict[str, str] = {
            "kotlin": "spring-boot",
        }
        if language in language_framework_map:
            hints.append(language_framework_map[language])

    return tuple(sorted(set(hints)))


class FileClassifier:
    """Classify files by language, type, and architectural layer."""

    def classify(self, files: list[FileDiff]) -> list[ClassifiedFile]:
        """Classify all files in a diff.

        Returns a ClassifiedFile for each input FileDiff, enriched with
        language, file_type, module, layer, and framework_hints metadata.
        """
        return [self._classify_single(f) for f in files]

    def _classify_single(self, file_diff: FileDiff) -> ClassifiedFile:
        """Classify a single file diff."""
        path = file_diff.path
        language = file_diff.language or _detect_language(path)
        file_type = _detect_file_type(path)
        layer = _detect_layer(path)
        module = _detect_module(path)
        framework_hints = _detect_frameworks(path, language)

        return ClassifiedFile(
            diff=file_diff,
            language=language,
            file_type=file_type,
            module=module,
            layer=layer,
            framework_hints=framework_hints,
        )
