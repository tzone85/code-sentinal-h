"""Tests for the Ollama LLM provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from codesentinel.core.exceptions import ConfigError, LLMError
from codesentinel.core.models import LLMResponse
from codesentinel.llm.ollama import OllamaProvider


def _make_ollama_response(
    content: str = '[{"finding": "test"}]',
    model: str = "llama3",
    prompt_eval_count: int = 100,
    eval_count: int = 50,
) -> dict[str, object]:
    """Build a dict matching the Ollama /api/chat JSON response shape."""
    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
        "done": True,
    }


# --------------------------------------------------------------------------- #
# Init tests
# --------------------------------------------------------------------------- #


class TestOllamaProviderInit:
    """Test OllamaProvider initialization and configuration."""

    def test_creates_provider_with_defaults(self) -> None:
        provider = OllamaProvider()
        assert provider.name == "ollama"
        assert provider._model == "llama3"
        assert provider._base_url == "http://localhost:11434"

    def test_raises_config_error_for_empty_model(self) -> None:
        with pytest.raises(ConfigError, match="model name"):
            OllamaProvider(model="")

    def test_custom_base_url(self) -> None:
        provider = OllamaProvider(base_url="http://gpu-server:11434")
        assert provider._base_url == "http://gpu-server:11434"

    def test_strips_trailing_slash_from_base_url(self) -> None:
        provider = OllamaProvider(base_url="http://gpu-server:11434/")
        assert provider._base_url == "http://gpu-server:11434"

    def test_custom_model(self) -> None:
        provider = OllamaProvider(model="codellama")
        assert provider._model == "codellama"

    def test_custom_temperature(self) -> None:
        provider = OllamaProvider(temperature=0.8)
        assert provider._temperature == 0.8

    def test_custom_num_predict(self) -> None:
        provider = OllamaProvider(num_predict=8192)
        assert provider._num_predict == 8192

    def test_custom_timeout(self) -> None:
        provider = OllamaProvider(timeout=300.0)
        assert provider._timeout == 300.0


# --------------------------------------------------------------------------- #
# Token tests
# --------------------------------------------------------------------------- #


class TestOllamaProviderTokens:
    """Test token estimation and context limits."""

    def test_estimate_tokens_uses_len_div_4(self) -> None:
        provider = OllamaProvider()
        text = "a" * 400
        assert provider.estimate_tokens(text) == 100

    def test_estimate_tokens_empty_string(self) -> None:
        provider = OllamaProvider()
        assert provider.estimate_tokens("") == 0

    def test_max_context_tokens_returns_32k(self) -> None:
        provider = OllamaProvider()
        assert provider.max_context_tokens() == 32_000


# --------------------------------------------------------------------------- #
# Review tests
# --------------------------------------------------------------------------- #


class TestOllamaProviderReview:
    """Test the review method with mocked httpx client."""

    async def test_review_returns_llm_response(self) -> None:
        provider = OllamaProvider()
        fake_data = _make_ollama_response('[{"pattern": "test"}]')

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            result = await provider.review("system prompt", "user prompt")

        assert isinstance(result, LLMResponse)
        assert result.content == '[{"pattern": "test"}]'
        assert result.model == "llama3"
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.latency_ms >= 0

    async def test_review_sends_correct_payload(self) -> None:
        provider = OllamaProvider(model="codellama", temperature=0.5, num_predict=2048)
        fake_data = _make_ollama_response("[]", model="codellama")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            await provider.review("sys", "usr")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["model"] == "codellama"
        assert payload["stream"] is False
        assert payload["messages"][0] == {"role": "system", "content": "sys"}
        assert payload["messages"][1] == {"role": "user", "content": "usr"}
        assert payload["options"]["temperature"] == 0.5
        assert payload["options"]["num_predict"] == 2048

    async def test_review_sends_json_format_when_requested(self) -> None:
        provider = OllamaProvider()
        fake_data = _make_ollama_response("[]")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            await provider.review("sys", "usr", response_format="json")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["format"] == "json"

    async def test_review_omits_format_when_none(self) -> None:
        provider = OllamaProvider()
        fake_data = _make_ollama_response("[]")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            await provider.review("sys", "usr")

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert "format" not in payload

    async def test_review_raises_llm_error_on_connection_failure(self) -> None:
        provider = OllamaProvider()

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(LLMError, match="Ollama API call failed"),
        ):
            await provider.review("sys", "usr")

    async def test_review_raises_llm_error_on_http_error(self) -> None:
        provider = OllamaProvider()

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp)

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(LLMError, match="HTTP 500"),
        ):
            await provider.review("sys", "usr")

    async def test_review_handles_empty_message(self) -> None:
        provider = OllamaProvider()
        fake_data = _make_ollama_response("")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            result = await provider.review("sys", "usr")

        assert result.content == ""

    async def test_review_handles_missing_token_counts(self) -> None:
        provider = OllamaProvider()
        fake_data = {
            "model": "llama3",
            "message": {"role": "assistant", "content": "hello"},
            "done": True,
        }

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            result = await provider.review("sys", "usr")

        assert result.input_tokens == 0
        assert result.output_tokens == 0

    async def test_review_posts_to_correct_url(self) -> None:
        provider = OllamaProvider(base_url="http://gpu:11434")
        fake_data = _make_ollama_response("[]")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            await provider.review("sys", "usr")

        url = mock_client.post.call_args[0][0]
        assert url == "http://gpu:11434/api/chat"

    async def test_review_passes_timeout_to_client(self) -> None:
        """Timeout value is forwarded to httpx.AsyncClient."""
        provider = OllamaProvider(timeout=300.0)
        fake_data = _make_ollama_response("[]")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await provider.review("sys", "usr")

        mock_cls.assert_called_once_with(timeout=300.0)

    async def test_review_handles_missing_message_key(self) -> None:
        """Response with no 'message' key returns empty content."""
        provider = OllamaProvider()
        fake_data = {"model": "llama3", "done": True}

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            result = await provider.review("sys", "usr")

        assert result.content == ""

    async def test_review_falls_back_to_configured_model(self) -> None:
        """When response has no 'model' key, uses configured model name."""
        provider = OllamaProvider(model="codellama")
        fake_data = {
            "message": {"role": "assistant", "content": "hello"},
            "done": True,
        }

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            result = await provider.review("sys", "usr")

        assert result.model == "codellama"

    async def test_review_handles_trailing_slash_in_url(self) -> None:
        """URL construction works with trailing-slash-stripped base_url."""
        provider = OllamaProvider(base_url="http://localhost:11434/")
        fake_data = _make_ollama_response("[]")

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = fake_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.llm.ollama.httpx.AsyncClient", return_value=mock_client):
            await provider.review("sys", "usr")

        url = mock_client.post.call_args[0][0]
        assert url == "http://localhost:11434/api/chat"
