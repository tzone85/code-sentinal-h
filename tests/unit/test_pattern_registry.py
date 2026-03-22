"""Tests for patterns/registry.py — pattern registry with filtering."""

from __future__ import annotations

from codesentinel.core.enums import Severity
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.patterns.schema import (
    AppliesTo,
    Pattern,
    PatternMetadata,
    PatternSpec,
)


def _pat(
    name: str,
    category: str = "general",
    language: str | None = None,
    severity: Severity = Severity.MEDIUM,
    tags: tuple[str, ...] = (),
    include: tuple[str, ...] = ("**/*",),
    exclude: tuple[str, ...] = (),
) -> Pattern:
    return Pattern(
        metadata=PatternMetadata(
            name=name,
            category=category,
            language=language,
            severity=severity,
            tags=tags,
        ),
        spec=PatternSpec(
            description=f"Pattern {name}",
            applies_to=AppliesTo(include=include, exclude=exclude),
        ),
    )


JAVA_CLEAN = _pat("clean-arch", "architecture", "java", Severity.HIGH, ("layers",), ("**/*.java",))
PYTHON_DJANGO = _pat("django-views", "web", "python", Severity.MEDIUM, ("django",), ("**/*.py",))
GENERAL_SECURITY = _pat("no-secrets", "security", None, Severity.CRITICAL, ("security",))
TS_REACT = _pat("react-hooks", "frontend", "typescript", Severity.LOW, ("react",), ("**/*.tsx", "**/*.ts"))
INFO_NAMING = _pat("naming-conv", "style", None, Severity.INFO, ("naming",))


def _full_registry() -> PatternRegistry:
    return PatternRegistry([JAVA_CLEAN, PYTHON_DJANGO, GENERAL_SECURITY, TS_REACT, INFO_NAMING])


# ------------------------------------------------------------------ #
# all()
# ------------------------------------------------------------------ #


class TestAll:
    def test_all_returns_all(self) -> None:
        reg = _full_registry()
        assert len(reg.all()) == 5

    def test_empty_registry(self) -> None:
        reg = PatternRegistry()
        assert reg.all() == []


# ------------------------------------------------------------------ #
# by_language()
# ------------------------------------------------------------------ #


class TestByLanguage:
    def test_java(self) -> None:
        reg = _full_registry()
        result = reg.by_language("java")
        names = {p.metadata.name for p in result}
        assert "clean-arch" in names
        # Language-agnostic patterns should also match
        assert "no-secrets" in names
        assert "naming-conv" in names

    def test_python(self) -> None:
        reg = _full_registry()
        result = reg.by_language("python")
        names = {p.metadata.name for p in result}
        assert "django-views" in names
        assert "no-secrets" in names
        assert "clean-arch" not in names

    def test_case_insensitive(self) -> None:
        reg = _full_registry()
        result = reg.by_language("Java")
        assert any(p.metadata.name == "clean-arch" for p in result)


# ------------------------------------------------------------------ #
# by_category()
# ------------------------------------------------------------------ #


class TestByCategory:
    def test_security(self) -> None:
        reg = _full_registry()
        result = reg.by_category("security")
        assert len(result) == 1
        assert result[0].metadata.name == "no-secrets"

    def test_case_insensitive(self) -> None:
        reg = _full_registry()
        result = reg.by_category("Security")
        assert len(result) == 1

    def test_nonexistent_category(self) -> None:
        reg = _full_registry()
        result = reg.by_category("nonexistent")
        assert result == []


# ------------------------------------------------------------------ #
# by_severity()
# ------------------------------------------------------------------ #


class TestBySeverity:
    def test_critical_only(self) -> None:
        reg = _full_registry()
        result = reg.by_severity(Severity.CRITICAL)
        assert len(result) == 1
        assert result[0].metadata.name == "no-secrets"

    def test_high_and_above(self) -> None:
        reg = _full_registry()
        result = reg.by_severity(Severity.HIGH)
        names = {p.metadata.name for p in result}
        assert "clean-arch" in names
        assert "no-secrets" in names
        assert len(result) == 2

    def test_info_gets_all(self) -> None:
        reg = _full_registry()
        result = reg.by_severity(Severity.INFO)
        assert len(result) == 5


# ------------------------------------------------------------------ #
# by_tags()
# ------------------------------------------------------------------ #


class TestByTags:
    def test_single_tag(self) -> None:
        reg = _full_registry()
        result = reg.by_tags(["security"])
        assert len(result) == 1

    def test_multiple_tags(self) -> None:
        reg = _full_registry()
        result = reg.by_tags(["django", "react"])
        names = {p.metadata.name for p in result}
        assert "django-views" in names
        assert "react-hooks" in names

    def test_case_insensitive(self) -> None:
        reg = _full_registry()
        result = reg.by_tags(["SECURITY"])
        assert len(result) == 1

    def test_no_matching_tags(self) -> None:
        reg = _full_registry()
        result = reg.by_tags(["nonexistent"])
        assert result == []


# ------------------------------------------------------------------ #
# for_file()
# ------------------------------------------------------------------ #


class TestForFile:
    def test_java_file(self) -> None:
        reg = _full_registry()
        result = reg.for_file("src/main/java/Service.java", "java")
        names = {p.metadata.name for p in result}
        assert "clean-arch" in names
        assert "no-secrets" in names  # language-agnostic
        assert "django-views" not in names

    def test_python_file(self) -> None:
        reg = _full_registry()
        result = reg.for_file("app/views.py", "python")
        names = {p.metadata.name for p in result}
        assert "django-views" in names
        assert "no-secrets" in names
        assert "clean-arch" not in names

    def test_exclude_glob(self) -> None:
        pat_with_exclude = _pat(
            "test-exclude",
            include=("**/*.py",),
            exclude=("**/test_*",),
        )
        reg = PatternRegistry([pat_with_exclude])
        assert len(reg.for_file("app/views.py")) == 1
        assert len(reg.for_file("tests/test_views.py")) == 0

    def test_no_language_matches_agnostic(self) -> None:
        reg = _full_registry()
        result = reg.for_file("README.md", None)
        # Only language-agnostic patterns with **/* include should match
        names = {p.metadata.name for p in result}
        assert "no-secrets" in names
        assert "naming-conv" in names

    def test_no_include_match(self) -> None:
        reg = _full_registry()
        result = reg.for_file("file.rs", "rust")
        # Only agnostic patterns (no-secrets, naming-conv) match
        names = {p.metadata.name for p in result}
        assert "clean-arch" not in names
        assert "django-views" not in names


# ------------------------------------------------------------------ #
# load()
# ------------------------------------------------------------------ #


class TestLoad:
    def test_load_replaces_patterns(self) -> None:
        reg = PatternRegistry([JAVA_CLEAN])
        assert len(reg.all()) == 1
        reg.load([PYTHON_DJANGO, TS_REACT])
        assert len(reg.all()) == 2


# ------------------------------------------------------------------ #
# stats()
# ------------------------------------------------------------------ #


class TestStats:
    def test_stats_structure(self) -> None:
        reg = _full_registry()
        stats = reg.stats()
        assert stats["total"] == 5
        assert isinstance(stats["by_severity"], dict)
        assert isinstance(stats["by_language"], dict)
        assert isinstance(stats["by_category"], dict)

    def test_stats_severity_counts(self) -> None:
        reg = _full_registry()
        stats = reg.stats()
        by_sev = stats["by_severity"]
        assert by_sev["critical"] == 1
        assert by_sev["high"] == 1
        assert by_sev["medium"] == 1

    def test_stats_language_counts(self) -> None:
        reg = _full_registry()
        stats = reg.stats()
        by_lang = stats["by_language"]
        assert by_lang["java"] == 1
        assert by_lang["python"] == 1
        assert by_lang["general"] == 2  # language=None → "general"

    def test_empty_registry_stats(self) -> None:
        reg = PatternRegistry()
        stats = reg.stats()
        assert stats["total"] == 0


# ------------------------------------------------------------------ #
# _glob_match — simple fnmatch fallback (no **) → line 20
# ------------------------------------------------------------------ #


class TestGlobMatchFallback:
    def test_simple_glob_without_doublestar(self) -> None:
        """Glob like '*.py' (no **) should use fnmatch directly."""
        pat = _pat("simple-glob", include=("*.py",))
        reg = PatternRegistry([pat])
        # Root-level python file matches *.py via fnmatch
        result = reg.for_file("setup.py")
        assert len(result) == 1

    def test_simple_glob_no_match(self) -> None:
        pat = _pat("simple-glob", include=("*.java",))
        reg = PatternRegistry([pat])
        result = reg.for_file("setup.py")
        assert len(result) == 0


# ------------------------------------------------------------------ #
# for_file — language mismatch (both non-None) → line 96
# ------------------------------------------------------------------ #


class TestForFileLanguageMismatch:
    def test_java_pattern_skips_python_file(self) -> None:
        """Pattern with language=java should not match a python file."""
        reg = PatternRegistry([JAVA_CLEAN])
        result = reg.for_file("src/main/java/App.java", "python")
        names = {p.metadata.name for p in result}
        assert "clean-arch" not in names

    def test_python_pattern_skips_typescript_file(self) -> None:
        reg = PatternRegistry([PYTHON_DJANGO])
        result = reg.for_file("app/views.py", "typescript")
        names = {p.metadata.name for p in result}
        assert "django-views" not in names
