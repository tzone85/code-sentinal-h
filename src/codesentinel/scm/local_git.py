"""Local Git SCM provider using gitpython."""

from __future__ import annotations

import logging

from git import Repo

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

_STAGED_FLAGS = frozenset({"--staged", "--cached"})


class LocalGitSCM(SCMProvider):
    """SCM provider for local git repositories using gitpython.

    Supports diffing between branches and staged changes.
    Does not support remote PR operations.
    """

    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Not supported — LocalGitSCM has no PR concept."""
        raise NotImplementedError(
            "get_pr_info is not supported by LocalGitSCM. Use GitHubSCM for pull request operations."
        )

    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Not supported — LocalGitSCM has no PR concept."""
        raise NotImplementedError(
            "get_pr_diff is not supported by LocalGitSCM. Use GitHubSCM for pull request operations."
        )

    async def post_review_comment(
        self,
        pr_identifier: str,
        file_path: str,
        line: int,
        body: str,
        severity: str,
    ) -> None:
        """Not supported — LocalGitSCM has no PR concept."""
        raise NotImplementedError(
            "post_review_comment is not supported by LocalGitSCM. Use GitHubSCM for pull request operations."
        )

    async def post_review_summary(
        self,
        pr_identifier: str,
        body: str,
        approve: bool,
        request_changes: bool,
    ) -> None:
        """Not supported — LocalGitSCM has no PR concept."""
        raise NotImplementedError(
            "post_review_summary is not supported by LocalGitSCM. Use GitHubSCM for pull request operations."
        )

    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Get a diff between two branches or staged changes.

        When ``head_branch`` is ``"--staged"`` or ``"--cached"``,
        returns the staged diff (``git diff --cached``).
        Otherwise returns ``git diff base_branch...head_branch``.
        """
        try:
            repo = Repo(repo_path)
        except Exception as exc:
            raise SCMError(f"Failed to open repository at {repo_path!r}: {exc}") from exc

        try:
            if head_branch in _STAGED_FLAGS:
                return str(repo.git.diff("--cached"))
            return str(repo.git.diff(f"{base_branch}...{head_branch}"))
        except Exception as exc:
            raise SCMError(f"Failed to compute diff in {repo_path!r}: {exc}") from exc
