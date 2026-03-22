"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesentinel.core.models import LLMResponse


class LLMProvider(ABC):
    """Abstract interface that all LLM providers must implement.

    Concrete providers (Claude, OpenAI, Ollama) inherit from this class
    and supply the actual API integration logic.
    """

    @abstractmethod
    async def review(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a review request to the LLM and return the response.

        Args:
            system_prompt: The system-level instructions for the LLM.
            user_prompt: The user-level prompt containing diff and patterns.
            response_format: Optional hint for desired output format (e.g. "json").

        Returns:
            An LLMResponse with the model's output and usage metadata.
        """

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of tokens in the given text.

        Each provider may use a different approximation ratio.
        """

    @abstractmethod
    def max_context_tokens(self) -> int:
        """Return the maximum context window size in tokens."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the provider name (e.g. 'claude', 'openai', 'ollama')."""
