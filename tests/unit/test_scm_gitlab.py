"""Tests for the GitLab SCM provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider
from codesentinel.scm.gitlab import GitLabSCM

# --------------------------------------------------------------------------- #
# Construction & interface
# --------------------------------------------------------------------------- #


class TestGitLabSCMConstruction:
    """Verify construction and interface compliance."""

    def test_is_scm_provider(self) -> None:
        scm = GitLabSCM(token="tok")
        assert isinstance(scm, SCMProvider)

    def test_default_base_url(self) -> None:
        scm = GitLabSCM(token="tok")
        assert scm._base_url == "https://gitlab.com"

    def test_custom_base_url(self) -> None:
        scm = GitLabSCM(token="tok", base_url="https://gitlab.corp.example.com")
        assert scm._base_url == "https://gitlab.corp.example.com"

    def test_base_url_trailing_slash_stripped(self) -> None:
        scm = GitLabSCM(token="tok", base_url="https://gitlab.corp.example.com/")
        assert scm._base_url == "https://gitlab.corp.example.com"

    def test_auth_header_uses_private_token(self) -> None:
        scm = GitLabSCM(token="my-secret-token")
        headers = scm._auth_headers()
        assert headers["PRIVATE-TOKEN"] == "my-secret-token"


# --------------------------------------------------------------------------- #
# MR identifier parsing
# --------------------------------------------------------------------------- #


class TestParseMRIdentifier:
    """Verify parsing of various MR identifier formats."""

    def test_short_format(self) -> None:
        scm = GitLabSCM(token="tok")
        project, number = scm._parse_mr_identifier("mygroup/myproject!42")
        assert project == "mygroup/myproject"
        assert number == 42

    def test_nested_group_short_format(self) -> None:
        scm = GitLabSCM(token="tok")
        project, number = scm._parse_mr_identifier("org/team/project!99")
        assert project == "org/team/project"
        assert number == 99

    def test_gitlab_url_format(self) -> None:
        scm = GitLabSCM(token="tok")
        project, number = scm._parse_mr_identifier(
            "https://gitlab.com/mygroup/myproject/-/merge_requests/42"
        )
        assert project == "mygroup/myproject"
        assert number == 42

    def test_gitlab_url_with_trailing_slash(self) -> None:
        scm = GitLabSCM(token="tok")
        project, number = scm._parse_mr_identifier(
            "https://gitlab.com/mygroup/myproject/-/merge_requests/42/"
        )
        assert project == "mygroup/myproject"
        assert number == 42

    def test_self_hosted_url_format(self) -> None:
        scm = GitLabSCM(token="tok")
        project, number = scm._parse_mr_identifier(
            "https://git.corp.com/team/project/-/merge_requests/7"
        )
        assert project == "team/project"
        assert number == 7

    def test_invalid_format_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse MR identifier"):
            scm._parse_mr_identifier("not-valid")

    def test_missing_number_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
        with pytest.raises(SCMError, match="Cannot parse MR identifier"):
            scm._parse_mr_identifier("mygroup/myproject")

    def test_encode_project_replaces_slashes(self) -> None:
        assert GitLabSCM._encode_project("group/project") == "group%2Fproject"
        assert GitLabSCM._encode_project("org/team/repo") == "org%2Fteam%2Frepo"


# --------------------------------------------------------------------------- #
# get_pr_info
# --------------------------------------------------------------------------- #


class TestGetPRInfo:
    """Verify MR info fetching."""

    async def test_returns_pr_info(self) -> None:
        scm = GitLabSCM(token="tok")
        response_data = {
            "iid": 42,
            "title": "Add new feature",
            "author": {"username": "jdoe"},
            "target_branch": "main",
            "source_branch": "feature-branch",
            "web_url": "https://gitlab.com/mygroup/myproject/-/merge_requests/42",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_info("mygroup/myproject!42")

        assert isinstance(result, PRInfo)
        assert result.number == 42
        assert result.title == "Add new feature"
        assert result.author == "jdoe"
        assert result.base_branch == "main"
        assert result.head_branch == "feature-branch"
        assert "merge_requests/42" in result.url

    async def test_uses_correct_api_url(self) -> None:
        scm = GitLabSCM(token="tok")
        response_data = {
            "iid": 1,
            "title": "t",
            "author": {"username": "u"},
            "target_branch": "main",
            "source_branch": "feat",
            "web_url": "https://gitlab.com/g/p/-/merge_requests/1",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.get_pr_info("mygroup/myproject!1")

        call_args = mock_client.get.call_args
        url = call_args[0][0]
        assert "mygroup%2Fmyproject" in url
        assert "/merge_requests/1" in url

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
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
            patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch MR info"),
        ):
            await scm.get_pr_info("mygroup/myproject!42")


# --------------------------------------------------------------------------- #
# get_pr_diff
# --------------------------------------------------------------------------- #


class TestGetPRDiff:
    """Verify MR diff fetching."""

    async def test_returns_unified_diff(self) -> None:
        scm = GitLabSCM(token="tok")
        changes_data = {
            "changes": [
                {
                    "old_path": "file.py",
                    "new_path": "file.py",
                    "diff": "@@ -1,3 +1,4 @@\n line1\n+new line\n line2\n line3",
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.json.return_value = changes_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("mygroup/myproject!42")

        assert "diff --git" in result
        assert "file.py" in result
        assert "+new line" in result

    async def test_empty_changes_returns_empty(self) -> None:
        scm = GitLabSCM(token="tok")

        mock_response = MagicMock()
        mock_response.json.return_value = {"changes": []}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            result = await scm.get_pr_diff("mygroup/myproject!42")

        assert result == ""

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
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
            patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to fetch MR diff"),
        ):
            await scm.get_pr_diff("mygroup/myproject!42")


# --------------------------------------------------------------------------- #
# post_review_comment
# --------------------------------------------------------------------------- #


class TestPostReviewComment:
    """Verify inline discussion note posting."""

    async def test_posts_comment_successfully(self) -> None:
        scm = GitLabSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "mygroup/myproject!42",
                file_path="src/main.py",
                line=10,
                body="Fix this issue",
                severity="high",
            )

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"]
        assert "HIGH" in payload["body"]
        assert payload["position"]["new_path"] == "src/main.py"
        assert payload["position"]["new_line"] == 10

    async def test_uses_discussions_endpoint(self) -> None:
        scm = GitLabSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_comment(
                "mygroup/myproject!42",
                file_path="f.py",
                line=1,
                body="test",
                severity="low",
            )

        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "/discussions" in url

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
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
            patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review comment"),
        ):
            await scm.post_review_comment(
                "mygroup/myproject!42",
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

    async def test_posts_summary_note(self) -> None:
        scm = GitLabSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "mygroup/myproject!42",
                body="Looks good!",
                approve=False,
                request_changes=False,
            )

        # Should post to notes endpoint
        call_args = mock_client.post.call_args
        url = call_args[0][0]
        assert "/notes" in url
        payload = call_args[1]["json"]
        assert payload["body"] == "Looks good!"

    async def test_approve_calls_approve_endpoint(self) -> None:
        scm = GitLabSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "mygroup/myproject!42",
                body="LGTM",
                approve=True,
                request_changes=False,
            )

        # Two POST calls: notes + approve
        assert mock_client.post.call_count == 2
        second_call = mock_client.post.call_args_list[1]
        assert "/approve" in second_call[0][0]

    async def test_no_approve_skips_approve_endpoint(self) -> None:
        scm = GitLabSCM(token="tok")
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client):
            await scm.post_review_summary(
                "mygroup/myproject!42",
                body="Issues found",
                approve=False,
                request_changes=True,
            )

        # Only one POST call: notes (no approve)
        assert mock_client.post.call_count == 1

    async def test_http_error_raises_scm_error(self) -> None:
        scm = GitLabSCM(token="tok")
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
            patch("codesentinel.scm.gitlab.httpx.AsyncClient", return_value=mock_client),
            pytest.raises(SCMError, match="Failed to post review summary"),
        ):
            await scm.post_review_summary(
                "mygroup/myproject!42",
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
        scm = GitLabSCM(token="tok")
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_local_diff("/repo", "main", "feature")
