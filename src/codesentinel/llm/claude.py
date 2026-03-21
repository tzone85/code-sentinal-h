"""Claude (Anthropic) LLM provider implementation."""

from __future__ import annotations

import os
import time

import anthropic

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.base import LLMProvider

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.2
_MAX_CONTEXT_TOKENS = 200_000


class ClaudeProvider(LLMProvider):
    """LLM provider backed by the Anthropic Claude API.

    Reads the API key from an environment variable (default: ANTHROPIC_API_KEY).
    Raises ConfigError at init time if the key is not set.
    """

    def __init__(
        self,
        *,
        api_key_env: str = "ANTHROPIC_API_KEY",
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> None:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ConfigError(f"API key not found. Set the {api_key_env} environment variable.")

        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def review(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a review request to Claude and return the parsed response."""
        start = time.monotonic()
        try:
            message = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        except Exception as exc:
            raise LLMError(f"Claude API call failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        content = ""
        for block in message.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            latency_ms=elapsed_ms,
        )

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using len // 3 approximation for Claude."""
        return len(text) // 3

    def max_context_tokens(self) -> int:
        """Claude supports up to 200K context tokens."""
        return _MAX_CONTEXT_TOKENS

    @property
    def name(self) -> str:
        return "claude"
