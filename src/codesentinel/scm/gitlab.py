"""GitLab SCM provider using the GitLab REST API v4."""

from __future__ import annotations

import logging
import re

import httpx

from codesentinel.core.exceptions import SCMError
from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider

logger = logging.getLogger(__name__)

# Pattern: "group/project!123" (GitLab uses ! for MRs)
_SHORT_RE = re.compile(r"^(?P<project>[^!]+)!(?P<number>\d+)$")

# Pattern: "https://gitlab.com/group/project/-/merge_requests/123"
_URL_RE = re.compile(
    r"https?://[^/]+/(?P<project>.+?)/-/merge_requests/(?P<number>\d+)/?$"
)


class GitLabSCM(SCMProvider):
    """GitLab SCM provider using httpx for REST API v4 calls.

    Supports both gitlab.com and self-hosted GitLab via ``base_url``.
    """

    def __init__(
        self,
        token: str,
        base_url: str = "https://gitlab.com",
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------ #
    # MR identifier parsing
    # ------------------------------------------------------------------ #

    def _parse_mr_identifier(self, pr_identifier: str) -> tuple[str, int]:
        """Parse a merge request identifier into (project_path, mr_number).

        Accepts:
            - "group/project!123"
            - "https://gitlab.com/group/project/-/merge_requests/123"

        Raises:
            SCMError: If the identifier cannot be parsed.
        """
        match = _SHORT_RE.match(pr_identifier)
        if match:
            return match["project"], int(match["number"])

        match = _URL_RE.match(pr_identifier)
        if match:
            return match["project"], int(match["number"])

        raise SCMError(f"Cannot parse MR identifier: {pr_identifier!r}")

    @staticmethod
    def _encode_project(project_path: str) -> str:
        """URL-encode the project path for GitLab API (slashes → %2F)."""
        return project_path.replace("/", "%2F")

    # ------------------------------------------------------------------ #
    # HTTP helpers
    # ------------------------------------------------------------------ #

    def _auth_headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._token}

    # ------------------------------------------------------------------ #
    # SCMProvider implementation
    # ------------------------------------------------------------------ #

    async def get_pr_info(self, pr_identifier: str) -> PRInfo:
        """Fetch merge request metadata from the GitLab API."""
        project_path, mr_number = self._parse_mr_identifier(pr_identifier)
        encoded = self._encode_project(project_path)
        url = f"{self._base_url}/api/v4/projects/{encoded}/merge_requests/{mr_number}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._auth_headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch MR info for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch MR info for {pr_identifier}: {exc}") from exc

        data = response.json()
        return PRInfo(
            number=data["iid"],
            title=data["title"],
            author=data["author"]["username"],
            base_branch=data["target_branch"],
            head_branch=data["source_branch"],
            url=data["web_url"],
            diff_url=f"{data['web_url']}.diff",
        )

    async def get_pr_diff(self, pr_identifier: str) -> str:
        """Fetch the raw diff for a merge request."""
        project_path, mr_number = self._parse_mr_identifier(pr_identifier)
        encoded = self._encode_project(project_path)
        url = (
            f"{self._base_url}/api/v4/projects/{encoded}"
            f"/merge_requests/{mr_number}/changes"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=self._auth_headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to fetch MR diff for {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to fetch MR diff for {pr_identifier}: {exc}") from exc

        data = response.json()
        return self._build_unified_diff(data.get("changes", []))

    @staticmethod
    def _build_unified_diff(changes: list[dict[str, object]]) -> str:
        """Convert GitLab MR changes response to unified diff text."""
        parts: list[str] = []
        for change in changes:
            diff_text = change.get("diff", "")
            old_path = change.get("old_path", "")
            new_path = change.get("new_path", "")
            header = f"diff --git a/{old_path} b/{new_path}"
            parts.append(f"{header}\n{diff_text}")
        return "\n".join(parts)

    async def post_review_comment(
        self,
        pr_identifier: str,
        file_path: str,
        line: int,
        body: str,
        severity: str,
    ) -> None:
        """Post an inline discussion note on a merge request."""
        project_path, mr_number = self._parse_mr_identifier(pr_identifier)
        encoded = self._encode_project(project_path)
        url = (
            f"{self._base_url}/api/v4/projects/{encoded}"
            f"/merge_requests/{mr_number}/discussions"
        )

        payload = {
            "body": f"**[{severity.upper()}]** {body}",
            "position": {
                "base_sha": "",
                "head_sha": "",
                "start_sha": "",
                "position_type": "text",
                "new_path": file_path,
                "new_line": line,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
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
        """Post a summary note on a merge request.

        GitLab does not have a single "review" concept like GitHub.
        We post a regular MR note for the summary, and optionally
        approve or unapprove the MR via the approvals API.
        """
        project_path, mr_number = self._parse_mr_identifier(pr_identifier)
        encoded = self._encode_project(project_path)

        # Post summary note
        notes_url = (
            f"{self._base_url}/api/v4/projects/{encoded}"
            f"/merge_requests/{mr_number}/notes"
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    notes_url, headers=self._auth_headers(), json={"body": body}
                )
                response.raise_for_status()

                # Approve if requested
                if approve:
                    approve_url = (
                        f"{self._base_url}/api/v4/projects/{encoded}"
                        f"/merge_requests/{mr_number}/approve"
                    )
                    resp = await client.post(approve_url, headers=self._auth_headers())
                    resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise SCMError(
                f"Failed to post review summary on {pr_identifier}: HTTP {exc.response.status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            raise SCMError(f"Failed to post review summary on {pr_identifier}: {exc}") from exc

    async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
        """Not supported by GitLab SCM — use LocalGitSCM instead."""
        raise NotImplementedError(
            "get_local_diff is not supported by GitLabSCM. Use LocalGitSCM for local diff operations."
        )
