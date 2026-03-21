"""Validate pattern data against the Pattern schema."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from codesentinel.patterns.schema import Pattern


def validate_pattern_data(data: dict[str, Any]) -> list[str]:
    """Validate raw pattern data (dict) against the Pattern schema.

    Returns a list of structured error messages.  An empty list means valid.
    """
    errors: list[str] = []
    try:
        Pattern.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors():
            loc = " -> ".join(str(part) for part in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
    except Exception as exc:
        errors.append(f"Unexpected validation error: {exc}")
    return errors


def validate_pattern(pattern: Pattern) -> list[str]:
    """Return semantic warnings for an already-parsed Pattern.

    These are advisory warnings (not schema errors) that help pattern
    authors improve quality.
    """
    warnings: list[str] = []

    if not pattern.spec.description:
        warnings.append("Pattern has no description")

    if not pattern.spec.rationale:
        warnings.append("Pattern has no rationale — explain why this matters")

    if not pattern.spec.examples.correct and not pattern.spec.examples.incorrect:
        warnings.append("Pattern has no code examples — add at least one correct and one incorrect example")

    if not pattern.spec.detection.positive_signals:
        warnings.append("Pattern has no positive detection signals")

    if not pattern.spec.remediation:
        warnings.append("Pattern has no remediation guidance")

    if pattern.metadata.confidence_threshold < 0.5:
        warnings.append("Confidence threshold below 0.5 may produce excessive false positives")

    return warnings
