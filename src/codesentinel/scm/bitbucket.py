"""Bitbucket SCM provider using the Bitbucket Cloud REST API v2."""

from __future__ import annotations

import logging
import re

import httpx

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

# Pattern: "workspace/repo#123"
_SHORT_RE = re.compile(r"^(?P<workspace>[^/]+)/(?P<repo>[^#]+)#(?P<number>\d+)$")

# Pattern: "https://bitbucket.org/workspace/repo/pull-requests/123"
_URL_RE = re.compile(
    r"https?://bitbucket\.org/(?P<workspace>[^/]+)/(?P<repo>[^/]+)"
    r"/pull-requests/(?P<number>\d+)/?$"
)


class BitbucketSCM(SCMProvider):
    """Bitbucket Cloud SCM provider using httpx for REST API v2 calls.

    Supports app password or repository/workspace access token auth.
    """

    def __init__(
        self,
        token: str,
        username: str = "",
        base_url: str = "https://api.bitbucket.org/2.0",
    ) -> None:
        self._token = token
        self._username = username
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # PR identifier parsing
    # ------------------------------------------------------------------ #

    def _parse_pr_identifier(self, pr_identifier: str) -> tuple[str, str, int]:
        """Parse a PR identifier into (workspace, repo, number).

        Accepts:
            - "workspace/repo#123"
            - "https://bitbucket.org/workspace/repo/pull-requests/123"

        Raises:
            SCMError: If the identifier cannot be parsed.
        """
        match = _SHORT_RE.match(pr_identifier)
        if match:
            return match["workspace"], match["repo"], int(match["number"])

        match = _URL_RE.match(pr_identifier)
        if match:
            return match["workspace"], match["repo"], int(match["number"])

        raise SCMError(f"Cannot parse Bitbucket PR identifier: {pr_identifier!r}")

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _auth_headers(self) -> dict[str, str]:
        """Build auth header.

        If username is provided, uses Basic auth (app password).
        Otherwise, uses Bearer token (repository/workspace access token).
        """
        if self._username:
            import base64

            encoded = base64.b64encode(
                f"{self._username}:{self._token}".encode()
            ).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------ #
    # SCMProvider implementation
    # ------------------------------------------------------------------ #

    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch pull request metadata from the Bitbucket API."""
        workspace, repo, number = self._parse_pr_identifier(pr_identifier)
        url = (
            f"{self._base_url}/repositories/{workspace}/{repo}"
            f"/pullrequests/{number}"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._auth_headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch PR info for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch PR info for {pr_identifier}: {exc}") from exc

        data = response.json()
        source = data.get("source", {})
        destination = data.get("destination", {})

        return PRInfo(
            number=data["id"],
            title=data["title"],
            author=data["author"]["display_name"],
            base_branch=destination.get("branch", {}).get("name", ""),
            head_branch=source.get("branch", {}).get("name", ""),
            url=data["links"]["html"]["href"],
            diff_url=data["links"]["diff"]["href"],
        )

    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the raw diff for a pull request."""
        workspace, repo, number = self._parse_pr_identifier(pr_identifier)
        url = (
            f"{self._base_url}/repositories/{workspace}/{repo}"
            f"/pullrequests/{number}/diff"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._auth_headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch PR diff for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
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
        """Post an inline comment on a pull request."""
        workspace, repo, number = self._parse_pr_identifier(pr_identifier)
        url = (
            f"{self._base_url}/repositories/{workspace}/{repo}"
            f"/pullrequests/{number}/comments"
        )

        payload = {
            "content": {"raw": f"**[{severity.upper()}]** {body}"},
            "inline": {
                "path": file_path,
                "to": line,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url, headers=self._auth_headers(), json=payload
                )
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
        """Post a summary comment on a pull request.

        Bitbucket uses separate endpoints for comments and approval.
        Approval is done via the approve endpoint.
        """
        workspace, repo, number = self._parse_pr_identifier(pr_identifier)
        base = (
            f"{self._base_url}/repositories/{workspace}/{repo}"
            f"/pullrequests/{number}"
        )

        # Post summary comment (no inline context = PR-level)
        comment_url = f"{base}/comments"
        payload = {"content": {"raw": body}}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    comment_url, headers=self._auth_headers(), json=payload
                )
                response.raise_for_status()

                if approve:
                    approve_url = f"{base}/approve"
                    resp = await client.post(approve_url, headers=self._auth_headers())
                    resp.raise_for_status()

                if request_changes:
                    changes_url = f"{base}/request-changes"
                    resp = await client.post(changes_url, headers=self._auth_headers())
                    resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to post review summary on {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to post review summary on {pr_identifier}: {exc}") from exc

    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Not supported by Bitbucket SCM — use LocalGitSCM instead."""
        raise NotImplementedError(
            "get_local_diff is not supported by BitbucketSCM. Use LocalGitSCM for local diff operations."
        )
