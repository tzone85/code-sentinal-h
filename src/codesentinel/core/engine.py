"""Review engine — main pipeline orchestrator.

Coordinates the full review pipeline from diff extraction through LLM
analysis to result reporting.  Each stage delegates to an injected
component, keeping the engine itself thin and testable.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from codesentinel.core.context_builder import ContextBuilder
from codesentinel.core.diff_parser import DiffParser
from codesentinel.core.enums import Severity
from codesentinel.core.exceptions import LLMError, SCMError
from codesentinel.core.file_classifier import FileClassifier
from codesentinel.core.models import (
    Finding,
    LLMResponse,
    ReviewChunk,
    ReviewResult,
    ReviewStats,
    ReviewTarget,
)
from codesentinel.core.pattern_matcher import PatternMatcher
from codesentinel.core.post_processor import PostProcessor
from codesentinel.core.prompts import build_system_prompt, build_user_prompt
from codesentinel.llm.base import LLMProvider
from codesentinel.patterns.registry import PatternRegistry
from codesentinel.reporters.base import Reporter
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

# Exit codes matching the CLI spec.
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_CONFIG_ERROR = 2
EXIT_RUNTIME_ERROR = 3

# Default concurrency for parallel LLM calls.
_DEFAULT_MAX_CONCURRENT = 3

# Retry delay for transient LLM failures (seconds).
_RETRY_BASE_DELAY = 2.0


@dataclass(frozen=True)
class EngineConfig:
    """Configuration subset relevant to the review engine."""

    mode: str = "coaching"
    min_severity: Severity = Severity.MEDIUM
    min_confidence: float = 0.7
    max_findings: int = 15
    max_concurrent_requests: int = _DEFAULT_MAX_CONCURRENT
    fail_on: Severity = Severity.CRITICAL
    additional_context: str = ""
    max_tokens: int = 100_000


class ReviewEngine:
    """Orchestrates the full code review pipeline.

    Uses constructor injection so every collaborator can be replaced
    with a test double.
    """

    def __init__(
        self,
        *,
        config: EngineConfig,
        llm_provider: LLMProvider,
        scm_provider: SCMProvider | None = None,
        pattern_registry: PatternRegistry,
        reporters: list[Reporter] | None = None,
    ) -> None:
        self._config = config
        self._llm = llm_provider
        self._scm = scm_provider
        self._registry = pattern_registry
        self._reporters = reporters or []

        # Internal collaborators (deterministic, no need to inject)
        self._diff_parser = DiffParser()
        self._file_classifier = FileClassifier()
        self._pattern_matcher = PatternMatcher()
        self._context_builder = ContextBuilder(max_tokens=config.max_tokens)
        self._post_processor = PostProcessor(
            min_severity=config.min_severity,
            min_confidence=config.min_confidence,
            max_findings=config.max_findings,
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def review(self, target: ReviewTarget) -> ReviewResult:
        """Run the full review pipeline.

        Steps:
        1.  Extract diff from target
        2.  Parse diff
        3.  Classify changed files
        4.  Match relevant patterns
        5.  Build LLM context chunks
        6.  Send chunks to LLM (parallel, rate-limited)
        7.  Parse LLM responses
        8.  Post-process findings
        9.  Build ReviewStats
        10. Dispatch to reporters
        11. Return ReviewResult
        """
        start_ns = time.monotonic_ns()

        # 1. Extract raw diff text
        raw_diff = await self._extract_diff(target)

        # 2. Parse diff
        parsed = self._diff_parser.parse(raw_diff)

        if not parsed.files:
            logger.info("Zero files in diff — nothing to review.")
            return self._empty_result(target, start_ns)

        # 3. Classify changed files
        classified = self._file_classifier.classify(list(parsed.files))

        # 4. Match relevant patterns
        all_patterns = self._registry.all()
        matched = self._pattern_matcher.match(classified, all_patterns)

        if not matched:
            logger.info("No patterns match any changed files.")
            return self._empty_result(target, start_ns, patterns_loaded=len(all_patterns))

        # 5. Build LLM context chunks
        chunks = self._context_builder.build_chunks(
            classified,
            matched,
            self._config.additional_context,
        )

        if not chunks:
            logger.info("No review chunks generated.")
            return self._empty_result(target, start_ns, patterns_loaded=len(all_patterns))

        # 6 + 7. Send chunks to LLM and parse responses
        raw_findings, llm_calls, input_tokens, output_tokens, failed_chunks = (
            await self._review_chunks(chunks)
        )

        # 8. Post-process findings
        processed = self._post_processor.process(raw_findings)

        # 9. Build stats
        matched_pattern_count = len({
            p.metadata.name
            for patterns in matched.values()
            for p in patterns
        })
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        stats = ReviewStats(
            files_reviewed=len(parsed.files),
            patterns_loaded=len(all_patterns),
            patterns_matched=matched_pattern_count,
            findings_total=len(processed),
            findings_by_severity=_count_by_severity(processed),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_calls=llm_calls,
            duration_ms=duration_ms,
        )

        result = ReviewResult(
            findings=tuple(processed),
            stats=stats,
            target=target,
        )

        # 10. Dispatch to reporters
        await self._dispatch_reporters(result)

        # Check if all chunks failed → runtime error
        if failed_chunks == len(chunks):
            logger.error("All LLM chunks failed.")

        # 11. Return result
        return result

    def compute_exit_code(self, result: ReviewResult) -> int:
        """Determine the CLI exit code from a review result.

        Returns:
            0 — no findings at or above fail_on severity
            1 — findings found at or above fail_on severity
        """
        for finding in result.findings:
            if finding.severity >= self._config.fail_on:
                return EXIT_FINDINGS
        return EXIT_CLEAN

    # ------------------------------------------------------------------ #
    # Diff extraction
    # ------------------------------------------------------------------ #

    async def _extract_diff(self, target: ReviewTarget) -> str:
        """Get the raw diff text based on the target type."""
        if target.type == "diff" and target.diff_path:
            return self._read_diff_file(target.diff_path)

        if target.type == "pr" and target.pr_url:
            if self._scm is None:
                raise SCMError("SCM provider required for PR reviews.")
            return await self._scm.get_pr_diff(target.pr_url)

        if target.type == "branch":
            if self._scm is None:
                raise SCMError("SCM provider required for branch reviews.")
            repo = target.repo_path or "."
            base = target.base_branch or "main"
            return await self._scm.get_local_diff(repo, base, target.branch)

        if target.type == "staged":
            if self._scm is None:
                raise SCMError("SCM provider required for staged reviews.")
            repo = target.repo_path or "."
            return await self._scm.get_local_diff(repo, "HEAD", None)

        raise SCMError(f"Unsupported review target type: {target.type}")

    @staticmethod
    def _read_diff_file(path: str) -> str:
        """Read a diff file from disk."""
        file_path = Path(path)
        if not file_path.exists():
            raise SCMError(f"Diff file not found: {path}")
        return file_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # Parallel LLM review with retry
    # ------------------------------------------------------------------ #

    async def _review_chunks(
        self,
        chunks: list[ReviewChunk],
    ) -> tuple[list[Finding], int, int, int, int]:
        """Send all chunks to the LLM in parallel with bounded concurrency.

        Returns:
            (all_findings, llm_calls, input_tokens, output_tokens, failed_count)
        """
        semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)

        async def _review_one(chunk: ReviewChunk) -> _ChunkResult:
            async with semaphore:
                return await self._review_single_chunk(chunk)

        results = await asyncio.gather(
            *(_review_one(c) for c in chunks),
            return_exceptions=True,
        )

        all_findings: list[Finding] = []
        total_llm_calls = 0
        total_input_tokens = 0
        total_output_tokens = 0
        failed_count = 0

        for r in results:
            if isinstance(r, BaseException):
                logger.error("Unexpected error in chunk review: %s", r)
                failed_count += 1
                continue
            all_findings.extend(r.findings)
            total_llm_calls += r.llm_calls
            total_input_tokens += r.input_tokens
            total_output_tokens += r.output_tokens
            if r.failed:
                failed_count += 1

        return (
            all_findings,
            total_llm_calls,
            total_input_tokens,
            total_output_tokens,
            failed_count,
        )

    async def _review_single_chunk(self, chunk: ReviewChunk) -> _ChunkResult:
        """Review a single chunk, with one retry on transient failure."""
        from codesentinel.patterns.schema import Pattern as PatternType

        patterns_context = "\n\n".join(
            f"### {p.metadata.name} ({p.metadata.severity.value})\n{p.spec.description}"
            for p in chunk.patterns
            if isinstance(p, PatternType)
        )

        system_prompt = build_system_prompt(
            confidence_threshold=self._config.min_confidence,
            mode=self._config.mode,
            patterns_context=patterns_context,
        )
        user_prompt = build_user_prompt(chunk)

        # First attempt
        response = await self._call_llm_with_retry(system_prompt, user_prompt)
        if response is None:
            return _ChunkResult(findings=[], llm_calls=2, failed=True)

        llm_calls = 1 if response.retry_count == 0 else 2
        findings = self._parse_findings(response.llm_response)

        return _ChunkResult(
            findings=findings,
            llm_calls=llm_calls,
            input_tokens=response.llm_response.input_tokens,
            output_tokens=response.llm_response.output_tokens,
        )

    async def _call_llm_with_retry(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> _LLMCallResult | None:
        """Call the LLM with a single retry on failure.

        Returns None if both attempts fail.
        """
        try:
            resp = await self._llm.review(system_prompt, user_prompt, response_format="json")
            return _LLMCallResult(llm_response=resp, retry_count=0)
        except LLMError as exc:
            logger.warning("LLM call failed (attempt 1): %s — retrying...", exc)

        # Exponential backoff: wait before retry
        await asyncio.sleep(_RETRY_BASE_DELAY)

        try:
            resp = await self._llm.review(system_prompt, user_prompt, response_format="json")
            return _LLMCallResult(llm_response=resp, retry_count=1)
        except LLMError as exc:
            logger.error("LLM call failed (attempt 2): %s — skipping chunk.", exc)
            return None

    # ------------------------------------------------------------------ #
    # Response parsing
    # ------------------------------------------------------------------ #

    def _parse_findings(self, response: LLMResponse) -> list[Finding]:
        """Parse LLM response content into Finding objects.

        Returns an empty list on malformed JSON (Section 20 compliance).
        """
        if not response.content or not response.content.strip():
            return []

        raw_dicts = PostProcessor.parse_llm_response(response.content)
        findings: list[Finding] = []

        for item in raw_dicts:
            finding = _dict_to_finding(item)
            if finding is not None:
                findings.append(finding)

        return findings

    # ------------------------------------------------------------------ #
    # Reporter dispatch
    # ------------------------------------------------------------------ #

    async def _dispatch_reporters(self, result: ReviewResult) -> None:
        """Send the result to all enabled reporters.

        Failures are logged but never prevent the review from completing.
        """
        for reporter in self._reporters:
            if not reporter.is_enabled():
                continue
            try:
                await reporter.report(result)
            except Exception as exc:
                logger.error(
                    "Reporter %s failed: %s",
                    type(reporter).__name__,
                    exc,
                )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _empty_result(
        self,
        target: ReviewTarget,
        start_ns: int,
        *,
        patterns_loaded: int = 0,
    ) -> ReviewResult:
        """Build a ReviewResult with zero findings."""
        duration_ms = (time.monotonic_ns() - start_ns) // 1_000_000
        return ReviewResult(
            findings=(),
            stats=ReviewStats(
                files_reviewed=0,
                patterns_loaded=patterns_loaded,
                patterns_matched=0,
                findings_total=0,
                duration_ms=duration_ms,
            ),
            target=target,
        )


# ---------------------------------------------------------------------- #
# Module-private data structures
# ---------------------------------------------------------------------- #


@dataclass(frozen=True)
class _ChunkResult:
    """Aggregated result from reviewing a single chunk."""

    findings: list[Finding]
    llm_calls: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    failed: bool = False


@dataclass(frozen=True)
class _LLMCallResult:
    """Wrapper for an LLM response with retry metadata."""

    llm_response: LLMResponse
    retry_count: int = 0


# ---------------------------------------------------------------------- #
# Pure helpers
# ---------------------------------------------------------------------- #


def _count_by_severity(findings: list[Finding]) -> dict[Severity, int]:
    """Count findings grouped by severity."""
    counts: dict[Severity, int] = {}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def _dict_to_finding(raw: dict[str, object]) -> Finding | None:
    """Safely convert a raw dict from the LLM into a Finding.

    Returns None if required fields are missing or invalid.
    """
    try:
        severity_str = str(raw.get("severity", "medium")).lower()
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM

        confidence_raw = raw.get("confidence", 0.5)
        confidence = float(str(confidence_raw)) if confidence_raw is not None else 0.5

        line_raw = raw.get("line", 0)
        line = int(str(line_raw))

        return Finding(
            pattern_name=str(raw.get("pattern_name", "unknown")),
            severity=severity,
            confidence=confidence,
            file=str(raw.get("file", "")),
            line=line,
            title=str(raw.get("title", "")),
            description=str(raw.get("description", "")),
            rationale=str(raw.get("rationale", "")),
            remediation=str(raw.get("remediation", "")),
            code_snippet=str(raw.get("code_snippet", "")),
        )
    except (TypeError, ValueError) as exc:
        logger.warning("Failed to parse finding dict: %s — %s", raw, exc)
        return None
