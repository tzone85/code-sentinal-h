"""OpenAI LLM provider implementation."""

from __future__ import annotations

import os
import time

import openai

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.base import LLMProvider

_DEFAULT_MODEL = "gpt-4o"
_DEFAULT_MAX_TOKENS = 4096
_DEFAULT_TEMPERATURE = 0.2
_MAX_CONTEXT_TOKENS = 128_000


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI API.

    Reads the API key from an environment variable (default: OPENAI_API_KEY).
    Supports custom ``base_url`` for Azure OpenAI or proxy endpoints.
    Raises ConfigError at init time if the key is not set.
    """

    def __init__(
        self,
        *,
        api_key_env: str = "OPENAI_API_KEY",
        model: str = _DEFAULT_MODEL,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = _DEFAULT_TEMPERATURE,
        base_url: str | None = None,
    ) -> None:
        api_key = os.environ.get(api_key_env)
        if not api_key:
            raise ConfigError(f"API key not found. Set the {api_key_env} environment variable.")

        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def review(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a review request to OpenAI and return the parsed response."""
        start = time.monotonic()

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            if response_format == "json":
                response = await self._client.chat.completions.create(  # type: ignore[call-overload]
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
            else:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                    messages=messages,  # type: ignore[arg-type]
                )
        except Exception as exc:
            raise LLMError(f"OpenAI API call failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        choice = response.choices[0] if response.choices else None
        content = choice.message.content or "" if choice else ""

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        return LLMResponse(
            content=content,
            model=response.model or self._model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
        )

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using len // 4 approximation for OpenAI."""
        return len(text) // 4

    def max_context_tokens(self) -> int:
        """OpenAI GPT-4o supports up to 128K context tokens."""
        return _MAX_CONTEXT_TOKENS

    @property
    def name(self) -> str:
        return "openai"
