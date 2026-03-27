"""ReviewEngine — main pipeline orchestrator for CodeSentinel.

Coordinates the full review pipeline: diff extraction → parsing →
classification → pattern matching → context building → LLM review →
post-processing → reporting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from codesentinel.core.context_builder import ContextBuilder
from codesentinel.core.diff_parser import DiffParser
from codesentinel.core.enums import Severity
from codesentinel.core.file_classifier import FileClassifier
from codesentinel.llm.rate_limiter import RateLimiter
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

logger = logging.getLogger(__name__)

# Severity lookup for fail_on comparison
_SEVERITY_MAP: dict[str, Severity] = {s.value: s for s in Severity}

_RETRY_DELAY_SECONDS = 1.0


class ReviewEngine:
    """Orchestrates the full CodeSentinel review pipeline."""

    def __init__(
        self,
        config: dict[str, object],
        llm_provider: LLMProvider,
        scm_provider: object | None,
        pattern_registry: PatternRegistry,
        reporters: list[object],
    ) -> None:
        self._config = config
        self._llm_provider = llm_provider
        self._scm_provider = scm_provider
        self._pattern_registry = pattern_registry
        self._reporters = reporters

        self._diff_parser = DiffParser()
        self._file_classifier = FileClassifier()
        self._pattern_matcher = PatternMatcher()
        self._rate_limiter = RateLimiter(
            max_concurrent=int(config.get("max_concurrent_requests", 3)),
        )
        self._post_processor = PostProcessor(
            min_severity=_SEVERITY_MAP.get(
                str(config.get("min_severity", "medium")), Severity.MEDIUM
            ),
            min_confidence=float(config.get("min_confidence", 0.7)),
            max_findings=int(config.get("max_findings", 15)),
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def review(self, target: ReviewTarget) -> ReviewResult:
        """Run the full review pipeline.

        Returns a ReviewResult regardless of errors — the engine never
        raises to the caller.  Use ``compute_exit_code`` to map the
        result to a process exit code.
        """
        start_ms = _now_ms()

        # 1. Extract raw diff text
        raw_diff = await self._extract_diff(target)
        if raw_diff is None:
            return self._empty_result(target, start_ms)

        # 2. Parse diff
        parsed = self._diff_parser.parse(raw_diff)
        if not parsed.files:
            logger.info("Zero files in diff — nothing to review.")
            return self._empty_result(target, start_ms)

        # 3. Classify files
        classified = self._file_classifier.classify(list(parsed.files))

        # 4. Match patterns
        all_patterns = self._pattern_registry.all()
        matched = self._pattern_matcher.match(classified, all_patterns)
        if not matched:
            logger.info("No patterns match any files.")
            return self._empty_result(
                target,
                start_ms,
                files_reviewed=len(parsed.files),
                patterns_loaded=len(all_patterns),
            )

        # 5. Build chunks
        additional_context = str(self._config.get("additional_context", ""))
        context_builder = ContextBuilder()
        chunks = context_builder.build_chunks(classified, matched, additional_context)

        # 6. Send chunks to LLM in parallel
        llm_results = await self._review_chunks(chunks)

        # 7-8. Parse and post-process findings
        all_findings = self._process_llm_results(llm_results)

        # 9. Build stats
        total_input = sum(r.input_tokens for r in llm_results if r is not None)
        total_output = sum(r.output_tokens for r in llm_results if r is not None)
        llm_calls = sum(1 for r in llm_results if r is not None)
        stats = self._build_stats(
            files_reviewed=len(parsed.files),
            patterns_loaded=len(all_patterns),
            patterns_matched=len(matched),
            findings=all_findings,
            input_tokens=total_input,
            output_tokens=total_output,
            llm_calls=llm_calls,
            start_ms=start_ms,
        )

        result = ReviewResult(
            findings=tuple(all_findings),
            stats=stats,
            target=target,
        )

        # 10. Dispatch to reporters
        await self._dispatch_reporters(result)

        return result

    def compute_exit_code(self, result: ReviewResult) -> int:
        """Determine the process exit code from a review result.

        Returns:
            0 — no findings at or above ``fail_on`` severity.
            1 — findings found at or above ``fail_on`` severity.
        """
        fail_on = _SEVERITY_MAP.get(
            str(self._config.get("fail_on", "critical")), Severity.CRITICAL
        )
        for finding in result.findings:
            if finding.severity >= fail_on:
                return 1
        return 0

    # ------------------------------------------------------------------ #
    # Diff extraction
    # ------------------------------------------------------------------ #

    async def _extract_diff(self, target: ReviewTarget) -> str | None:
        """Extract raw diff text from the target source."""
        if target.type == "diff" and target.diff_path:
            return self._read_diff_file(target.diff_path)

        if target.type == "pr" and target.pr_url and self._scm_provider:
            try:
                return await self._scm_provider.get_pr_diff(target.pr_url)
            except Exception:
                logger.error("Failed to fetch PR diff for %s", target.pr_url, exc_info=True)
                return None

        if target.type in ("branch", "staged") and self._scm_provider:
            repo_path = target.repo_path or "."
            base = target.base_branch or "main"
            head = "--staged" if target.type == "staged" else (target.branch or "HEAD")
            try:
                return await self._scm_provider.get_local_diff(repo_path, base, head)
            except Exception:
                logger.error("Failed to get local diff", exc_info=True)
                return None

        logger.warning("No diff source available for target type: %s", target.type)
        return None

    @staticmethod
    def _read_diff_file(path: str) -> str | None:
        """Read a diff file from disk, returning None on failure."""
        file_path = Path(path)
        if not file_path.exists():
            logger.warning("Diff file not found: %s", path)
            return None
        try:
            return file_path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Cannot read diff file: %s", path)
            return None

    # ------------------------------------------------------------------ #
    # LLM interaction
    # ------------------------------------------------------------------ #

    async def _review_chunks(
        self, chunks: list[ReviewChunk]
    ) -> list[LLMResponse | None]:
        """Send all chunks to the LLM in parallel, returning responses.

        Each chunk gets one retry on failure.  Failed chunks yield None.
        """
        tasks = [self._review_single_chunk(chunk) for chunk in chunks]
        return list(await asyncio.gather(*tasks))

    async def _review_single_chunk(
        self, chunk: ReviewChunk
    ) -> LLMResponse | None:
        """Send a single chunk to the LLM with one retry on failure."""
        patterns_context = "\n\n".join(
            f"### {p.metadata.name}\n{p.spec.description}"
            for p in chunk.patterns
        )
        system_prompt = build_system_prompt(
            confidence_threshold=float(self._config.get("min_confidence", 0.7)),
            mode=str(self._config.get("mode", "coaching")),
            patterns_context=patterns_context,
        )
        user_prompt = build_user_prompt(chunk)

        for attempt in range(2):
            try:
                async with self._rate_limiter:
                    return await self._llm_provider.review(
                        system_prompt, user_prompt, "json"
                    )
            except Exception:
                if attempt == 0:
                    logger.warning(
                        "LLM call failed, retrying in %.1fs...", _RETRY_DELAY_SECONDS
                    )
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)
                else:
                    logger.error("LLM call failed after retry. Skipping chunk.")
        return None

    # ------------------------------------------------------------------ #
    # Post-processing
    # ------------------------------------------------------------------ #

    def _process_llm_results(
        self, llm_results: list[LLMResponse | None]
    ) -> list[Finding]:
        """Parse LLM responses and run the post-processing pipeline."""
        raw_findings: list[Finding] = []

        for response in llm_results:
            if response is None:
                continue
            parsed_dicts = PostProcessor.parse_llm_response(response.content)
            for d in parsed_dicts:
                finding = self._dict_to_finding(d)
                if finding is not None:
                    raw_findings.append(finding)

        return self._post_processor.process(raw_findings)

    @staticmethod
    def _dict_to_finding(data: dict[str, object]) -> Finding | None:
        """Convert a parsed dict to a Finding, or None if invalid."""
        try:
            severity_str = str(data.get("severity", "medium")).lower()
            severity = _SEVERITY_MAP.get(severity_str, Severity.MEDIUM)
            return Finding(
                pattern_name=str(data.get("pattern_name", "unknown")),
                severity=severity,
                confidence=float(data.get("confidence", 0.5)),
                file=str(data.get("file", "")),
                line=int(data.get("line", 0)),
                title=str(data.get("title", "")),
                description=str(data.get("description", "")),
                rationale=str(data.get("rationale", "")),
                remediation=str(data.get("remediation", "")),
                code_snippet=str(data.get("code_snippet", "")),
            )
        except (TypeError, ValueError):
            logger.warning("Failed to parse finding dict: %s", data)
            return None

    # ------------------------------------------------------------------ #
    # Reporter dispatch
    # ------------------------------------------------------------------ #

    async def _dispatch_reporters(self, result: ReviewResult) -> None:
        """Send results to all enabled reporters. Failures are logged, not raised."""
        for reporter in self._reporters:
            try:
                if hasattr(reporter, "is_enabled") and not reporter.is_enabled():
                    continue
                if hasattr(reporter, "report"):
                    await reporter.report(result)
            except Exception:
                logger.error(
                    "Reporter %s failed — review still completes.",
                    type(reporter).__name__,
                    exc_info=True,
                )

    # ------------------------------------------------------------------ #
    # Stats and result helpers
    # ------------------------------------------------------------------ #

    def _empty_result(
        self,
        target: ReviewTarget,
        start_ms: int,
        *,
        files_reviewed: int = 0,
        patterns_loaded: int = 0,
    ) -> ReviewResult:
        """Build a ReviewResult with zero findings."""
        stats = ReviewStats(
            files_reviewed=files_reviewed,
            patterns_loaded=patterns_loaded,
            patterns_matched=0,
            findings_total=0,
            duration_ms=_now_ms() - start_ms,
        )
        return ReviewResult(findings=(), stats=stats, target=target)

    @staticmethod
    def _build_stats(
        *,
        files_reviewed: int,
        patterns_loaded: int,
        patterns_matched: int,
        findings: list[Finding],
        input_tokens: int,
        output_tokens: int,
        llm_calls: int,
        start_ms: int,
    ) -> ReviewStats:
        """Build ReviewStats from pipeline results."""
        severity_counts: dict[Severity, int] = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        return ReviewStats(
            files_reviewed=files_reviewed,
            patterns_loaded=patterns_loaded,
            patterns_matched=patterns_matched,
            findings_total=len(findings),
            findings_by_severity=severity_counts,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            llm_calls=llm_calls,
            duration_ms=_now_ms() - start_ms,
        )


def _now_ms() -> int:
    """Current time in milliseconds."""
    return int(time.monotonic() * 1000)
