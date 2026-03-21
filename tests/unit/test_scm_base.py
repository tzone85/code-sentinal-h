"""Tests for the SCM provider abstraction layer."""

from __future__ import annotations

import pytest

from codesentinel.core.models import PRInfo
from codesentinel.scm.base import SCMProvider


class TestSCMProviderInterface:
    """Verify that SCMProvider defines the correct abstract contract."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError, match="abstract"):
            SCMProvider()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_get_pr_info(self) -> None:
        class Incomplete(SCMProvider):
            async def get_pr_diff(self, pr_identifier: str) -> str:
                return ""

            async def post_review_comment(
                self,
                pr_identifier: str,
                file_path: str,
                line: int,
                body: str,
                severity: str,
            ) -> None:
                pass

            async def post_review_summary(
                self,
                pr_identifier: str,
                body: str,
                approve: bool,
                request_changes: bool,
            ) -> None:
                pass

            async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
                return ""

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_get_pr_diff(self) -> None:
        class Incomplete(SCMProvider):
            async def get_pr_info(self, pr_identifier: str) -> PRInfo:
                return PRInfo(
                    number=1,
                    title="",
                    author="",
                    base_branch="",
                    head_branch="",
                    url="",
                    diff_url="",
                )

            async def post_review_comment(
                self,
                pr_identifier: str,
                file_path: str,
                line: int,
                body: str,
                severity: str,
            ) -> None:
                pass

            async def post_review_summary(
                self,
                pr_identifier: str,
                body: str,
                approve: bool,
                request_changes: bool,
            ) -> None:
                pass

            async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
                return ""

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_post_review_comment(self) -> None:
        class Incomplete(SCMProvider):
            async def get_pr_info(self, pr_identifier: str) -> PRInfo:
                return PRInfo(
                    number=1,
                    title="",
                    author="",
                    base_branch="",
                    head_branch="",
                    url="",
                    diff_url="",
                )

            async def get_pr_diff(self, pr_identifier: str) -> str:
                return ""

            async def post_review_summary(
                self,
                pr_identifier: str,
                body: str,
                approve: bool,
                request_changes: bool,
            ) -> None:
                pass

            async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
                return ""

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_post_review_summary(self) -> None:
        class Incomplete(SCMProvider):
            async def get_pr_info(self, pr_identifier: str) -> PRInfo:
                return PRInfo(
                    number=1,
                    title="",
                    author="",
                    base_branch="",
                    head_branch="",
                    url="",
                    diff_url="",
                )

            async def get_pr_diff(self, pr_identifier: str) -> str:
                return ""

            async def post_review_comment(
                self,
                pr_identifier: str,
                file_path: str,
                line: int,
                body: str,
                severity: str,
            ) -> None:
                pass

            async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
                return ""

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_get_local_diff(self) -> None:
        class Incomplete(SCMProvider):
            async def get_pr_info(self, pr_identifier: str) -> PRInfo:
                return PRInfo(
                    number=1,
                    title="",
                    author="",
                    base_branch="",
                    head_branch="",
                    url="",
                    diff_url="",
                )

            async def get_pr_diff(self, pr_identifier: str) -> str:
                return ""

            async def post_review_comment(
                self,
                pr_identifier: str,
                file_path: str,
                line: int,
                body: str,
                severity: str,
            ) -> None:
                pass

            async def post_review_summary(
                self,
                pr_identifier: str,
                body: str,
                approve: bool,
                request_changes: bool,
            ) -> None:
                pass

        with pytest.raises(TypeError, match="abstract"):
            Incomplete()  # type: ignore[abstract]

    def test_complete_subclass_can_instantiate(self) -> None:
        class Complete(SCMProvider):
            async def get_pr_info(self, pr_identifier: str) -> PRInfo:
                return PRInfo(
                    number=1,
                    title="Test",
                    author="dev",
                    base_branch="main",
                    head_branch="feature",
                    url="https://example.com/pr/1",
                    diff_url="https://example.com/pr/1.diff",
                )

            async def get_pr_diff(self, pr_identifier: str) -> str:
                return "diff content"

            async def post_review_comment(
                self,
                pr_identifier: str,
                file_path: str,
                line: int,
                body: str,
                severity: str,
            ) -> None:
                pass

            async def post_review_summary(
                self,
                pr_identifier: str,
                body: str,
                approve: bool,
                request_changes: bool,
            ) -> None:
                pass

            async def get_local_diff(self, repo_path: str, base_branch: str, head_branch: str) -> str:
                return "local diff"

        provider = Complete()
        assert isinstance(provider, SCMProvider)
