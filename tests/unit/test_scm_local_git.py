"""Tests for the Local Git SCM provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.scm.base import SCMProvider
from codesentinel.scm.local_git import LocalGitSCM

# --------------------------------------------------------------------------- #
# Construction & interface
# --------------------------------------------------------------------------- #


class TestLocalGitSCMConstruction:
    """Verify construction and interface compliance."""

    def test_is_scm_provider(self) -> None:
        scm = LocalGitSCM()
        assert isinstance(scm, SCMProvider)


# --------------------------------------------------------------------------- #
# get_local_diff — branch diff
# --------------------------------------------------------------------------- #


class TestGetLocalDiff:
    """Verify local diff operations."""

    async def test_returns_diff_between_branches(self) -> None:
        scm = LocalGitSCM()
        diff_text = "diff --git a/file.py b/file.py\n+new line"

        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = diff_text

        with patch("codesentinel.scm.local_git.Repo", return_value=mock_repo):
            result = await scm.get_local_diff("/repo", "main", "feature")

        assert result == diff_text
        mock_repo.git.diff.assert_called_once_with("main...feature")

    async def test_staged_diff_with_staged_flag(self) -> None:
        scm = LocalGitSCM()
        diff_text = "diff --git a/staged.py b/staged.py\n+staged change"

        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = diff_text

        with patch("codesentinel.scm.local_git.Repo", return_value=mock_repo):
            result = await scm.get_local_diff("/repo", "main", "--staged")

        assert result == diff_text
        mock_repo.git.diff.assert_called_once_with("--cached")

    async def test_staged_diff_with_cached_flag(self) -> None:
        scm = LocalGitSCM()
        diff_text = "diff --git a/cached.py b/cached.py\n+cached change"

        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = diff_text

        with patch("codesentinel.scm.local_git.Repo", return_value=mock_repo):
            result = await scm.get_local_diff("/repo", "main", "--cached")

        assert result == diff_text
        mock_repo.git.diff.assert_called_once_with("--cached")

    async def test_invalid_repo_path_raises_scm_error(self) -> None:
        scm = LocalGitSCM()

        with (
            patch(
                "codesentinel.scm.local_git.Repo",
                side_effect=Exception("not a git repo"),
            ),
            pytest.raises(SCMError, match="Failed to open repository"),
        ):
            await scm.get_local_diff("/not-a-repo", "main", "feature")

    async def test_git_diff_error_raises_scm_error(self) -> None:
        scm = LocalGitSCM()
        mock_repo = MagicMock()
        mock_repo.git.diff.side_effect = Exception("git diff failed")

        with (
            patch("codesentinel.scm.local_git.Repo", return_value=mock_repo),
            pytest.raises(SCMError, match="Failed to compute diff"),
        ):
            await scm.get_local_diff("/repo", "main", "feature")

    async def test_empty_diff_returns_empty_string(self) -> None:
        scm = LocalGitSCM()
        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = ""

        with patch("codesentinel.scm.local_git.Repo", return_value=mock_repo):
            result = await scm.get_local_diff("/repo", "main", "feature")

        assert result == ""


# --------------------------------------------------------------------------- #
# Unsupported PR operations
# --------------------------------------------------------------------------- #


class TestUnsupportedPROperations:
    """Verify that PR operations raise NotImplementedError."""

    async def test_get_pr_info_raises(self) -> None:
        scm = LocalGitSCM()
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_pr_info("owner/repo#1")

    async def test_get_pr_diff_raises(self) -> None:
        scm = LocalGitSCM()
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.get_pr_diff("owner/repo#1")

    async def test_post_review_comment_raises(self) -> None:
        scm = LocalGitSCM()
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.post_review_comment("owner/repo#1", "file.py", 1, "body", "high")

    async def test_post_review_summary_raises(self) -> None:
        scm = LocalGitSCM()
        with pytest.raises(NotImplementedError, match="not supported"):
            await scm.post_review_summary("owner/repo#1", "body", False, False)
