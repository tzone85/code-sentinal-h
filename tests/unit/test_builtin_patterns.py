"""Tests for built-in pattern library — verify all patterns load and validate."""

from __future__ import annotations

from codesentinel.core.enums import Severity
from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.validator import validate_pattern

# Phase 1 (5 patterns)
PHASE1_PATTERNS = {
    "clean-architecture",
    "api-error-responses",
    "security-no-hardcoded-secrets",
    "error-handling",
    "naming-conventions",
}

# Phase 2 — extended library (11 new patterns)
PHASE2_PATTERNS = {
    # Java
    "spring-boot-layers",
    "ddd-aggregates",
    "event-driven-patterns",
    # Python
    "django-patterns",
    "fastapi-patterns",
    "pep8-beyond-linting",
    # TypeScript
    "react-patterns",
    "nestjs-patterns",
    "nextjs-patterns",
    # General
    "security-basics",
    "testing-patterns",
}

ALL_EXPECTED = PHASE1_PATTERNS | PHASE2_PATTERNS


class TestBuiltinPatterns:
    def _load_all(self) -> list:
        loader = PatternLoader()
        return loader.load_builtin()

    def test_all_sixteen_patterns_load(self) -> None:
        patterns = self._load_all()
        names = {p.metadata.name for p in patterns}
        assert names == ALL_EXPECTED, f"Missing: {ALL_EXPECTED - names}, Extra: {names - ALL_EXPECTED}"

    def test_pattern_count(self) -> None:
        assert len(self._load_all()) == 16

    def test_each_pattern_has_description(self) -> None:
        for p in self._load_all():
            assert p.spec.description, f"{p.metadata.name} missing description"

    def test_each_pattern_has_rationale(self) -> None:
        for p in self._load_all():
            assert p.spec.rationale, f"{p.metadata.name} missing rationale"

    def test_each_pattern_has_examples(self) -> None:
        for p in self._load_all():
            assert p.spec.examples.correct or p.spec.examples.incorrect, f"{p.metadata.name} missing examples"

    def test_each_pattern_has_detection_signals(self) -> None:
        for p in self._load_all():
            assert p.spec.detection.positive_signals, f"{p.metadata.name} missing positive detection signals"

    def test_each_pattern_has_remediation(self) -> None:
        for p in self._load_all():
            assert p.spec.remediation, f"{p.metadata.name} missing remediation"

    def test_each_pattern_has_references(self) -> None:
        for p in self._load_all():
            assert p.spec.references, f"{p.metadata.name} missing references"

    def test_no_validation_warnings(self) -> None:
        for p in self._load_all():
            warnings = validate_pattern(p)
            assert warnings == [], f"{p.metadata.name} has warnings: {warnings}"

    def test_severity_distribution(self) -> None:
        patterns = self._load_all()
        severities = {p.metadata.name: p.metadata.severity for p in patterns}
        assert severities["security-no-hardcoded-secrets"] == Severity.CRITICAL
        assert severities["clean-architecture"] == Severity.HIGH
        assert severities["spring-boot-layers"] == Severity.HIGH
        assert severities["security-basics"] == Severity.HIGH
        assert severities["api-error-responses"] == Severity.MEDIUM
        assert severities["naming-conventions"] == Severity.LOW
        assert severities["pep8-beyond-linting"] == Severity.LOW

    def test_java_patterns_language(self) -> None:
        patterns = self._load_all()
        java_names = {"clean-architecture", "spring-boot-layers", "ddd-aggregates", "event-driven-patterns"}
        for p in patterns:
            if p.metadata.name in java_names:
                assert p.metadata.language == "java", f"{p.metadata.name} should be java"

    def test_python_patterns_language(self) -> None:
        patterns = self._load_all()
        python_names = {"django-patterns", "fastapi-patterns", "pep8-beyond-linting"}
        for p in patterns:
            if p.metadata.name in python_names:
                assert p.metadata.language == "python", f"{p.metadata.name} should be python"

    def test_typescript_patterns_language(self) -> None:
        patterns = self._load_all()
        ts_names = {"react-patterns", "nestjs-patterns", "nextjs-patterns"}
        for p in patterns:
            if p.metadata.name in ts_names:
                assert p.metadata.language == "typescript", f"{p.metadata.name} should be typescript"

    def test_general_patterns_are_language_agnostic(self) -> None:
        patterns = self._load_all()
        general_names = {
            "api-error-responses",
            "security-no-hardcoded-secrets",
            "error-handling",
            "naming-conventions",
            "security-basics",
            "testing-patterns",
        }
        for p in patterns:
            if p.metadata.name in general_names:
                assert p.metadata.language is None, f"{p.metadata.name} should be language-agnostic"
