"""JSON file reporter — writes ReviewResult as pretty-printed JSON."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from codesentinel.core.models import ReviewResult
from codesentinel.reporters.base import Reporter

logger = logging.getLogger(__name__)


class _ResultEncoder(json.JSONEncoder):
    """Handle Enum and datetime serialization for ReviewResult."""

    def default(self, o: object) -> object:
        if isinstance(o, Enum):
            return o.value
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def _serialize_result(result: ReviewResult) -> dict[str, object]:
    """Convert a ReviewResult to a JSON-safe dict."""
    target_dict = asdict(result.target)
    stats_raw = asdict(result.stats)
    # Convert Severity enum keys in findings_by_severity to strings
    stats_raw["findings_by_severity"] = {
        (k.value if isinstance(k, Enum) else str(k)): v for k, v in result.stats.findings_by_severity.items()
    }

    findings_list = []
    for finding in result.findings:
        f_dict = asdict(finding)
        f_dict["severity"] = finding.severity.value
        findings_list.append(f_dict)

    return {
        "version": "1.0",
        "timestamp": result.timestamp.isoformat(),
        "target": target_dict,
        "config": dict(result.config),
        "stats": stats_raw,
        "findings": findings_list,
    }


class JsonReporter(Reporter):
    """Write review results to a JSON file."""

    def __init__(self, *, output_path: str, enabled: bool = True) -> None:
        self._output_path = output_path
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    async def report(self, result: ReviewResult) -> None:
        """Serialize *result* and write to ``output_path``."""
        payload = _serialize_result(result)
        try:
            Path(self._output_path).write_text(
                json.dumps(payload, indent=2, cls=_ResultEncoder) + "\n",
                encoding="utf-8",
            )
        except OSError:
            logger.error("Failed to write JSON report to %s", self._output_path, exc_info=True)
