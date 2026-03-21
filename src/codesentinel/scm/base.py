"""Abstract base class for source control management providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesentinel.core.models import PRInfo


class SCMProvider(ABC):
    """Abstract interface for SCM integrations (GitHub, GitLab, local git, etc.).

    Concrete providers implement the actual API / CLI logic.
    """

    @abstractmethod
    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch metadata for a pull / merge request.

        Args:
            pr_identifier: PR URL or "owner/repo#number" string.

        Returns:
            A PRInfo with title, author, branches, and URLs.
        """

    @abstractmethod
    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the raw unified diff for a pull / merge request.

        Args:
            pr_identifier: PR URL or "owner/repo#number" string.

        Returns:
            The raw unified diff text.
        """

    @abstractmethod
    async def post_review_comment(
        self,
        pr_identifier: str,
        file_path: str,
        line: int,
        body: str,
        severity: str,
    ) -> None:
        """Post an inline review comment on a specific file/line.

        Args:
            pr_identifier: PR URL or "owner/repo#number" string.
            file_path: Path of the file to comment on.
            line: Line number in the new file.
            body: Comment body text.
            severity: Finding severity level.
        """

    @abstractmethod
    async def post_review_summary(
        self,
        pr_identifier: str,
        body: str,
        *,
        approve: bool = False,
        request_changes: bool = False,
    ) -> None:
        """Post a summary review comment on the PR.

        Args:
            pr_identifier: PR URL or "owner/repo#number" string.
            body: Summary body text.
            approve: Submit review as APPROVE.
            request_changes: Submit review as REQUEST_CHANGES.
        """

    @abstractmethod
    async def get_local_diff(
        self,
        repo_path: str,
        base_branch: str,
        head_branch: str | None = None,
    ) -> str:
        """Get a local git diff between branches.

        Args:
            repo_path: Path to the git repository.
            base_branch: The base branch to diff against.
            head_branch: The head branch (None = current HEAD).

        Returns:
            The raw unified diff text.
        """
