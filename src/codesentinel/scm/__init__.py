"""Source control management providers."""

from codesentinel.scm.azure_devops import AzureDevOpsSCM
from codesentinel.scm.base import SCMProvider
from codesentinel.scm.bitbucket import BitbucketSCM
from codesentinel.scm.github import GitHubSCM
from codesentinel.scm.gitlab import GitLabSCM
from codesentinel.scm.local_git import LocalGitSCM

__all__ = [
    "AzureDevOpsSCM",
    "BitbucketSCM",
    "GitHubSCM",
    "GitLabSCM",
    "LocalGitSCM",
    "SCMProvider",
]
