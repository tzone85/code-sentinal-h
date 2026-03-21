"""Tests for the GitHub SCM provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider
from codesentinel.scm.github import GitHubSCM

# --------------------------------------------------------------------------- #
# Construction & interface
# --------------------------------------------------------------------------- #


class TestGitHubSCMConstruction:
    """Verify construction and interface compliance."""

    def test_is_scm_provider(self) -> None:
        scm = GitHubSCM(token="tok")
        assert isinstance(scm, SCMProvider)

    def test_default_base_url(self) -> None:
        scm = GitHubSCM(token="tok")
        assert scm._base_url == "https://api.github.com"

    def test_custom_base_url(self) -> None:
        scm = GitHubSCM(token="tok", base_url="https://gh.corp.example.com/api/v3")
        assert scm._base_url == "https://gh.corp.example.com/api/v3"

    def test_base_url_trailing_slash_stripped(self) -> None:
        scm = GitHubSCM(token="tok", base_url="https://gh.corp.example.com/api/v3/")
        assert scm._base_url == "https://gh.corp.example.com/api/v3"


# --------------------------------------------------------------------------- #
# PR identifier parsing
# --------------------------------------------------------------------------- #


class TestParsePRIdentifier:
    """Verify parsing of various PR identifier formats."""

    def test_owner_repo_number_format(self) -> None:
        scm = GitHubSCM(token="tok")
        owner, repo, number = scm._parse_pr_identifier("octocat/hello-world#42")
        assert owner == "octocat"
        assert repo == "hello-world"
        assert number == 42

    def test_github_url_format(self) -> None:
        scm = GitHubSCM(token="tok")
        owner, repo, number = scm._parse_pr_identifier("https://github.com/octocat/hello-world/pull/42")
        assert owner == "octocat"
        assert repo == "hello-world"
        assert number == 42

    def test_github_url_with_trailing_slash(self) -> None:
        scm = GitHubSCM(token="tok")
        owner, repo, number = scm._parse_pr_identifier("https://github.com/octocat/hello-world/pull/42/")
        assert owner == "octocat"
        assert repo == "hello-world"
        assert number == 42

    def test_github_enterprise_url_format(self) -> None:
        scm = GitHubSCM(token="tok")
        owner, repo, number = scm._parse_pr_identifier("https://gh.corp.com/team/project/pull/99")
        assert owner == "team"
        assert repo == "project"
        assert number == 99

    def test_invalid_format_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse PR identifier"):
            scm._parse_pr_identifier("not-a-valid-identifier")

    def test_missing_number_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse PR identifier"):
            scm._parse_pr_identifier("octocat/hello-world")

    def test_non_numeric_number_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse PR identifier"):
            scm._parse_pr_identifier("octocat/hello-world#abc")


# --------------------------------------------------------------------------- #
# get_pr_info
# --------------------------------------------------------------------------- #


class TestGetPRInfo:
    """Verify PR info fetching."""

    async def test_returns_pr_info(self) -> None:
        scm = GitHubSCM(token="tok")
        response_data = {
            "number": 42,
            "title": "Add feature",
            "user": {"login": "octocat"},
            "base": {"ref": "main"},
            "head": {"ref": "feature-branch"},
            "html_url": "https://github.com/octocat/hello-world/pull/42",
            "diff_url": "https://github.com/octocat/hello-world/pull/42.diff",
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_info("octocat/hello-world#42")

        assert isinstance(result, PRInfo)
        assert result.number == 42
        assert result.title == "Add feature"
        assert result.author == "octocat"
        assert result.base_branch == "main"
        assert result.head_branch == "feature-branch"

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
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
            patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR info"),
        ):
            await scm.get_pr_info("octocat/hello-world#42")


# --------------------------------------------------------------------------- #
# get_pr_diff
# --------------------------------------------------------------------------- #


class TestGetPRDiff:
    """Verify PR diff fetching."""

    async def test_returns_diff_text(self) -> None:
        scm = GitHubSCM(token="tok")
        diff_text = "diff --git a/file.py b/file.py\n+new line"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = diff_text
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("octocat/hello-world#42")

        assert result == diff_text
        # Verify the Accept header was set for diff format
        call_kwargs = mock_client.get.call_args
        assert call_kwargs[1]["headers"]["Accept"] == "application/vnd.github.diff"

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
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
            patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch PR diff"),
        ):
            await scm.get_pr_diff("octocat/hello-world#42")


# --------------------------------------------------------------------------- #
# post_review_comment
# --------------------------------------------------------------------------- #


class TestPostReviewComment:
    """Verify inline review comment posting."""

    async def test_posts_comment_successfully(self) -> None:
        scm = GitHubSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "octocat/hello-world#42",
                file_path="src/main.py",
                line=10,
                body="Fix this issue",
                severity="high",
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"]
        assert body["path"] == "src/main.py"
        assert body["line"] == 10
        assert "Fix this issue" in body["body"]

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
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
            patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review comment"),
        ):
            await scm.post_review_comment(
                "octocat/hello-world#42",
                file_path="src/main.py",
                line=10,
                body="Fix",
                severity="high",
            )


# --------------------------------------------------------------------------- #
# post_review_summary
# --------------------------------------------------------------------------- #


class TestPostReviewSummary:
    """Verify review summary posting."""

    async def test_posts_approve_event(self) -> None:
        scm = GitHubSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "octocat/hello-world#42",
                body="Looks good!",
                approve=True,
                request_changes=False,
            )

        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"]
        assert body["event"] == "APPROVE"
        assert body["body"] == "Looks good!"

    async def test_posts_request_changes_event(self) -> None:
        scm = GitHubSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "octocat/hello-world#42",
                body="Please fix these issues",
                approve=False,
                request_changes=True,
            )

        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"]
        assert body["event"] == "REQUEST_CHANGES"

    async def test_posts_comment_event_when_neither(self) -> None:
        scm = GitHubSCM(token="tok")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "octocat/hello-world#42",
                body="FYI",
                approve=False,
                request_changes=False,
            )

        call_kwargs = mock_client.post.call_args
        body = call_kwargs[1]["json"]
        assert body["event"] == "COMMENT"

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitHubSCM(token="tok")
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
            patch("codesentinel.scm.github.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review summary"),
        ):
            await scm.post_review_summary(
                "octocat/hello-world#42",
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
        scm = GitHubSCM(token="tok")
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_local_diff("/repo", "main", "feature")
