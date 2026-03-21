"""Abstract base class for review result reporters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesentinel.core.models import ReviewResult


class Reporter(ABC):
    """Abstract interface for reporting review results.

    Concrete implementations may write to the terminal, post to GitHub,
    output JSON/SARIF files, etc.
    """

    @abstractmethod
    async def report(self, result: ReviewResult) -> None:
        """Emit the review result.

        Args:
            result: The complete review result to report.
        """

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if this reporter is enabled and should receive results."""
