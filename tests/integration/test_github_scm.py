"""Integration tests for GitHub SCM provider.

Requires GITHUB_TOKEN environment variable. Skipped if not set.
Uses real GitHub API calls against a known public test PR.
"""

from __future__ import annotations

import os

import pytest

from codesentinel.core.exceptions import SCMError
from codesentinel.scm.github import GitHubSCM

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("GITHUB_TOKEN"),
        reason="GITHUB_TOKEN not set",
    ),
]

# Use a known public PR for testing (the first merged PR in this repo)
TEST_PR_IDENTIFIER = "tzone85/code-sentinal-h#1"


def _make_scm() -> GitHubSCM:
    token = os.environ["GITHUB_TOKEN"]
    return GitHubSCM(token=token)


class TestGetPRInfo:
    @pytest.mark.asyncio
    async def test_fetches_pr_metadata(self) -> None:
        scm = _make_scm()
        pr_info = await scm.get_pr_info(TEST_PR_IDENTIFIER)

        assert pr_info.number == 1
        assert pr_info.title  # Non-empty title
        assert pr_info.author  # Non-empty author
        assert pr_info.url  # Has a URL
        assert pr_info.base_branch  # Has base branch
        assert pr_info.head_branch  # Has head branch

    @pytest.mark.asyncio
    async def test_invalid_pr_raises_scm_error(self) -> None:
        scm = _make_scm()
        with pytest.raises(SCMError):
            await scm.get_pr_info("tzone85/code-sentinal-h#99999")


class TestGetPRDiff:
    @pytest.mark.asyncio
    async def test_fetches_pr_diff(self) -> None:
        scm = _make_scm()
        diff = await scm.get_pr_diff(TEST_PR_IDENTIFIER)

        assert isinstance(diff, str)
        assert len(diff) > 0
        assert "diff" in diff.lower() or "---" in diff

    @pytest.mark.asyncio
    async def test_invalid_pr_raises_scm_error(self) -> None:
        scm = _make_scm()
        with pytest.raises(SCMError):
            await scm.get_pr_diff("tzone85/code-sentinal-h#99999")


class TestPRIdentifierFormats:
    @pytest.mark.asyncio
    async def test_url_format_works(self) -> None:
        scm = _make_scm()
        pr_info = await scm.get_pr_info(
            "https://github.com/tzone85/code-sentinal-h/pull/1"
        )
        assert pr_info.number == 1

    @pytest.mark.asyncio
    async def test_short_format_works(self) -> None:
        scm = _make_scm()
        pr_info = await scm.get_pr_info("tzone85/code-sentinal-h#1")
        assert pr_info.number == 1
