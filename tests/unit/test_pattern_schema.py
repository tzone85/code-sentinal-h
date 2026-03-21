"""Tests for patterns/schema.py — Pydantic pattern models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codesentinel.core.enums import Severity
from codesentinel.patterns.schema import (
    AppliesTo,
    CodeExample,
    Detection,
    Examples,
    Pattern,
    PatternMetadata,
    PatternSpec,
    Reference,
)

# ------------------------------------------------------------------ #
# PatternMetadata
# ------------------------------------------------------------------ #


class TestPatternMetadata:
    def test_valid_kebab_case_name(self) -> None:
        meta = PatternMetadata(name="clean-architecture", category="architecture")
        assert meta.name == "clean-architecture"

    def test_single_word_name(self) -> None:
        meta = PatternMetadata(name="security", category="general")
        assert meta.name == "security"

    def test_invalid_name_uppercase(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            PatternMetadata(name="CleanArchitecture", category="arch")

    def test_invalid_name_underscore(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            PatternMetadata(name="clean_architecture", category="arch")

    def test_invalid_name_spaces(self) -> None:
        with pytest.raises(ValidationError, match="kebab-case"):
            PatternMetadata(name="clean architecture", category="arch")

    def test_default_severity(self) -> None:
        meta = PatternMetadata(name="test-pattern", category="general")
        assert meta.severity == Severity.MEDIUM

    def test_custom_severity(self) -> None:
        meta = PatternMetadata(name="critical-vuln", category="security", severity=Severity.CRITICAL)
        assert meta.severity == Severity.CRITICAL

    def test_default_confidence_threshold(self) -> None:
        meta = PatternMetadata(name="test-pattern", category="general")
        assert meta.confidence_threshold == 0.7

    def test_confidence_threshold_bounds(self) -> None:
        PatternMetadata(name="test-a", category="g", confidence_threshold=0.0)
        PatternMetadata(name="test-b", category="g", confidence_threshold=1.0)
        with pytest.raises(ValidationError):
            PatternMetadata(name="test-c", category="g", confidence_threshold=-0.1)
        with pytest.raises(ValidationError):
            PatternMetadata(name="test-d", category="g", confidence_threshold=1.1)

    def test_tags_as_tuple(self) -> None:
        meta = PatternMetadata(name="test-tags", category="g", tags=("a", "b"))
        assert meta.tags == ("a", "b")

    def test_language_none_by_default(self) -> None:
        meta = PatternMetadata(name="test-lang", category="g")
        assert meta.language is None

    def test_frozen(self) -> None:
        meta = PatternMetadata(name="frozen-test", category="g")
        with pytest.raises(ValidationError):
            meta.name = "mutated"  # type: ignore[misc]


# ------------------------------------------------------------------ #
# AppliesTo
# ------------------------------------------------------------------ #


class TestAppliesTo:
    def test_defaults(self) -> None:
        at = AppliesTo()
        assert at.include == ("**/*",)
        assert at.exclude == ()

    def test_custom_globs(self) -> None:
        at = AppliesTo(include=("**/*.java",), exclude=("**/test/**",))
        assert at.include == ("**/*.java",)
        assert at.exclude == ("**/test/**",)


# ------------------------------------------------------------------ #
# Detection
# ------------------------------------------------------------------ #


class TestDetection:
    def test_defaults(self) -> None:
        d = Detection()
        assert d.positive_signals == ()
        assert d.negative_signals == ()
        assert d.context_clues == ()

    def test_with_signals(self) -> None:
        d = Detection(positive_signals=("sig1",), negative_signals=("neg1",), context_clues=("clue1",))
        assert len(d.positive_signals) == 1


# ------------------------------------------------------------------ #
# CodeExample & Examples
# ------------------------------------------------------------------ #


class TestExamples:
    def test_code_example(self) -> None:
        ex = CodeExample(description="good code", code="print('hello')")
        assert ex.description == "good code"

    def test_examples_container(self) -> None:
        correct = CodeExample(description="correct", code="ok()")
        incorrect = CodeExample(description="wrong", code="bad()")
        examples = Examples(correct=(correct,), incorrect=(incorrect,))
        assert len(examples.correct) == 1
        assert len(examples.incorrect) == 1


# ------------------------------------------------------------------ #
# Reference
# ------------------------------------------------------------------ #


class TestReference:
    def test_reference(self) -> None:
        ref = Reference(title="Docs", url="https://example.com")
        assert ref.title == "Docs"
        assert ref.url == "https://example.com"


# ------------------------------------------------------------------ #
# PatternSpec
# ------------------------------------------------------------------ #


class TestPatternSpec:
    def test_minimal_spec(self) -> None:
        spec = PatternSpec(description="A test pattern")
        assert spec.description == "A test pattern"
        assert spec.rationale == ""
        assert spec.remediation == ""

    def test_full_spec(self) -> None:
        spec = PatternSpec(
            description="desc",
            rationale="reason",
            applies_to=AppliesTo(include=("**/*.py",)),
            detection=Detection(positive_signals=("sig",)),
            examples=Examples(
                correct=(CodeExample(description="good", code="ok()"),),
            ),
            remediation="fix it",
            references=(Reference(title="ref", url="https://x.com"),),
        )
        assert spec.applies_to.include == ("**/*.py",)
        assert len(spec.references) == 1


# ------------------------------------------------------------------ #
# Pattern (top-level)
# ------------------------------------------------------------------ #


class TestPattern:
    def test_minimal_pattern(self) -> None:
        p = Pattern(
            metadata=PatternMetadata(name="test-pat", category="general"),
            spec=PatternSpec(description="desc"),
        )
        assert p.api_version == "v1"
        assert p.kind == "Pattern"
        assert p.metadata.name == "test-pat"

    def test_from_dict_with_alias(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "metadata": {"name": "from-dict", "category": "test"},
            "spec": {"description": "from dict"},
        }
        p = Pattern.model_validate(data)
        assert p.api_version == "v1"
        assert p.metadata.name == "from-dict"

    def test_populate_by_name(self) -> None:
        data = {
            "api_version": "v1",
            "kind": "Pattern",
            "metadata": {"name": "by-name", "category": "test"},
            "spec": {"description": "by name"},
        }
        p = Pattern.model_validate(data)
        assert p.api_version == "v1"

    def test_roundtrip_dump_with_alias(self) -> None:
        p = Pattern(
            metadata=PatternMetadata(name="roundtrip", category="g"),
            spec=PatternSpec(description="d"),
        )
        dumped = p.model_dump(by_alias=True)
        assert "apiVersion" in dumped
        restored = Pattern.model_validate(dumped)
        assert restored.metadata.name == "roundtrip"

    def test_frozen(self) -> None:
        p = Pattern(
            metadata=PatternMetadata(name="frozen", category="g"),
            spec=PatternSpec(description="d"),
        )
        with pytest.raises(ValidationError):
            p.kind = "Other"  # type: ignore[misc]

    def test_missing_metadata_raises(self) -> None:
        with pytest.raises(ValidationError):
            Pattern(spec=PatternSpec(description="no metadata"))  # type: ignore[call-arg]

    def test_missing_spec_raises(self) -> None:
        with pytest.raises(ValidationError):
            Pattern(metadata=PatternMetadata(name="no-spec", category="g"))  # type: ignore[call-arg]
