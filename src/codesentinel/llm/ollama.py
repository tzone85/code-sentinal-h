"""Ollama LLM provider implementation for local model inference."""

from __future__ import annotations

import time
from typing import Any

import httpx

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.base import LLMProvider

_DEFAULT_MODEL = "llama3"
_DEFAULT_TEMPERATURE = 0.2
_DEFAULT_NUM_PREDICT = 4096
_DEFAULT_BASE_URL = "http://localhost:11434"
_DEFAULT_TIMEOUT = 120.0
_MAX_CONTEXT_TOKENS = 32_000


class OllamaProvider(LLMProvider):
    """LLM provider backed by a local Ollama instance.

    Communicates with the ``/api/chat`` endpoint over HTTP.  No API key
    is required but the server must be reachable at ``base_url``.
    Raises ConfigError at init time if ``model`` is empty.
    """

    def __init__(
        self,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        model: str = _DEFAULT_MODEL,
        temperature: float = _DEFAULT_TEMPERATURE,
        num_predict: int = _DEFAULT_NUM_PREDICT,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if not model:
            raise ConfigError("Ollama model name must not be empty.")

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._num_predict = num_predict
        self._timeout = timeout

    async def review(
        self,
        system_prompt: str,
        user_prompt: str,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Send a review request to Ollama and return the parsed response."""
        start = time.monotonic()

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": self._temperature,
                "num_predict": self._num_predict,
            },
        }
        if response_format == "json":
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"Ollama API returned HTTP {exc.response.status_code}: {exc.response.text}") from exc
        except Exception as exc:
            raise LLMError(f"Ollama API call failed: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        message = data.get("message", {})
        content: str = message.get("content", "")

        input_tokens: int = data.get("prompt_eval_count", 0)
        output_tokens: int = data.get("eval_count", 0)

        return LLMResponse(
            content=content,
            model=data.get("model", self._model),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed_ms,
        )

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using len // 4 approximation."""
        return len(text) // 4

    def max_context_tokens(self) -> int:
        """Ollama models default to a 32K context window."""
        return _MAX_CONTEXT_TOKENS

    @property
    def name(self) -> str:
        return "ollama"
