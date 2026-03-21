"""Tests for the OpenAI LLM provider."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.openai_provider import OpenAIProvider

# --------------------------------------------------------------------------- #
# Fakes matching the openai SDK response shape
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _FakeUsage:
    prompt_tokens: int = 100
    completion_tokens: int = 50
    total_tokens: int = 150


@dataclass(frozen=True)
class _FakeMessage:
    role: str = "assistant"
    content: str = '[{"finding": "test"}]'


@dataclass(frozen=True)
class _FakeChoice:
    index: int = 0
    message: _FakeMessage = _FakeMessage()
    finish_reason: str = "stop"


@dataclass(frozen=True)
class _FakeResponse:
    id: str = "chatcmpl-123"
    model: str = "gpt-4o"
    choices: tuple[_FakeChoice, ...] = (_FakeChoice(),)
    usage: _FakeUsage = _FakeUsage()


def _make_fake_response(text: str = '[{"finding": "test"}]') -> _FakeResponse:
    return _FakeResponse(
        choices=(_FakeChoice(message=_FakeMessage(content=text)),),
    )


# --------------------------------------------------------------------------- #
# Init tests
# --------------------------------------------------------------------------- #


class TestOpenAIProviderInit:
    """Test OpenAIProvider initialization and configuration."""

    def test_raises_config_error_when_api_key_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ConfigError, match="API key"):
            OpenAIProvider()

    def test_raises_config_error_for_custom_env_var_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True), pytest.raises(ConfigError, match="MY_OPENAI_KEY"):
            OpenAIProvider(api_key_env="MY_OPENAI_KEY")

    def test_creates_provider_with_env_var(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-key"}):
            provider = OpenAIProvider()
            assert provider.name == "openai"

    def test_creates_provider_with_custom_env_var(self) -> None:
        with patch.dict("os.environ", {"MY_KEY": "sk-test-key"}):
            provider = OpenAIProvider(api_key_env="MY_KEY")
            assert provider.name == "openai"

    def test_custom_model(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider(model="gpt-4-turbo")
            assert provider._model == "gpt-4-turbo"

    def test_custom_max_tokens(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider(max_tokens=8192)
            assert provider._max_tokens == 8192

    def test_custom_temperature(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider(temperature=0.5)
            assert provider._temperature == 0.5

    def test_custom_base_url(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider(base_url="https://my-proxy.example.com/v1")
            assert provider._client.base_url is not None


# --------------------------------------------------------------------------- #
# Token tests
# --------------------------------------------------------------------------- #


class TestOpenAIProviderTokens:
    """Test token estimation and context limits."""

    def test_estimate_tokens_uses_len_div_4(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider()
            text = "a" * 400
            assert provider.estimate_tokens(text) == 100

    def test_estimate_tokens_empty_string(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider()
            assert provider.estimate_tokens("") == 0

    def test_max_context_tokens_returns_128k(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            provider = OpenAIProvider()
            assert provider.max_context_tokens() == 128_000


# --------------------------------------------------------------------------- #
# Review tests
# --------------------------------------------------------------------------- #


class TestOpenAIProviderReview:
    """Test the review method with mocked OpenAI client."""

    @pytest.fixture()
    def provider(self) -> OpenAIProvider:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            return OpenAIProvider()

    async def test_review_returns_llm_response(self, provider: OpenAIProvider) -> None:
        fake = _make_fake_response('[{"pattern": "test"}]')
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        result = await provider.review("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.content == '[{"pattern": "test"}]'
        assert result.model == "gpt-4o"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.latency_ms >= 0

    async def test_review_passes_system_and_user_messages(self, provider: OpenAIProvider) -> None:
        fake = _make_fake_response("[]")
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        await provider.review("sys prompt", "usr prompt")

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        assert messages[0] == {"role": "system", "content": "sys prompt"}
        assert messages[1] == {"role": "user", "content": "usr prompt"}

    async def test_review_sets_json_response_format(self, provider: OpenAIProvider) -> None:
        fake = _make_fake_response("[]")
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        await provider.review("sys", "usr", response_format="json")

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    async def test_review_omits_response_format_when_none(self, provider: OpenAIProvider) -> None:
        fake = _make_fake_response("[]")
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        await provider.review("sys", "usr")

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert "response_format" not in call_kwargs

    async def test_review_measures_latency(self, provider: OpenAIProvider) -> None:
        fake = _make_fake_response("[]")
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        result = await provider.review("sys", "usr")

        assert result.latency_ms >= 0

    async def test_review_raises_llm_error_on_api_failure(self, provider: OpenAIProvider) -> None:
        provider._client.chat.completions.create = AsyncMock(
            side_effect=Exception("API down"),
        )

        with pytest.raises(LLMError, match="OpenAI API"):
            await provider.review("sys", "usr")

    async def test_review_handles_empty_choices(self, provider: OpenAIProvider) -> None:
        fake = _FakeResponse(choices=())
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        result = await provider.review("sys", "usr")

        assert result.content == ""

    async def test_review_handles_none_content(self, provider: OpenAIProvider) -> None:
        fake = _FakeResponse(
            choices=(_FakeChoice(message=_FakeMessage(content=None)),),  # type: ignore[arg-type]
        )
        provider._client.chat.completions.create = AsyncMock(return_value=fake)

        result = await provider.review("sys", "usr")

        assert result.content == ""
