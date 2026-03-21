"""Pydantic configuration models for CodeSentinel.

All models use ``frozen=True`` to enforce immutability — consistent with
the frozen-dataclass convention used in ``core/models.py``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# LLM configuration
# --------------------------------------------------------------------------- #

_VALID_PROVIDERS = Literal["claude", "openai", "ollama"]


class LLMConfig(BaseModel):
    """LLM provider settings."""

    model_config = ConfigDict(frozen=True)

    provider: _VALID_PROVIDERS = "claude"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = Field(default=4096, gt=0)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_concurrent_requests: int = Field(default=3, gt=0)

    claude: dict[str, object] = Field(default_factory=dict)
    openai: dict[str, object] = Field(default_factory=dict)
    ollama: dict[str, object] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Pattern configuration
# --------------------------------------------------------------------------- #


class BuiltinPatternsConfig(BaseModel):
    """Controls which built-in patterns are loaded."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    include: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()


class RemotePatternSource(BaseModel):
    """A remote Git repository containing additional patterns."""

    model_config = ConfigDict(frozen=True)

    repo: str
    path: str
    ref: str = "main"
    cache_ttl: int = Field(default=3600, gt=0)


class PatternsConfig(BaseModel):
    """Where to load patterns from."""

    model_config = ConfigDict(frozen=True)

    builtin: BuiltinPatternsConfig = Field(default_factory=BuiltinPatternsConfig)
    remote: tuple[RemotePatternSource, ...] = ()
    local: tuple[str, ...] = ()


# --------------------------------------------------------------------------- #
# Review configuration
# --------------------------------------------------------------------------- #

_VALID_SEVERITIES = Literal["critical", "high", "medium", "low", "info"]
_VALID_MODES = Literal["coaching", "strict", "gatekeeping"]

_DEFAULT_IGNORE_GLOBS: tuple[str, ...] = (
    "*.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.snap",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.gif",
    "*.ico",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "go.sum",
    "Cargo.lock",
)


class AdditionalContext(BaseModel):
    """An extra file to include as context for the LLM."""

    model_config = ConfigDict(frozen=True)

    path: str
    description: str = ""


class ReviewConfig(BaseModel):
    """Review behaviour settings."""

    model_config = ConfigDict(frozen=True)

    min_severity: _VALID_SEVERITIES = "medium"
    max_findings: int = Field(default=15, gt=0)
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    mode: _VALID_MODES = "coaching"
    focus: tuple[str, ...] = ()
    ignore: tuple[str, ...] = _DEFAULT_IGNORE_GLOBS
    additional_context: tuple[AdditionalContext, ...] = ()


# --------------------------------------------------------------------------- #
# Reporter configuration
# --------------------------------------------------------------------------- #

_VALID_COMMENT_STYLES = Literal["inline", "summary", "both"]


class TerminalReporterConfig(BaseModel):
    """Terminal (Rich) reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = True
    color: bool = True
    verbose: bool = False


class GitHubReporterConfig(BaseModel):
    """GitHub PR review reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    post_review: bool = True
    request_changes_on: _VALID_SEVERITIES = "critical"
    comment_style: _VALID_COMMENT_STYLES = "both"


class GitLabReporterConfig(BaseModel):
    """GitLab MR reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    post_review: bool = True
    request_changes_on: _VALID_SEVERITIES = "critical"
    comment_style: _VALID_COMMENT_STYLES = "both"


class AzureDevOpsReporterConfig(BaseModel):
    """Azure DevOps PR reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    post_review: bool = True
    request_changes_on: _VALID_SEVERITIES = "critical"
    comment_style: _VALID_COMMENT_STYLES = "both"


class JsonReporterConfig(BaseModel):
    """JSON file reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    output_path: str = "codesentinel-report.json"


class SarifReporterConfig(BaseModel):
    """SARIF file reporter settings."""

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    output_path: str = "codesentinel-report.sarif"


class ReportersConfig(BaseModel):
    """Top-level reporters configuration."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    terminal: TerminalReporterConfig = Field(default_factory=TerminalReporterConfig)
    github: GitHubReporterConfig = Field(default_factory=GitHubReporterConfig)
    gitlab: GitLabReporterConfig = Field(default_factory=GitLabReporterConfig)
    azure_devops: AzureDevOpsReporterConfig = Field(
        default_factory=AzureDevOpsReporterConfig,
    )
    json_reporter: JsonReporterConfig = Field(
        default_factory=JsonReporterConfig,
        alias="json",
    )
    sarif: SarifReporterConfig = Field(default_factory=SarifReporterConfig)


# --------------------------------------------------------------------------- #
# Top-level configuration
# --------------------------------------------------------------------------- #


class CodeSentinelConfig(BaseModel):
    """Root configuration model, combining all sections."""

    model_config = ConfigDict(frozen=True)

    version: str = "1.0"
    llm: LLMConfig = Field(default_factory=LLMConfig)
    patterns: PatternsConfig = Field(default_factory=PatternsConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    reporters: ReportersConfig = Field(default_factory=ReportersConfig)
