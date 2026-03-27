"""Prompt templates for LLM-powered code review.

Provides system prompt construction with mode-specific instructions
and user prompt building from ReviewChunk data.
"""

from __future__ import annotations

from codesentinel.core.models import ReviewChunk

_SYSTEM_PROMPT_TEMPLATE = """\
You are CodeSentinel, an expert AI code reviewer. Your task is to review code \
changes (diffs) against a set of architectural patterns and best practices.

## Instructions

1. Analyze each file diff against the provided patterns.
2. Identify violations, anti-patterns, and areas for improvement.
3. Only report findings where you have confidence >= {confidence_threshold}.
4. Return findings as a JSON array (no markdown fences, no extra text).

## Response Format

Return ONLY a JSON array of finding objects. Each finding must have:
```
[
  {{
    "pattern_name": "string — the pattern that was violated",
    "severity": "critical|high|medium|low|info",
    "confidence": 0.0 to 1.0,
    "file": "string — file path",
    "line": integer — line number in the new file,
    "title": "string — short title",
    "description": "string — detailed description of the issue",
    "rationale": "string — why this matters",
    "remediation": "string — how to fix it",
    "code_snippet": "string — relevant code (optional)"
  }}
]
```

If there are no findings, return an empty array: []

## Review Mode

{mode_instructions}

## Patterns to Check

{patterns_context}
"""

_COACHING_INSTRUCTIONS = """\
You are in **coaching** mode. For each finding:
- Explain clearly WHY the pattern exists and why it matters.
- Provide educational context to help the developer learn.
- Suggest concrete remediation steps with code examples where helpful.
- Use an encouraging, constructive tone.
- Prioritize learning over strict enforcement.\
"""

_STRICT_INSTRUCTIONS = """\
You are in **strict** mode. For each finding:
- Enforce patterns strictly — flag all violations.
- Be concise and direct in descriptions.
- Focus on compliance rather than education.
- Every violation at or above the minimum severity must be reported.
- Do not soften language or provide extensive explanations.\
"""


def get_mode_instructions(mode: str) -> str:
    """Return mode-specific instructions for the system prompt.

    Args:
        mode: Review mode — 'coaching' or 'strict'. Unknown values
              default to coaching.

    Returns:
        Instruction text tailored to the review mode.
    """
    if mode == "strict":
        return _STRICT_INSTRUCTIONS
    return _COACHING_INSTRUCTIONS


def build_system_prompt(
    *,
    confidence_threshold: float,
    mode: str,
    patterns_context: str,
) -> str:
    """Construct the full system prompt for an LLM review call.

    Args:
        confidence_threshold: Minimum confidence to report a finding.
        mode: Review mode ('coaching' or 'strict').
        patterns_context: Formatted text describing the patterns to check.

    Returns:
        The complete system prompt string.
    """
    mode_instructions = get_mode_instructions(mode)
    return _SYSTEM_PROMPT_TEMPLATE.format(
        confidence_threshold=confidence_threshold,
        mode_instructions=mode_instructions,
        patterns_context=patterns_context or "No specific patterns provided. Use general best practices.",
    )


def build_user_prompt(chunk: ReviewChunk) -> str:
    """Build the user prompt from a ReviewChunk.

    Assembles file diffs, pattern references, and additional context
    into a single prompt string for the LLM.

    Args:
        chunk: The review chunk containing files, patterns, and context.

    Returns:
        The formatted user prompt string.
    """
    sections: list[str] = []

    sections.append("## Code Changes to Review\n")

    if not chunk.files:
        sections.append("No files to review in this chunk.\n")
    else:
        for file_diff in chunk.files:
            sections.append(f"### File: {file_diff.path}")
            sections.append(f"Status: {file_diff.status.value}")
            if file_diff.hunks:
                sections.append("```diff")
                for hunk in file_diff.hunks:
                    sections.append(hunk.content)
                sections.append("```")
            sections.append("")

    if chunk.patterns:
        sections.append("## Applicable Patterns\n")
        for pattern in chunk.patterns:
            if hasattr(pattern, "metadata") and hasattr(pattern, "spec"):
                sections.append(f"- **{pattern.metadata.name}**: {pattern.spec.description}")
            else:
                sections.append(f"- {pattern}")
        sections.append("")

    if chunk.additional_context:
        sections.append("## Additional Context\n")
        sections.append(chunk.additional_context)
        sections.append("")

    return "\n".join(sections)
