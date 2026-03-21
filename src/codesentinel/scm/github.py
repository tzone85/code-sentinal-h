"""GitHub SCM provider using the GitHub REST API."""

from __future__ import annotations

import logging
import re

import httpx

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

# Pattern: "owner/repo#123"
_SHORT_RE = re.compile(r"^(?P<owner>[^/]+)/(?P<repo>[^#]+)#(?P<number>\d+)$")

# Pattern: "https://github.com/owner/repo/pull/123"
_URL_RE = re.compile(r"https?://[^/]+/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$")


class GitHubSCM(SCMProvider):
    """GitHub SCM provider using httpx for REST API calls.

    Supports both github.com and GitHub Enterprise via ``base_url``.
    """

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # PR identifier parsing
    # ------------------------------------------------------------------ #

    def _parse_pr_identifier(self, pr_identifier: str) -> tuple[str, str, int]:
        """Parse a PR identifier into (owner, repo, number).

        Accepts:
            - "owner/repo#123"
            - "https://github.com/owner/repo/pull/123"

        Raises:
            SCMError: If the identifier cannot be parsed.
        """
        match = _SHORT_RE.match(pr_identifier)
        if match:
            return match["owner"], match["repo"], int(match["number"])

        match = _URL_RE.match(pr_identifier)
        if match:
            return match["owner"], match["repo"], int(match["number"])

        raise SCMError(f"Cannot parse PR identifier: {pr_identifier!r}")

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------ #
    # SCMProvider implementation
    # ------------------------------------------------------------------ #

    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch pull request metadata from the GitHub API."""
        owner, repo, number = self._parse_pr_identifier(pr_identifier)
        url = f"{self._base_url}/repos/{owner}/{repo}/pulls/{number}"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self._auth_headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(f"Failed to fetch PR info for {pr_identifier}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch PR info for {pr_identifier}: {exc}") from exc

        data = response.json()
        return PRInfo(
            number=data["number"],
            title=data["title"],
            author=data["user"]["login"],
            base_branch=data["base"]["ref"],
            head_branch=data["head"]["ref"],
            url=data["html_url"],
            diff_url=data["diff_url"],
        )

    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the raw diff for a pull request."""
        owner, repo, number = self._parse_pr_identifier(pr_identifier)
        url = f"{self._base_url}/repos/{owner}/{repo}/pulls/{number}"

        headers = {
            **self._auth_headers(),
            "Accept": "application/vnd.github.diff",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(f"Failed to fetch PR diff for {pr_identifier}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch PR diff for {pr_identifier}: {exc}") from exc

        return response.text

    async def post_review_comment(
        self,
        pr_identifier: str,
        file_path: str,
        line: int,
        body: str,
        severity: str,
    ) -> None:
        """Post an inline review comment on a pull request."""
        owner, repo, number = self._parse_pr_identifier(pr_identifier)
        url = f"{self._base_url}/repos/{owner}/{repo}/pulls/{number}/comments"

        payload = {
            "body": body,
            "path": file_path,
            "line": line,
            "side": "RIGHT",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self._auth_headers(), json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to post review comment on {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to post review comment on {pr_identifier}: {exc}") from exc

    async def post_review_summary(
        self,
        pr_identifier: str,
        body: str,
        approve: bool,
        request_changes: bool,
    ) -> None:
        """Submit a PR review with an event type."""
        owner, repo, number = self._parse_pr_identifier(pr_identifier)
        url = f"{self._base_url}/repos/{owner}/{repo}/pulls/{number}/reviews"

        if approve:
            event = "APPROVE"
        elif request_changes:
            event = "REQUEST_CHANGES"
        else:
            event = "COMMENT"

        payload = {
            "body": body,
            "event": event,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, headers=self._auth_headers(), json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to post review summary on {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to post review summary on {pr_identifier}: {exc}") from exc

    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Not supported by GitHub SCM — use LocalGitSCM instead."""
        raise NotImplementedError(
            "get_local_diff is not supported by GitHubSCM. Use LocalGitSCM for local diff operations."
        )
