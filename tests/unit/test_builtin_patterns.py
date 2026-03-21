"""Tests for built-in pattern library — verify all patterns load and validate."""

from __future__ import annotations

from codesentinel.core.enums import Severity
from codesentinel.patterns.loader import PatternLoader
from codesentinel.patterns.validator import validate_pattern

EXPECTED_PATTERNS = {
    "clean-architecture",
    "api-error-responses",
    "security-no-hardcoded-secrets",
    "error-handling",
    "naming-conventions",
}


class TestBuiltinPatterns:
    def _load_all(self) -> list:
        loader = PatternLoader()
        return loader.load_builtin()

    def test_all_five_patterns_load(self) -> None:
        patterns = self._load_all()
        names = {p.metadata.name for p in patterns}
        assert names == EXPECTED_PATTERNS

    def test_each_pattern_has_description(self) -> None:
        for p in self._load_all():
            assert p.spec.description, f"{p.metadata.name} missing description"

    def test_each_pattern_has_rationale(self) -> None:
        for p in self._load_all():
            assert p.spec.rationale, f"{p.metadata.name} missing rationale"

    def test_each_pattern_has_examples(self) -> None:
        for p in self._load_all():
            assert p.spec.examples.correct or p.spec.examples.incorrect, (
                f"{p.metadata.name} missing examples"
            )

    def test_each_pattern_has_detection_signals(self) -> None:
        for p in self._load_all():
            assert p.spec.detection.positive_signals, (
                f"{p.metadata.name} missing positive detection signals"
            )

    def test_each_pattern_has_remediation(self) -> None:
        for p in self._load_all():
            assert p.spec.remediation, f"{p.metadata.name} missing remediation"

    def test_each_pattern_has_references(self) -> None:
        for p in self._load_all():
            assert p.spec.references, f"{p.metadata.name} missing references"

    def test_no_validation_warnings_for_complete_patterns(self) -> None:
        for p in self._load_all():
            warnings = validate_pattern(p)
            assert warnings == [], f"{p.metadata.name} has warnings: {warnings}"

    def test_severity_distribution(self) -> None:
        patterns = self._load_all()
        severities = {p.metadata.name: p.metadata.severity for p in patterns}
        assert severities["security-no-hardcoded-secrets"] == Severity.CRITICAL
        assert severities["clean-architecture"] == Severity.HIGH
        assert severities["api-error-responses"] == Severity.MEDIUM
        assert severities["error-handling"] == Severity.MEDIUM
        assert severities["naming-conventions"] == Severity.LOW

    def test_clean_architecture_is_java_only(self) -> None:
        patterns = self._load_all()
        clean_arch = next(p for p in patterns if p.metadata.name == "clean-architecture")
        assert clean_arch.metadata.language == "java"
        assert "**/*.java" in clean_arch.spec.applies_to.include

    def test_general_patterns_are_language_agnostic(self) -> None:
        patterns = self._load_all()
        general = [p for p in patterns if p.metadata.name != "clean-architecture"]
        for p in general:
            assert p.metadata.language is None, (
                f"{p.metadata.name} should be language-agnostic"
            )
