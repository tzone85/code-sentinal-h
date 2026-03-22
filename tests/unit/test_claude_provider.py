"""Tests for the Claude (Anthropic) LLM provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.claude import ClaudeProvider


@dataclass(frozen=True)
class _FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass(frozen=True)
class _FakeMessage:
    id: str = "msg_123"
    model: str = "claude-sonnet-4-20250514"
    content: tuple[Any, ...] = ()
    usage: _FakeUsage = _FakeUsage()

    @staticmethod
    def _default_content() -> tuple[Any, ...]:
        @dataclass(frozen=True)
        class TextBlock:
            type: str = "text"
            text: str = '[{"finding": "test"}]'

        return (TextBlock(),)


def _make_fake_message(text: str = '[{"finding": "test"}]') -> _FakeMessage:
    @dataclass(frozen=True)
    class TextBlock:
        type: str = "text"
        text: str = ""

    return _FakeMessage(content=(TextBlock(text=text),))


class TestClaudeProviderInit:
    """Test ClaudeProvider initialization and configuration."""

    def test_raises_config_error_when_api_key_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ConfigError, match="API key"):
            ClaudeProvider()

    def test_raises_config_error_for_custom_env_var_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ConfigError, match="MY_CLAUDE_KEY"):
            ClaudeProvider(api_key_env="MY_CLAUDE_KEY")

    def test_creates_provider_with_env_var(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}):
            provider = ClaudeProvider()
            assert provider.name == "claude"

    def test_creates_provider_with_custom_env_var(self) -> None:
        with patch.dict("os.environ", {"MY_KEY": "sk-test-key"}):
            provider = ClaudeProvider(api_key_env="MY_KEY")
            assert provider.name == "claude"

    def test_custom_model(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider(model="claude-opus-4-20250514")
            assert provider._model == "claude-opus-4-20250514"

    def test_custom_max_tokens(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider(max_tokens=8192)
            assert provider._max_tokens == 8192

    def test_custom_temperature(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider(temperature=0.5)
            assert provider._temperature == 0.5


class TestClaudeProviderTokens:
    """Test token estimation and context limits."""

    def test_estimate_tokens_uses_len_div_3(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider()
            text = "a" * 300
            assert provider.estimate_tokens(text) == 100

    def test_estimate_tokens_empty_string(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider()
            assert provider.estimate_tokens("") == 0

    def test_max_context_tokens_returns_200k(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            provider = ClaudeProvider()
            assert provider.max_context_tokens() == 200_000


class TestClaudeProviderReview:
    """Test the review method with mocked Anthropic client."""

    @pytest.fixture()
    def provider(self) -> ClaudeProvider:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test"}):
            return ClaudeProvider()

    async def test_review_returns_llm_response(self, provider: ClaudeProvider) -> None:
        fake_msg = _make_fake_message('[{"pattern": "test"}]')
        provider._client.messages.create = AsyncMock(return_value=fake_msg)

        result = await provider.review("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.content == '[{"pattern": "test"}]'
        assert result.model == "claude-sonnet-4-20250514"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.latency_ms >= 0

    async def test_review_passes_correct_params(self, provider: ClaudeProvider) -> None:
        fake_msg = _make_fake_message("[]")
        provider._client.messages.create = AsyncMock(return_value=fake_msg)

        await provider.review("sys", "usr", response_format="json")

        call_kwargs = provider._client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "sys"
        assert call_kwargs["model"] == provider._model
        assert call_kwargs["max_tokens"] == provider._max_tokens
        assert call_kwargs["temperature"] == provider._temperature
        assert any(msg["content"] == "usr" for msg in call_kwargs["messages"])

    async def test_review_measures_latency(self, provider: ClaudeProvider) -> None:
        fake_msg = _make_fake_message("[]")
        provider._client.messages.create = AsyncMock(return_value=fake_msg)

        result = await provider.review("sys", "usr")

        assert result.latency_ms >= 0

    async def test_review_raises_llm_error_on_api_failure(self, provider: ClaudeProvider) -> None:
        provider._client.messages.create = AsyncMock(side_effect=Exception("API down"))

        with pytest.raises(LLMError, match="Claude API"):
            await provider.review("sys", "usr")

    async def test_review_handles_empty_content(self, provider: ClaudeProvider) -> None:
        fake_msg = _make_fake_message("")
        provider._client.messages.create = AsyncMock(return_value=fake_msg)

        result = await provider.review("sys", "usr")

        assert result.content == ""
