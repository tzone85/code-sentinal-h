"""Abstract base class for source control management providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codesentinel.core.models import PRInfo


class SCMProvider(ABC):
    """Abstract interface that all SCM providers must implement.

    Concrete providers (GitHub, Local Git, GitLab, etc.) inherit from
    this class and supply the actual SCM integration logic.
    """

    @abstractmethod
    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch pull request metadata.

        Args:
            pr_identifier: PR reference (URL or "owner/repo#number").

        Returns:
            A PRInfo with the pull request metadata.
        """

    @abstractmethod
    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the diff content for a pull request.

        Args:
            pr_identifier: PR reference (URL or "owner/repo#number").

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
        """Post an inline review comment on a specific file and line.

        Args:
            pr_identifier: PR reference.
            file_path: Path to the file within the diff.
            line: Line number for the comment.
            body: Comment body text.
            severity: Finding severity level.
        """

    @abstractmethod
    async def post_review_summary(
        self,
        pr_identifier: str,
        body: str,
        approve: bool,
        request_changes: bool,
    ) -> None:
        """Post a review summary on a pull request.

        Args:
            pr_identifier: PR reference.
            body: Summary body text.
            approve: Whether to approve the PR.
            request_changes: Whether to request changes.
        """

    @abstractmethod
    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Get a diff between two branches in a local repository.

        Args:
            repo_path: Path to the local git repository.
            base_branch: Base branch for comparison.
            head_branch: Head branch (or "--staged"/"--cached" for staged changes).

        Returns:
            The raw unified diff text.
        """
