"""Pydantic models for the CodeSentinel pattern schema."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codesentinel.core.enums import Severity

_KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PatternMetadata(BaseModel):
    """Pattern identity and classification metadata."""

    model_config = ConfigDict(frozen=True)

    name: str
    category: str
    language: str | None = None
    severity: Severity = Severity.MEDIUM
    tags: tuple[str, ...] = ()
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _KEBAB_CASE_RE.match(value):
            msg = f"Pattern name must be kebab-case: {value!r}"
            raise ValueError(msg)
        return value


class AppliesTo(BaseModel):
    """File glob patterns controlling where a pattern applies."""

    model_config = ConfigDict(frozen=True)

    include: tuple[str, ...] = ("**/*",)
    exclude: tuple[str, ...] = ()


class Detection(BaseModel):
    """Signals used by the LLM to detect pattern violations."""

    model_config = ConfigDict(frozen=True)

    positive_signals: tuple[str, ...] = ()
    negative_signals: tuple[str, ...] = ()
    context_clues: tuple[str, ...] = ()


class CodeExample(BaseModel):
    """A single code example (correct or incorrect)."""

    model_config = ConfigDict(frozen=True)

    description: str
    code: str


class Examples(BaseModel):
    """Correct and incorrect code examples for a pattern."""

    model_config = ConfigDict(frozen=True)

    correct: tuple[CodeExample, ...] = ()
    incorrect: tuple[CodeExample, ...] = ()


class Reference(BaseModel):
    """External reference link for a pattern."""

    model_config = ConfigDict(frozen=True)

    title: str
    url: str


class PatternSpec(BaseModel):
    """Full specification of a pattern's behaviour."""

    model_config = ConfigDict(frozen=True)

    description: str
    rationale: str = ""
    applies_to: AppliesTo = Field(default_factory=AppliesTo)
    detection: Detection = Field(default_factory=Detection)
    examples: Examples = Field(default_factory=Examples)
    remediation: str = ""
    references: tuple[Reference, ...] = ()


class Pattern(BaseModel):
    """Top-level pattern document matching the YAML schema."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    api_version: str = Field(alias="apiVersion", default="v1")
    kind: str = "Pattern"
    metadata: PatternMetadata
    spec: PatternSpec
