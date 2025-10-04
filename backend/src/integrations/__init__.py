"""Integration clients for external version control systems.

This package provides clients for GitHub and GitLab APIs to support
GitOps pull request automation.
"""

from src.integrations.github_client import (
    GitHubClient,
    GitHubConfig,
    GitHubCommit,
    PullRequest,
    GitHubAPIError,
)
from src.integrations.gitlab_client import (
    GitLabClient,
    GitLabConfig,
    GitLabCommit,
    MergeRequest,
    GitLabAPIError,
)

__all__ = [
    "GitHubClient",
    "GitHubConfig",
    "GitHubCommit",
    "PullRequest",
    "GitHubAPIError",
    "GitLabClient",
    "GitLabConfig",
    "GitLabCommit",
    "MergeRequest",
    "GitLabAPIError",
]
