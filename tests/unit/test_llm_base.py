"""Tests for the LLM provider abstraction layer."""

from __future__ import annotations

import pytest

from codesentinel.core.models import LLMResponse
from codesentinel.llm.base import LLMProvider


class TestLLMProviderInterface:
    """Verify that LLMProvider defines the correct abstract contract."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            LLMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_review(self) -> None:
        class Incomplete(LLMProvider):
            def estimate_tokens(self, text: str) -> int:
                return 0

            def max_context_tokens(self) -> int:
                return 0

            @property
            def name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_estimate_tokens(self) -> None:
        class Incomplete(LLMProvider):
            async def review(
                self,
                system_prompt: str,
                user_prompt: str,
                response_format: str | None = None,
            ) -> LLMResponse:
                return LLMResponse(content="", model="", input_tokens=0, output_tokens=0, latency_ms=0)

            def max_context_tokens(self) -> int:
                return 0

            @property
            def name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_max_context_tokens(self) -> None:
        class Incomplete(LLMProvider):
            async def review(
                self,
                system_prompt: str,
                user_prompt: str,
                response_format: str | None = None,
            ) -> LLMResponse:
                return LLMResponse(content="", model="", input_tokens=0, output_tokens=0, latency_ms=0)

            def estimate_tokens(self, text: str) -> int:
                return 0

            @property
            def name(self) -> str:
                return "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_name(self) -> None:
        class Incomplete(LLMProvider):
            async def review(
                self,
                system_prompt: str,
                user_prompt: str,
                response_format: str | None = None,
            ) -> LLMResponse:
                return LLMResponse(content="", model="", input_tokens=0, output_tokens=0, latency_ms=0)

            def estimate_tokens(self, text: str) -> int:
                return 0

            def max_context_tokens(self) -> int:
                return 0

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_complete_subclass_can_instantiate(self) -> None:
        class Complete(LLMProvider):
            async def review(
                self,
                system_prompt: str,
                user_prompt: str,
                response_format: str | None = None,
            ) -> LLMResponse:
                return LLMResponse(content="ok", model="test", input_tokens=1, output_tokens=1, latency_ms=10)

            def estimate_tokens(self, text: str) -> int:
                return len(text) // 4

            def max_context_tokens(self) -> int:
                return 100_000

            @property
            def name(self) -> str:
                return "test-provider"

        provider = Complete()
        assert provider.name == "test-provider"
        assert provider.estimate_tokens("hello world") == 2
        assert provider.max_context_tokens() == 100_000
