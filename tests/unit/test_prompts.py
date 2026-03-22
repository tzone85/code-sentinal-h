"""Tests for the prompt builder module."""

from __future__ import annotations

from codesentinel.core.enums import FileStatus
from codesentinel.core.models import DiffHunk, FileDiff, ReviewChunk
from codesentinel.core.prompts import (
    build_system_prompt,
    build_user_prompt,
    get_mode_instructions,
)


class TestModeInstructions:
    """Test mode-specific instruction generation."""

    def test_coaching_mode_instructions(self) -> None:
        instructions = get_mode_instructions("coaching")
        assert "coaching" in instructions.lower() or "educational" in instructions.lower()
        assert len(instructions) > 0

    def test_strict_mode_instructions(self) -> None:
        instructions = get_mode_instructions("strict")
        assert "strict" in instructions.lower() or "enforce" in instructions.lower()
        assert len(instructions) > 0

    def test_unknown_mode_defaults_to_coaching(self) -> None:
        instructions = get_mode_instructions("unknown")
        coaching = get_mode_instructions("coaching")
        assert instructions == coaching


class TestBuildSystemPrompt:
    """Test system prompt construction."""

    def test_contains_confidence_threshold(self) -> None:
        prompt = build_system_prompt(
            confidence_threshold=0.8,
            mode="coaching",
            patterns_context="pattern info here",
        )
        assert "0.8" in prompt

    def test_contains_mode_instructions(self) -> None:
        prompt = build_system_prompt(
            confidence_threshold=0.7,
            mode="strict",
            patterns_context="",
        )
        assert "strict" in prompt.lower() or "enforce" in prompt.lower()

    def test_contains_patterns_context(self) -> None:
        prompt = build_system_prompt(
            confidence_threshold=0.7,
            mode="coaching",
            patterns_context="Check for SQL injection",
        )
        assert "Check for SQL injection" in prompt

    def test_returns_non_empty_string(self) -> None:
        prompt = build_system_prompt(
            confidence_threshold=0.7,
            mode="coaching",
            patterns_context="",
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_includes_json_format_instructions(self) -> None:
        prompt = build_system_prompt(
            confidence_threshold=0.7,
            mode="coaching",
            patterns_context="",
        )
        assert "json" in prompt.lower() or "JSON" in prompt


class TestBuildUserPrompt:
    """Test user prompt construction from ReviewChunk."""

    def test_includes_file_diffs(self) -> None:
        chunk = ReviewChunk(
            files=(
                FileDiff(
                    path="src/main.py",
                    old_path=None,
                    status=FileStatus.MODIFIED,
                    hunks=(
                        DiffHunk(
                            old_start=1,
                            old_count=3,
                            new_start=1,
                            new_count=5,
                            content="@@ -1,3 +1,5 @@\n+import os\n def main():\n     pass",
                            added_lines=("import os",),
                        ),
                    ),
                ),
            ),
        )
        prompt = build_user_prompt(chunk)
        assert "src/main.py" in prompt
        assert "import os" in prompt

    def test_includes_additional_context(self) -> None:
        chunk = ReviewChunk(
            files=(),
            additional_context="This is a Django project using DRF",
        )
        prompt = build_user_prompt(chunk)
        assert "Django" in prompt

    def test_handles_empty_chunk(self) -> None:
        chunk = ReviewChunk(files=())
        prompt = build_user_prompt(chunk)
        assert isinstance(prompt, str)

    def test_includes_multiple_files(self) -> None:
        chunk = ReviewChunk(
            files=(
                FileDiff(path="a.py", old_path=None, status=FileStatus.MODIFIED),
                FileDiff(path="b.py", old_path=None, status=FileStatus.ADDED),
            ),
        )
        prompt = build_user_prompt(chunk)
        assert "a.py" in prompt
        assert "b.py" in prompt

    def test_includes_pattern_context(self) -> None:
        chunk = ReviewChunk(
            files=(FileDiff(path="x.py", old_path=None, status=FileStatus.MODIFIED),),
            patterns=("Check for hardcoded secrets",),
        )
        prompt = build_user_prompt(chunk)
        assert "hardcoded secrets" in prompt.lower() or "Check for hardcoded secrets" in prompt
