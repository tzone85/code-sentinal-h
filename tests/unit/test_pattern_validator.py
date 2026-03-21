"""Tests for patterns/validator.py — pattern validation."""

from __future__ import annotations

from codesentinel.patterns.schema import (
    CodeExample,
    Detection,
    Examples,
    Pattern,
    PatternMetadata,
    PatternSpec,
)
from codesentinel.patterns.validator import validate_pattern, validate_pattern_data


class TestValidatePatternData:
    def test_valid_pattern_data(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "metadata": {"name": "valid-name", "category": "general"},
            "spec": {"description": "A valid pattern"},
        }
        errors = validate_pattern_data(data)
        assert errors == []

    def test_invalid_name_returns_errors(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "metadata": {"name": "BAD NAME", "category": "general"},
            "spec": {"description": "bad name"},
        }
        errors = validate_pattern_data(data)
        assert len(errors) > 0
        assert any("kebab-case" in e for e in errors)

    def test_missing_metadata_returns_errors(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "spec": {"description": "no meta"},
        }
        errors = validate_pattern_data(data)
        assert len(errors) > 0

    def test_missing_spec_returns_errors(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "metadata": {"name": "no-spec", "category": "g"},
        }
        errors = validate_pattern_data(data)
        assert len(errors) > 0

    def test_invalid_confidence_threshold(self) -> None:
        data = {
            "apiVersion": "v1",
            "kind": "Pattern",
            "metadata": {"name": "bad-conf", "category": "g", "confidence_threshold": 2.0},
            "spec": {"description": "d"},
        }
        errors = validate_pattern_data(data)
        assert len(errors) > 0

    def test_empty_dict_returns_errors(self) -> None:
        errors = validate_pattern_data({})
        assert len(errors) > 0


class TestValidatePattern:
    def _make_pattern(self, **spec_overrides: object) -> Pattern:
        spec_args = {
            "description": "A complete pattern",
            "rationale": "It matters because...",
            "detection": Detection(positive_signals=("signal",)),
            "examples": Examples(
                correct=(CodeExample(description="good", code="ok()"),),
                incorrect=(CodeExample(description="bad", code="bad()"),),
            ),
            "remediation": "Fix it like this",
        }
        spec_args.update(spec_overrides)
        return Pattern(
            metadata=PatternMetadata(name="test-warn", category="g"),
            spec=PatternSpec(**spec_args),  # type: ignore[arg-type]
        )

    def test_complete_pattern_no_warnings(self) -> None:
        p = self._make_pattern()
        warnings = validate_pattern(p)
        assert warnings == []

    def test_missing_description_warns(self) -> None:
        p = self._make_pattern(description="")
        warnings = validate_pattern(p)
        assert any("description" in w for w in warnings)

    def test_missing_rationale_warns(self) -> None:
        p = self._make_pattern(rationale="")
        warnings = validate_pattern(p)
        assert any("rationale" in w for w in warnings)

    def test_no_examples_warns(self) -> None:
        p = self._make_pattern(examples=Examples())
        warnings = validate_pattern(p)
        assert any("examples" in w.lower() for w in warnings)

    def test_no_positive_signals_warns(self) -> None:
        p = self._make_pattern(detection=Detection())
        warnings = validate_pattern(p)
        assert any("positive" in w.lower() for w in warnings)

    def test_no_remediation_warns(self) -> None:
        p = self._make_pattern(remediation="")
        warnings = validate_pattern(p)
        assert any("remediation" in w.lower() for w in warnings)

    def test_low_confidence_threshold_warns(self) -> None:
        p = Pattern(
            metadata=PatternMetadata(name="low-conf", category="g", confidence_threshold=0.3),
            spec=PatternSpec(
                description="d",
                rationale="r",
                detection=Detection(positive_signals=("s",)),
                examples=Examples(
                    correct=(CodeExample(description="g", code="x"),),
                    incorrect=(CodeExample(description="b", code="y"),),
                ),
                remediation="fix",
            ),
        )
        warnings = validate_pattern(p)
        assert any("0.5" in w for w in warnings)


class TestValidatePatternDataEdgeCases:
    """Cover line 24-25: the except Exception fallback in validate_pattern_data."""

    def test_non_dict_input(self) -> None:
        """Passing something that causes an unexpected error."""
        # A completely mangled input that might trigger an unexpected error
        data = {"metadata": None, "spec": None}
        errors = validate_pattern_data(data)
        assert len(errors) > 0

    def test_string_input(self) -> None:
        """validate_pattern_data should handle weird types gracefully."""
        errors = validate_pattern_data({"apiVersion": "v1", "kind": "Pattern", "metadata": "not-a-dict", "spec": 123})
        assert len(errors) > 0

    def test_nested_invalid_types(self) -> None:
        errors = validate_pattern_data(
            {
                "apiVersion": "v1",
                "kind": "Pattern",
                "metadata": {"name": 123, "category": []},
                "spec": {"description": True},
            }
        )
        assert len(errors) > 0
