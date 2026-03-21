"""Tests for the Azure DevOps SCM provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.azure_devops import AzureDevOpsSCM
from codesentinel.scm.base import SCMProvider

# --------------------------------------------------------------------------- #
# Construction & interface
# --------------------------------------------------------------------------- #


class TestAzureDevOpsSCMConstruction:
    """Verify construction and interface compliance."""

    def test_is_scm_provider(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        assert isinstance(scm, SCMProvider)

    def test_default_base_url(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        assert scm._base_url == "https://dev.azure.com"

    def test_custom_base_url(self) -> None:
        scm = AzureDevOpsSCM(token="pat", base_url="https://tfs.corp.com")
        assert scm._base_url == "https://tfs.corp.com"

    def test_base_url_trailing_slash_stripped(self) -> None:
        scm = AzureDevOpsSCM(token="pat", base_url="https://dev.azure.com/")
        assert scm._base_url == "https://dev.azure.com"

    def test_auth_header_is_basic(self) -> None:
        scm = AzureDevOpsSCM(token="my-pat")
        headers = scm._auth_headers()
        assert headers["Authorization"].startswith("Basic ")
        assert "Content-Type" in headers


# --------------------------------------------------------------------------- #
# PR identifier parsing
# --------------------------------------------------------------------------- #


class TestParsePRIdentifier:
    """Verify parsing of various PR identifier formats."""

    def test_short_format(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        org, project, repo, number = scm._parse_pr_identifier("myorg/myproject/myrepo#42")
        assert org == "myorg"
        assert project == "myproject"
        assert repo == "myrepo"
        assert number == 42

    def test_azure_devops_url_format(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        org, project, repo, number = scm._parse_pr_identifier(
            "https://dev.azure.com/myorg/myproject/_git/myrepo/pullrequest/42"
        )
        assert org == "myorg"
        assert project == "myproject"
        assert repo == "myrepo"
        assert number == 42

    def test_azure_devops_url_trailing_slash(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        org, project, repo, number = scm._parse_pr_identifier(
            "https://dev.azure.com/myorg/myproject/_git/myrepo/pullrequest/42/"
        )
        assert org == "myorg"
        assert project == "myproject"
        assert repo == "myrepo"
        assert number == 42

    def test_vsts_url_format(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        org, project, repo, number = scm._parse_pr_identifier(
            "https://myorg.visualstudio.com/myproject/_git/myrepo/pullrequest/99"
        )
        assert org == "myorg"
        assert project == "myproject"
        assert repo == "myrepo"
        assert number == 99

    def test_invalid_format_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        with pytest.raises(SCMError, match="Cannot parse Azure DevOps PR identifier"):
            scm._parse_pr_identifier("not-valid")

    def test_missing_number_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        with pytest.raises(SCMError, match="Cannot parse Azure DevOps PR identifier"):
            scm._parse_pr_identifier("myorg/myproject/myrepo")


# --------------------------------------------------------------------------- #
# get_pr_info
# --------------------------------------------------------------------------- #


class TestGetPRInfo:
    """Verify PR info fetching."""

    async def test_returns_pr_info(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        response_data = {
            "pullRequestId": 42,
            "title": "Add feature",
            "createdBy": {"uniqueName": "user@example.com"},
            "targetRefName": "refs/heads/main",
            "sourceRefName": "refs/heads/feature-branch",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_info("myorg/myproject/myrepo#42")

        assert isinstance(result, PRInfo)
        assert result.number == 42
        assert result.title == "Add feature"
        assert result.author == "user@example.com"
        assert result.base_branch == "main"
        assert result.head_branch == "feature-branch"

    async def test_strips_refs_heads_prefix(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        response_data = {
            "pullRequestId": 1,
            "title": "t",
            "createdBy": {"uniqueName": "u"},
            "targetRefName": "refs/heads/develop",
            "sourceRefName": "refs/heads/my-feature",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_info("myorg/myproject/myrepo#1")

        assert result.base_branch == "develop"
        assert result.head_branch == "my-feature"

    async def test_http_error_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
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
            patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR info"),
        ):
            await scm.get_pr_info("myorg/myproject/myrepo#42")


# --------------------------------------------------------------------------- #
# get_pr_diff
# --------------------------------------------------------------------------- #


class TestGetPRDiff:
    """Verify PR diff fetching via iterations API."""

    async def test_returns_diff_from_latest_iteration(self) -> None:
        scm = AzureDevOpsSCM(token="pat")

        iterations_response = MagicMock()
        iterations_response.json.return_value = {
            "value": [{"id": 1}, {"id": 2}]
        }
        iterations_response.raise_for_status = MagicMock()

        changes_response = MagicMock()
        changes_response.json.return_value = {
            "changeEntries": [
                {
                    "item": {"path": "/src/main.py"},
                    "changeType": "edit",
                }
            ]
        }
        changes_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.side_effect = [iterations_response, changes_response]
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("myorg/myproject/myrepo#42")

        assert "diff --git" in result
        assert "/src/main.py" in result
        # Verify iteration 2 (latest) was used
        second_call = mock_client.get.call_args_list[1]
        assert "/iterations/2/" in second_call[0][0]

    async def test_empty_iterations_returns_empty(self) -> None:
        scm = AzureDevOpsSCM(token="pat")

        mock_response = MagicMock()
        mock_response.json.return_value = {"value": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("myorg/myproject/myrepo#42")

        assert result == ""

    async def test_http_error_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
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
            patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR diff"),
        ):
            await scm.get_pr_diff("myorg/myproject/myrepo#42")


# --------------------------------------------------------------------------- #
# post_review_comment
# --------------------------------------------------------------------------- #


class TestPostReviewComment:
    """Verify inline comment thread posting."""

    async def test_posts_comment_successfully(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "myorg/myproject/myrepo#42",
                file_path="src/main.py",
                line=10,
                body="Fix this issue",
                severity="high",
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert "HIGH" in payload["comments"][0]["content"]
        assert payload["threadContext"]["filePath"] == "/src/main.py"
        assert payload["threadContext"]["rightFileStart"]["line"] == 10

    async def test_uses_threads_endpoint(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "myorg/myproject/myrepo#42",
                file_path="f.py",
                line=1,
                body="test",
                severity="low",
            )

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "/threads" in url

    async def test_http_error_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
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
            patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review comment"),
        ):
            await scm.post_review_comment(
                "myorg/myproject/myrepo#42",
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

    async def test_posts_summary_thread(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myorg/myproject/myrepo#42",
                body="Summary of findings",
                approve=False,
                request_changes=False,
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["comments"][0]["content"] == "Summary of findings"
        assert payload["status"] == 1  # Active

    async def test_approve_sets_fixed_status(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "myorg/myproject/myrepo#42",
                body="LGTM",
                approve=True,
                request_changes=False,
            )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["status"] == 4  # Fixed

    async def test_http_error_raises_scm_error(self) -> None:
        scm = AzureDevOpsSCM(token="pat")
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
            patch("codesentinel.scm.azure_devops.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review summary"),
        ):
            await scm.post_review_summary(
                "myorg/myproject/myrepo#42",
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
        scm = AzureDevOpsSCM(token="pat")
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_local_diff("/repo", "main", "feature")
