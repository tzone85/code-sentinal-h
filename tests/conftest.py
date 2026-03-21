"""Shared test fixtures for CodeSentinel.

Provides reusable fixtures for sample diffs, patterns, mock LLM/SCM
providers, and configuration objects used across the test suite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from codesentinel.core.enums import FileStatus, FileType, Severity
from codesentinel.core.models import (
    ClassifiedFile,
    DiffHunk,
    FileDiff,
    Finding,
    LLMResponse,
    ReviewTarget,
)
from codesentinel.patterns.schema import (
    AppliesTo,
    CodeExample,
    Detection,
    Examples,
    Pattern,
    PatternMetadata,
    PatternSpec,
)

# --------------------------------------------------------------------------- #
# Path constants
# --------------------------------------------------------------------------- #

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
DIFFS_DIR = FIXTURES_DIR / "diffs"
PATTERNS_DIR = FIXTURES_DIR / "patterns"
CONFIGS_DIR = FIXTURES_DIR / "configs"


# --------------------------------------------------------------------------- #
# Sample diff text
# --------------------------------------------------------------------------- #


@pytest.fixture()
def sample_diff_text() -> str:
    """A small unified diff modifying one Python file."""
    return (
        "diff --git a/src/main.py b/src/main.py\n"
        "index 1234567..89abcde 100644\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,4 +1,5 @@\n"
        " import os\n"
        "+import sys\n"
        "\n"
        " def main():\n"
        '-    print("hello")\n'
        '+    print("hello world")\n'
    )


@pytest.fixture()
def multi_file_diff_text() -> str:
    """A unified diff with Python and Java files."""
    return (
        "diff --git a/src/main.py b/src/main.py\n"
        "index 1111111..2222222 100644\n"
        "--- a/src/main.py\n"
        "+++ b/src/main.py\n"
        "@@ -1,2 +1,3 @@\n"
        " x = 1\n"
        "+y = 2\n"
        " z = 3\n"
        "diff --git a/src/App.java b/src/App.java\n"
        "index 3333333..4444444 100644\n"
        "--- a/src/App.java\n"
        "+++ b/src/App.java\n"
        "@@ -1,3 +1,2 @@\n"
        " public class App {\n"
        "-    int old = 1;\n"
        " }\n"
    )


# --------------------------------------------------------------------------- #
# Sample FileDiff / ClassifiedFile objects
# --------------------------------------------------------------------------- #


@pytest.fixture()
def sample_file_diff() -> FileDiff:
    """A modified Python file with one hunk."""
    hunk = DiffHunk(
        old_start=1,
        old_count=4,
        new_start=1,
        new_count=5,
        content="+import sys\n-print('hello')\n+print('hello world')",
        added_lines=("import sys", "    print('hello world')"),
        removed_lines=("    print('hello')",),
        context_lines=("import os",),
    )
    return FileDiff(
        path="src/main.py",
        old_path="src/main.py",
        status=FileStatus.MODIFIED,
        hunks=(hunk,),
        language="python",
    )


@pytest.fixture()
def sample_classified_file(sample_file_diff: FileDiff) -> ClassifiedFile:
    """A classified Python source file."""
    return ClassifiedFile(
        diff=sample_file_diff,
        language="python",
        file_type=FileType.SOURCE,
        module="src",
        layer=None,
    )


@pytest.fixture()
def java_domain_file() -> ClassifiedFile:
    """A Java domain-layer file for architecture pattern tests."""
    hunk = DiffHunk(
        old_start=1,
        old_count=0,
        new_start=1,
        new_count=3,
        content="+import infra;\n+public class User {}",
        added_lines=("import infra;", "public class User {}"),
    )
    return ClassifiedFile(
        diff=FileDiff(
            path="src/domain/model/User.java",
            old_path=None,
            status=FileStatus.ADDED,
            hunks=(hunk,),
            language="java",
        ),
        language="java",
        file_type=FileType.SOURCE,
        module="domain",
        layer="domain",
    )


# --------------------------------------------------------------------------- #
# Sample patterns
# --------------------------------------------------------------------------- #


@pytest.fixture()
def general_pattern() -> Pattern:
    """A language-agnostic general pattern that matches all files."""
    return Pattern(
        metadata=PatternMetadata(
            name="error-handling",
            category="general",
            severity=Severity.MEDIUM,
        ),
        spec=PatternSpec(
            description="All errors must be handled explicitly",
            rationale="Unhandled errors cause crashes",
            detection=Detection(positive_signals=("bare except",)),
            examples=Examples(
                correct=(CodeExample(description="good", code="try: ... except ValueError: ..."),),
                incorrect=(CodeExample(description="bad", code="try: ... except: ..."),),
            ),
            remediation="Use specific exception types",
        ),
    )


@pytest.fixture()
def java_pattern() -> Pattern:
    """A Java-specific architecture pattern."""
    return Pattern(
        metadata=PatternMetadata(
            name="clean-architecture",
            category="architecture",
            language="java",
            severity=Severity.HIGH,
            tags=("clean-arch", "layers"),
            confidence_threshold=0.8,
        ),
        spec=PatternSpec(
            description="Domain layer must not import infrastructure",
            rationale="Clean Architecture Dependency Rule",
            applies_to=AppliesTo(
                include=("**/*.java",),
                exclude=("**/test/**",),
            ),
            detection=Detection(
                positive_signals=("import from infrastructure in domain",),
            ),
            examples=Examples(
                correct=(CodeExample(description="clean", code="import domain.repo;"),),
                incorrect=(CodeExample(description="violation", code="import infra.jpa;"),),
            ),
            remediation="Use a port interface in the domain layer",
        ),
    )


@pytest.fixture()
def python_pattern() -> Pattern:
    """A Python-specific pattern."""
    return Pattern(
        metadata=PatternMetadata(
            name="django-patterns",
            category="framework",
            language="python",
            severity=Severity.MEDIUM,
        ),
        spec=PatternSpec(
            description="Django views must validate input",
            applies_to=AppliesTo(include=("**/*.py",)),
        ),
    )


# --------------------------------------------------------------------------- #
# Mock LLM provider
# --------------------------------------------------------------------------- #


@pytest.fixture()
def mock_llm_provider() -> AsyncMock:
    """A mock LLM provider that returns an empty findings response."""
    provider = AsyncMock()
    provider.name = "mock-llm"
    provider.review.return_value = LLMResponse(
        content="[]",
        model="mock-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )
    provider.estimate_tokens.return_value = 100
    provider.max_context_tokens = 100_000
    return provider


@pytest.fixture()
def mock_llm_with_findings() -> AsyncMock:
    """A mock LLM provider that returns a single finding."""
    provider = AsyncMock()
    provider.name = "mock-llm"
    provider.review.return_value = LLMResponse(
        content=(
            '[{"pattern_name": "test-pattern", "severity": "high", '
            '"confidence": 0.9, "file": "src/main.py", "line": 10, '
            '"title": "Issue found", "description": "desc", '
            '"rationale": "reason", "remediation": "fix it"}]'
        ),
        model="mock-model",
        input_tokens=100,
        output_tokens=50,
        latency_ms=200,
    )
    return provider


# --------------------------------------------------------------------------- #
# Mock SCM provider
# --------------------------------------------------------------------------- #


@pytest.fixture()
def mock_scm_provider() -> AsyncMock:
    """A mock SCM provider for testing without real API calls."""
    scm = AsyncMock()
    scm.get_pr_diff.return_value = ""
    scm.post_review_comment.return_value = None
    scm.post_review_summary.return_value = None
    return scm


# --------------------------------------------------------------------------- #
# Sample findings
# --------------------------------------------------------------------------- #


@pytest.fixture()
def sample_finding() -> Finding:
    """A single HIGH severity finding."""
    return Finding(
        pattern_name="test-pattern",
        severity=Severity.HIGH,
        confidence=0.9,
        file="src/main.py",
        line=10,
        title="Test finding",
        description="A test finding description",
        rationale="Because tests",
        remediation="Fix it",
    )


@pytest.fixture()
def sample_findings() -> list[Finding]:
    """A list of findings with mixed severities."""
    return [
        Finding(
            pattern_name="sec-001",
            severity=Severity.CRITICAL,
            confidence=0.95,
            file="src/auth.py",
            line=42,
            title="SQL injection",
            description="Unsanitized user input in query",
            rationale="OWASP A1",
            remediation="Use parameterized queries",
        ),
        Finding(
            pattern_name="err-001",
            severity=Severity.MEDIUM,
            confidence=0.8,
            file="src/api.py",
            line=15,
            title="Missing error handling",
            description="API call has no error handling",
            rationale="Unhandled errors crash the service",
            remediation="Add try/except around external calls",
        ),
        Finding(
            pattern_name="style-001",
            severity=Severity.LOW,
            confidence=0.7,
            file="src/utils.py",
            line=5,
            title="Naming convention",
            description="Variable name too short",
            rationale="Readability",
            remediation="Use descriptive names",
        ),
    ]


# --------------------------------------------------------------------------- #
# Review targets
# --------------------------------------------------------------------------- #


@pytest.fixture()
def diff_review_target() -> ReviewTarget:
    """A review target pointing to a fixture diff file."""
    return ReviewTarget(
        type="diff",
        diff_path=str(DIFFS_DIR / "python_django_violation.diff"),
    )


# --------------------------------------------------------------------------- #
# Default config
# --------------------------------------------------------------------------- #


@pytest.fixture()
def default_config() -> dict[str, object]:
    """Default engine configuration matching spec defaults."""
    return {
        "mode": "coaching",
        "min_severity": "medium",
        "min_confidence": 0.7,
        "max_findings": 15,
        "fail_on": "critical",
    }
