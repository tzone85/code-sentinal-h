"""Unit tests for core/pattern_matcher.py."""

from __future__ import annotations

import pytest

from codesentinel.core.enums import FileStatus, FileType
from codesentinel.core.models import ClassifiedFile, FileDiff
from codesentinel.core.pattern_matcher import PatternMatcher
from codesentinel.patterns.schema import (
    AppliesTo,
    Pattern,
    PatternMetadata,
    PatternSpec,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_file(
    path: str,
    language: str | None = None,
    file_type: FileType = FileType.SOURCE,
    layer: str | None = None,
    module: str | None = None,
) -> ClassifiedFile:
    """Create a minimal ClassifiedFile for testing."""
    return ClassifiedFile(
        diff=FileDiff(path=path, old_path=None, status=FileStatus.MODIFIED),
        language=language,
        file_type=file_type,
        module=module,
        layer=layer,
    )


def _make_pattern(
    name: str,
    *,
    language: str | None = None,
    category: str = "general",
    include: tuple[str, ...] = ("**/*",),
    exclude: tuple[str, ...] = (),
) -> Pattern:
    """Create a minimal Pattern for testing."""
    return Pattern(
        metadata=PatternMetadata(name=name, category=category, language=language),
        spec=PatternSpec(
            description=f"Test pattern: {name}",
            applies_to=AppliesTo(include=include, exclude=exclude),
        ),
    )


@pytest.fixture()
def matcher() -> PatternMatcher:
    return PatternMatcher()


# --------------------------------------------------------------------------- #
# Empty / edge-case inputs
# --------------------------------------------------------------------------- #


class TestEmptyInputs:
    def test_no_files_returns_empty(self, matcher: PatternMatcher) -> None:
        patterns = [_make_pattern("p1")]
        result = matcher.match([], patterns)
        assert result == {}

    def test_no_patterns_returns_empty(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/main.py", language="python")]
        result = matcher.match(files, [])
        assert result == {}

    def test_both_empty_returns_empty(self, matcher: PatternMatcher) -> None:
        result = matcher.match([], [])
        assert result == {}


# --------------------------------------------------------------------------- #
# Glob include matching
# --------------------------------------------------------------------------- #


class TestGlobInclude:
    def test_wildcard_matches_all_files(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/main.py", language="python"),
            _make_file("src/App.java", language="java"),
        ]
        patterns = [_make_pattern("catch-all", include=("**/*",))]
        result = matcher.match(files, patterns)
        assert "src/main.py" in result
        assert "src/App.java" in result

    def test_extension_glob_filters_correctly(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/main.py", language="python"),
            _make_file("src/App.java", language="java"),
        ]
        patterns = [_make_pattern("java-only", language="java", include=("**/*.java",))]
        result = matcher.match(files, patterns)
        assert "src/App.java" in result
        assert "src/main.py" not in result

    def test_directory_glob_matches(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/domain/model/User.java", language="java"),
            _make_file("src/controller/UserCtrl.java", language="java"),
        ]
        patterns = [_make_pattern("domain-only", language="java", include=("**/domain/**",))]
        result = matcher.match(files, patterns)
        assert "src/domain/model/User.java" in result
        assert "src/controller/UserCtrl.java" not in result


# --------------------------------------------------------------------------- #
# Glob exclude matching
# --------------------------------------------------------------------------- #


class TestGlobExclude:
    def test_exclude_removes_matching_files(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/main.py", language="python"),
            _make_file("src/tests/test_main.py", language="python"),
        ]
        patterns = [
            _make_pattern(
                "no-tests",
                language="python",
                include=("**/*.py",),
                exclude=("**/test/**", "**/tests/**"),
            )
        ]
        result = matcher.match(files, patterns)
        assert "src/main.py" in result
        assert "src/tests/test_main.py" not in result

    def test_exclude_takes_precedence_over_include(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/generated/Api.java", language="java")]
        patterns = [
            _make_pattern(
                "no-generated",
                language="java",
                include=("**/*.java",),
                exclude=("**/generated/**",),
            )
        ]
        result = matcher.match(files, patterns)
        assert "src/generated/Api.java" not in result


# --------------------------------------------------------------------------- #
# Language matching
# --------------------------------------------------------------------------- #


class TestLanguageMatching:
    def test_language_specific_pattern_matches_same_language(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/main.py", language="python")]
        patterns = [_make_pattern("py-pattern", language="python")]
        result = matcher.match(files, patterns)
        assert "src/main.py" in result

    def test_language_specific_pattern_skips_different_language(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/main.py", language="python")]
        patterns = [_make_pattern("java-pattern", language="java")]
        result = matcher.match(files, patterns)
        assert "src/main.py" not in result

    def test_language_agnostic_pattern_matches_any_language(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/main.py", language="python"),
            _make_file("src/App.java", language="java"),
        ]
        patterns = [_make_pattern("agnostic", language=None)]
        result = matcher.match(files, patterns)
        assert "src/main.py" in result
        assert "src/App.java" in result

    def test_file_with_no_language_matches_agnostic_only(self, matcher: PatternMatcher) -> None:
        files = [_make_file("Makefile", language=None)]
        patterns = [
            _make_pattern("agnostic", language=None),
            _make_pattern("py-only", language="python"),
        ]
        result = matcher.match(files, patterns)
        assert "Makefile" in result
        assert len(result["Makefile"]) == 1
        assert result["Makefile"][0].metadata.name == "agnostic"


# --------------------------------------------------------------------------- #
# Multi-file, multi-pattern combinations
# --------------------------------------------------------------------------- #


class TestMultiMatch:
    def test_file_matches_multiple_patterns(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/main.py", language="python")]
        patterns = [
            _make_pattern("py-security", language="python"),
            _make_pattern("py-naming", language="python"),
            _make_pattern("general-errors", language=None),
        ]
        result = matcher.match(files, patterns)
        assert len(result["src/main.py"]) == 3

    def test_pattern_matches_multiple_files(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/a.py", language="python"),
            _make_file("src/b.py", language="python"),
        ]
        patterns = [_make_pattern("py-pattern", language="python")]
        result = matcher.match(files, patterns)
        assert "src/a.py" in result
        assert "src/b.py" in result

    def test_no_match_file_absent_from_result(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/main.py", language="python"),
            _make_file("README.md", language=None, file_type=FileType.DOCS),
        ]
        patterns = [_make_pattern("py-only", language="python", include=("**/*.py",))]
        result = matcher.match(files, patterns)
        assert "src/main.py" in result
        assert "README.md" not in result


# --------------------------------------------------------------------------- #
# Category matching (pattern category vs file layer)
# --------------------------------------------------------------------------- #


class TestCategoryMatching:
    def test_architecture_pattern_matches_domain_layer(self, matcher: PatternMatcher) -> None:
        files = [_make_file("src/domain/User.java", language="java", layer="domain")]
        patterns = [_make_pattern("clean-arch", language="java", category="architecture", include=("**/*.java",))]
        result = matcher.match(files, patterns)
        assert "src/domain/User.java" in result

    def test_general_category_matches_any_layer(self, matcher: PatternMatcher) -> None:
        files = [
            _make_file("src/controller/Api.java", language="java", layer="presentation"),
        ]
        patterns = [_make_pattern("general-rule", language="java", category="general")]
        result = matcher.match(files, patterns)
        assert "src/controller/Api.java" in result


# --------------------------------------------------------------------------- #
# Root file matching with **/ prefix (line 30)
# --------------------------------------------------------------------------- #


class TestRootFileMatching:
    def test_root_file_matches_doublestar_glob(self, matcher: PatternMatcher) -> None:
        """Root-level file should match **/*.py via stripped suffix fallback."""
        files = [_make_file("setup.py", language="python")]
        patterns = [_make_pattern("catch-py", language="python", include=("**/*.py",))]
        result = matcher.match(files, patterns)
        assert "setup.py" in result

    def test_root_file_matches_wildcard(self, matcher: PatternMatcher) -> None:
        files = [_make_file("Makefile", language=None)]
        patterns = [_make_pattern("all", include=("**/*",))]
        result = matcher.match(files, patterns)
        assert "Makefile" in result

    def test_root_file_no_match_specific_dir(self, matcher: PatternMatcher) -> None:
        """Root file should not match a directory-specific glob."""
        files = [_make_file("setup.py", language="python")]
        patterns = [_make_pattern("src-only", include=("src/**/*.py",))]
        result = matcher.match(files, patterns)
        assert "setup.py" not in result
