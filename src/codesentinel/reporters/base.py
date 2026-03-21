"""Abstract base class for review result reporters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesentinel.core.models import ReviewResult


class Reporter(ABC):
    """Interface that all reporters must implement."""

    @abstractmethod
    async def report(self, result: ReviewResult) -> None:
        """Publish or display the review result.

        Args:
            result: The complete review result to report.
        """

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if this reporter should run."""
