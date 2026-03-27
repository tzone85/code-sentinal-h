"""Azure DevOps SCM provider using the Azure DevOps REST API."""

from __future__ import annotations

import base64
import logging
import re

import httpx

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

# Pattern: "org/project/_git/repo/pullrequest/123"
_SHORT_RE = re.compile(
    r"^(?P<org>[^/]+)/(?P<project>[^/]+)/(?P<repo>[^/]+)#(?P<number>\d+)$"
)

# Pattern: "https://dev.azure.com/org/project/_git/repo/pullrequest/123"
_URL_RE = re.compile(
    r"https?://dev\.azure\.com/"
    r"(?P<org>[^/]+)/(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<number>\d+)/?$"
)

# Legacy VSTS URL: "https://org.visualstudio.com/project/_git/repo/pullrequest/123"
_VSTS_URL_RE = re.compile(
    r"https?://(?P<org>[^.]+)\.visualstudio\.com/"
    r"(?P<project>[^/]+)/_git/(?P<repo>[^/]+)/pullrequest/(?P<number>\d+)/?$"
)


class AzureDevOpsSCM(SCMProvider):
    """Azure DevOps SCM provider using httpx for REST API calls.

    Supports both dev.azure.com and legacy visualstudio.com URLs.
    Uses Personal Access Token (PAT) for authentication.
    """

    def __init__(
        self,
        token: str,
        organization: str = "",
        base_url: str = "https://dev.azure.com",
    ) -> None:
        self._token = token
        self._organization = organization
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # PR identifier parsing
    # ------------------------------------------------------------------ #

    def _parse_pr_identifier(self, pr_identifier: str) -> tuple[str, str, str, int]:
        """Parse a PR identifier into (org, project, repo, number).

        Accepts:
            - "org/project/repo#123"
            - "https://dev.azure.com/org/project/_git/repo/pullrequest/123"
            - "https://org.visualstudio.com/project/_git/repo/pullrequest/123"

        Raises:
            SCMError: If the identifier cannot be parsed.
        """
        match = _SHORT_RE.match(pr_identifier)
        if match:
            return match["org"], match["project"], match["repo"], int(match["number"])

        match = _URL_RE.match(pr_identifier)
        if match:
            return match["org"], match["project"], match["repo"], int(match["number"])

        match = _VSTS_URL_RE.match(pr_identifier)
        if match:
            return match["org"], match["project"], match["repo"], int(match["number"])

        raise SCMError(f"Cannot parse Azure DevOps PR identifier: {pr_identifier!r}")

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _auth_headers(self) -> dict[str, str]:
        """Build Basic auth header from PAT (Azure DevOps convention)."""
        encoded = base64.b64encode(f":{self._token}".encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    def _api_url(self, org: str, project: str, repo: str) -> str:
        """Build the base API URL for a repository."""
        return f"{self._base_url}/{org}/{project}/_apis/git/repositories/{repo}"

    # ------------------------------------------------------------------ #
    # SCMProvider implementation
    # ------------------------------------------------------------------ #

    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch pull request metadata from Azure DevOps API."""
        org, project, repo, number = self._parse_pr_identifier(pr_identifier)
        url = f"{self._api_url(org, project, repo)}/pullrequests/{number}"
        params = {"api-version": "7.1"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._auth_headers(), params=params)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch PR info for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch PR info for {pr_identifier}: {exc}") from exc

        data = response.json()

        # Extract branch names (Azure DevOps uses refs/heads/ prefix)
        base_ref = data.get("targetRefName", "")
        head_ref = data.get("sourceRefName", "")
        base_branch = base_ref.removeprefix("refs/heads/")
        head_branch = head_ref.removeprefix("refs/heads/")

        # Build web URL
        web_url = (
            f"https://dev.azure.com/{org}/{project}/_git/{repo}"
            f"/pullrequest/{number}"
        )

        return PRInfo(
            number=data["pullRequestId"],
            title=data["title"],
            author=data["createdBy"]["uniqueName"],
            base_branch=base_branch,
            head_branch=head_branch,
            url=web_url,
            diff_url=f"{url}/diff?api-version=7.1",
        )

    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the diff for a pull request using the iterations API."""
        org, project, repo, number = self._parse_pr_identifier(pr_identifier)
        base_url = self._api_url(org, project, repo)
        params = {"api-version": "7.1"}

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get iterations to find the latest
                iter_url = f"{base_url}/pullrequests/{number}/iterations"
                response = await client.get(
                    iter_url, headers=self._auth_headers(), params=params
                )
                response.raise_for_status()

                iterations = response.json().get("value", [])
                if not iterations:
                    return ""

                latest_id = iterations[-1]["id"]

                # Get changes for the latest iteration
                changes_url = (
                    f"{base_url}/pullrequests/{number}"
                    f"/iterations/{latest_id}/changes"
                )
                response = await client.get(
                    changes_url, headers=self._auth_headers(), params=params
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch PR diff for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch PR diff for {pr_identifier}: {exc}") from exc

        changes = response.json().get("changeEntries", [])
        return self._build_unified_diff(changes)

    @staticmethod
    def _build_unified_diff(change_entries: list[dict[str, object]]) -> str:
        """Convert Azure DevOps change entries to a minimal unified diff representation."""
        parts: list[str] = []
        for entry in change_entries:
            item = entry.get("item", {})
            path = item.get("path", "") if isinstance(item, dict) else ""
            change_type = entry.get("changeType", "edit")
            header = f"diff --git a{path} b{path}"
            parts.append(f"{header}\n--- a{path}\n+++ b{path}\n# changeType: {change_type}")
        return "\n".join(parts)

    async def post_review_comment(
        self,
        pr_identifier: str,
        file_path: str,
        line: int,
        body: str,
        severity: str,
    ) -> None:
        """Post an inline comment thread on a pull request."""
        org, project, repo, number = self._parse_pr_identifier(pr_identifier)
        url = (
            f"{self._api_url(org, project, repo)}"
            f"/pullrequests/{number}/threads"
        )
        params = {"api-version": "7.1"}

        payload = {
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": f"**[{severity.upper()}]** {body}",
                    "commentType": 1,
                }
            ],
            "status": 1,  # Active
            "threadContext": {
                "filePath": f"/{file_path}",
                "rightFileStart": {"line": line, "offset": 1},
                "rightFileEnd": {"line": line, "offset": 1},
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url, headers=self._auth_headers(), json=payload, params=params
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
        """Post a summary comment thread on a pull request.

        Azure DevOps uses a thread with no file context for summary comments.
        Optionally sets vote via the reviewers API.
        """
        org, project, repo, number = self._parse_pr_identifier(pr_identifier)
        base_url = self._api_url(org, project, repo)
        params = {"api-version": "7.1"}

        # Post summary thread (no threadContext = PR-level comment)
        threads_url = f"{base_url}/pullrequests/{number}/threads"
        payload = {
            "comments": [
                {
                    "parentCommentId": 0,
                    "content": body,
                    "commentType": 1,
                }
            ],
            "status": 4 if approve else 1,  # 4=Fixed, 1=Active
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    threads_url, headers=self._auth_headers(), json=payload, params=params
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to post review summary on {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to post review summary on {pr_identifier}: {exc}") from exc

    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Not supported by Azure DevOps SCM — use LocalGitSCM instead."""
        raise NotImplementedError(
            "get_local_diff is not supported by AzureDevOpsSCM. Use LocalGitSCM for local diff operations."
        )
