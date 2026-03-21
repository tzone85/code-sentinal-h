"""Tests for the Bitbucket SCM provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider
from codesentinel.scm.bitbucket import BitbucketSCM

# --------------------------------------------------------------------------- #
# Construction & interface
# --------------------------------------------------------------------------- #


class TestBitbucketSCMConstruction:
    """Verify construction and interface compliance."""

    def test_is_scm_provider(self) -> None:
        scm = BitbucketSCM(token="tok")
        assert isinstance(scm, SCMProvider)

    def test_default_base_url(self) -> None:
        scm = BitbucketSCM(token="tok")
        assert scm._base_url == "https://api.bitbucket.org/2.0"

    def test_custom_base_url(self) -> None:
        scm = BitbucketSCM(token="tok", base_url="https://bb.corp.com/api/2.0")
        assert scm._base_url == "https://bb.corp.com/api/2.0"

    def test_base_url_trailing_slash_stripped(self) -> None:
        scm = BitbucketSCM(token="tok", base_url="https://api.bitbucket.org/2.0/")
        assert scm._base_url == "https://api.bitbucket.org/2.0"

    def test_bearer_auth_without_username(self) -> None:
        scm = BitbucketSCM(token="my-token")
        headers = scm._auth_headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_basic_auth_with_username(self) -> None:
        scm = BitbucketSCM(token="app-password", username="myuser")
        headers = scm._auth_headers()
        assert headers["Authorization"].startswith("Basic ")


# --------------------------------------------------------------------------- #
# PR identifier parsing
# --------------------------------------------------------------------------- #


class TestParsePRIdentifier:
    """Verify parsing of various PR identifier formats."""

    def test_short_format(self) -> None:
        scm = BitbucketSCM(token="tok")
        workspace, repo, number = scm._parse_pr_identifier("myworkspace/myrepo#42")
        assert workspace == "myworkspace"
        assert repo == "myrepo"
        assert number == 42

    def test_bitbucket_url_format(self) -> None:
        scm = BitbucketSCM(token="tok")
        workspace, repo, number = scm._parse_pr_identifier(
            "https://bitbucket.org/myworkspace/myrepo/pull-requests/42"
        )
        assert workspace == "myworkspace"
        assert repo == "myrepo"
        assert number == 42

    def test_bitbucket_url_trailing_slash(self) -> None:
        scm = BitbucketSCM(token="tok")
        workspace, repo, number = scm._parse_pr_identifier(
            "https://bitbucket.org/myworkspace/myrepo/pull-requests/42/"
        )
        assert workspace == "myworkspace"
        assert repo == "myrepo"
        assert number == 42

    def test_invalid_format_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse Bitbucket PR identifier"):
            scm._parse_pr_identifier("not-valid")

    def test_missing_number_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse Bitbucket PR identifier"):
            scm._parse_pr_identifier("myworkspace/myrepo")


# --------------------------------------------------------------------------- #
# get_pr_info
# --------------------------------------------------------------------------- #


class TestGetPRInfo:
    """Verify PR info fetching."""

    async def test_returns_pr_info(self) -> None:
        scm = BitbucketSCM(token="tok")
        response_data = {
            "id": 42,
            "title": "Add feature",
            "author": {"display_name": "John Doe"},
            "source": {"branch": {"name": "feature-branch"}},
            "destination": {"branch": {"name": "main"}},
            "links": {
                "html": {"href": "https://bitbucket.org/ws/repo/pull-requests/42"},
                "diff": {"href": "https://api.bitbucket.org/2.0/repositories/ws/repo/pullrequests/42/diff"},
            },
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_info("myworkspace/myrepo#42")

        assert isinstance(result, PRInfo)
        assert result.number == 42
        assert result.title == "Add feature"
        assert result.author == "John Doe"
        assert result.base_branch == "main"
        assert result.head_branch == "feature-branch"

    async def test_http_error_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR info"),
        ):
            await scm.get_pr_info("myworkspace/myrepo#42")


# --------------------------------------------------------------------------- #
# get_pr_diff
# --------------------------------------------------------------------------- #


class TestGetPRDiff:
    """Verify PR diff fetching."""

    async def test_returns_diff_text(self) -> None:
        scm = BitbucketSCM(token="tok")
        diff_text = "diff --git a/file.py b/file.py\n+new line"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = diff_text
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("myworkspace/myrepo#42")

        assert result == diff_text

    async def test_uses_diff_endpoint(self) -> None:
        scm = BitbucketSCM(token="tok")

        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.get_pr_diff("myworkspace/myrepo#42")

        call_args = mock_client.get.call_args
        url = call_args[0][0]
        assert "/diff" in url

    async def test_http_error_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR diff"),
        ):
            await scm.get_pr_diff("myworkspace/myrepo#42")


# --------------------------------------------------------------------------- #
# post_review_comment
# --------------------------------------------------------------------------- #


class TestPostReviewComment:
    """Verify inline comment posting."""

    async def test_posts_comment_successfully(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "myworkspace/myrepo#42",
                file_path="src/main.py",
                line=10,
                body="Fix this issue",
                severity="high",
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert "HIGH" in payload["content"]["raw"]
        assert payload["inline"]["path"] == "src/main.py"
        assert payload["inline"]["to"] == 10

    async def test_uses_comments_endpoint(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "myworkspace/myrepo#42",
                file_path="f.py",
                line=1,
                body="test",
                severity="low",
            )

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "/comments" in url

    async def test_http_error_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unprocessable", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review comment"),
        ):
            await scm.post_review_comment(
                "myworkspace/myrepo#42",
                file_path="f.py",
                line=1,
                body="test",
                severity="high",
            )


# --------------------------------------------------------------------------- #
# post_review_summary
# --------------------------------------------------------------------------- #


class TestPostReviewSummary:
    """Verify review summary posting."""

    async def test_posts_summary_comment(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myworkspace/myrepo#42",
                body="Looks good!",
                approve=False,
                request_changes=False,
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["content"]["raw"] == "Looks good!"

    async def test_approve_calls_approve_endpoint(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myworkspace/myrepo#42",
                body="LGTM",
                approve=True,
                request_changes=False,
            )

        assert mock_client.post.call_count == 2
        second_call = mock_client.post.call_args_list[1]
        assert "/approve" in second_call[0][0]

    async def test_request_changes_calls_request_changes_endpoint(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myworkspace/myrepo#42",
                body="Fix issues",
                approve=False,
                request_changes=True,
            )

        assert mock_client.post.call_count == 2
        second_call = mock_client.post.call_args_list[1]
        assert "/request-changes" in second_call[0][0]

    async def test_no_approve_no_request_changes_posts_only_comment(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myworkspace/myrepo#42",
                body="FYI",
                approve=False,
                request_changes=False,
            )

        assert mock_client.post.call_count == 1

    async def test_http_error_raises_scm_error(self) -> None:
        scm = BitbucketSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("codesentinel.scm.bitbucket.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review summary"),
        ):
            await scm.post_review_summary(
                "myworkspace/myrepo#42",
                body="Review",
                approve=False,
                request_changes=False,
            )


# --------------------------------------------------------------------------- #
# get_local_diff (not applicable)
# --------------------------------------------------------------------------- #


class TestGetLocalDiff:
    """Verify that get_local_diff is not supported."""

    async def test_raises_not_implemented(self) -> None:
        scm = BitbucketSCM(token="tok")
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_local_diff("/repo", "main", "feature")
