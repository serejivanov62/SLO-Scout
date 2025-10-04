"""GitHub client for GitOps PR automation.

This module provides a client for GitHub GraphQL API to create pull requests,
branches, and commit artifacts as part of the GitOps deployment workflow.

Implementation follows research.md GitHub integration decisions:
- GraphQL API for PR creation (REST as fallback)
- OAuth app or PAT authentication
- Feature branch naming: slo-scout/{service}-slos
- Conventional commit messages
"""

import base64
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


logger = logging.getLogger(__name__)


@dataclass
class GitHubConfig:
    """GitHub API configuration."""

    token: str
    api_url: str = "https://api.github.com"
    graphql_endpoint: str = "https://api.github.com/graphql"
    timeout: int = 30
    max_retries: int = 3


@dataclass
class PullRequest:
    """Represents a created pull request."""

    number: int
    url: str
    branch_name: str
    title: str
    state: str
    created_at: datetime


@dataclass
class GitHubCommit:
    """Represents a file to commit."""

    path: str
    content: str
    encoding: str = "utf-8"


class GitHubAPIError(Exception):
    """Raised when GitHub API returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class GitHubClient:
    """Client for GitHub GraphQL API for GitOps automation.

    Supports:
    - Creating feature branches from default branch
    - Committing multiple files in a single commit
    - Creating pull requests with templated body
    - Conventional commit message formatting

    Authentication:
    - OAuth token (recommended for apps)
    - Personal Access Token (PAT) for individual users

    Required token scopes:
    - repo (full control of private repositories)
    - workflow (if committing to .github/workflows)

    Example:
        >>> config = GitHubConfig(token="ghp_...")
        >>> client = GitHubClient(config)
        >>> pr = await client.create_pull_request(
        ...     repo="org/observability-config",
        ...     branch_name="slo-scout/payments-api-slos",
        ...     base_branch="main",
        ...     files=[GitHubCommit(path="prometheus/rules.yml", content="...")],
        ...     commit_message="feat(slos): add SLOs for payments-api",
        ...     pr_title="Add SLOs for payments-api service",
        ...     pr_body="## Summary\\n- Add SLI/SLO definitions\\n- Add Prometheus rules"
        ... )
        >>> print(pr.url)
        https://github.com/org/observability-config/pull/123
    """

    def __init__(self, config: GitHubConfig):
        """Initialize GitHub client.

        Args:
            config: GitHub API configuration with authentication token
        """
        self.config = config
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=config.timeout,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self):
        """Close HTTP client."""
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _graphql_request(self, query: str, variables: Optional[Dict] = None) -> Dict:
        """Execute GraphQL query with retry logic.

        Args:
            query: GraphQL query string
            variables: Query variables

        Returns:
            GraphQL response data

        Raises:
            GitHubAPIError: If API returns error response
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = await self._client.post(
            self.config.graphql_endpoint,
            json=payload,
        )

        if response.status_code != 200:
            raise GitHubAPIError(
                f"GraphQL request failed: {response.text}",
                status_code=response.status_code,
            )

        data = response.json()

        if "errors" in data:
            error_messages = [err.get("message", str(err)) for err in data["errors"]]
            raise GitHubAPIError(
                f"GraphQL errors: {', '.join(error_messages)}",
                response_data=data,
            )

        return data.get("data", {})

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _rest_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
    ) -> Dict:
        """Execute REST API request with retry logic.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint path (e.g., "/repos/org/repo/git/refs")
            json_data: Request JSON payload

        Returns:
            Response JSON data

        Raises:
            GitHubAPIError: If API returns error response
        """
        url = f"{self.config.api_url}{endpoint}"

        response = await self._client.request(
            method=method,
            url=url,
            json=json_data,
        )

        if response.status_code not in (200, 201, 204):
            raise GitHubAPIError(
                f"REST API request failed: {response.text}",
                status_code=response.status_code,
            )

        if response.status_code == 204:
            return {}

        return response.json()

    async def get_repository_id(self, repo: str) -> str:
        """Get repository node ID for GraphQL operations.

        Args:
            repo: Repository in format "owner/name"

        Returns:
            Repository node ID

        Raises:
            GitHubAPIError: If repository not found
        """
        owner, name = repo.split("/", 1)

        query = """
        query($owner: String!, $name: String!) {
            repository(owner: $owner, name: $name) {
                id
            }
        }
        """

        data = await self._graphql_request(
            query,
            variables={"owner": owner, "name": name},
        )

        if not data.get("repository"):
            raise GitHubAPIError(f"Repository {repo} not found")

        return data["repository"]["id"]

    async def get_default_branch(self, repo: str) -> str:
        """Get default branch name for repository.

        Args:
            repo: Repository in format "owner/name"

        Returns:
            Default branch name (e.g., "main" or "master")
        """
        owner, name = repo.split("/", 1)

        query = """
        query($owner: String!, $name: String!) {
            repository(owner: $owner, name: $name) {
                defaultBranchRef {
                    name
                }
            }
        }
        """

        data = await self._graphql_request(
            query,
            variables={"owner": owner, "name": name},
        )

        return data["repository"]["defaultBranchRef"]["name"]

    async def get_branch_sha(self, repo: str, branch: str) -> str:
        """Get latest commit SHA for a branch.

        Args:
            repo: Repository in format "owner/name"
            branch: Branch name

        Returns:
            Commit SHA
        """
        endpoint = f"/repos/{repo}/git/ref/heads/{branch}"
        data = await self._rest_request("GET", endpoint)
        return data["object"]["sha"]

    async def create_branch(
        self,
        repo: str,
        branch_name: str,
        from_branch: Optional[str] = None,
    ) -> str:
        """Create a new branch from base branch.

        Args:
            repo: Repository in format "owner/name"
            branch_name: Name for new branch
            from_branch: Base branch name (defaults to repository default branch)

        Returns:
            Created branch SHA

        Raises:
            GitHubAPIError: If branch already exists or base branch not found
        """
        if not from_branch:
            from_branch = await self.get_default_branch(repo)

        # Get base branch SHA
        base_sha = await self.get_branch_sha(repo, from_branch)

        # Create new branch reference
        endpoint = f"/repos/{repo}/git/refs"
        data = await self._rest_request(
            "POST",
            endpoint,
            json_data={
                "ref": f"refs/heads/{branch_name}",
                "sha": base_sha,
            },
        )

        logger.info(
            f"Created branch {branch_name} from {from_branch} at {base_sha[:7]}",
            extra={"repo": repo, "branch": branch_name, "base_sha": base_sha},
        )

        return data["object"]["sha"]

    async def commit_files(
        self,
        repo: str,
        branch: str,
        files: List[GitHubCommit],
        commit_message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
    ) -> str:
        """Commit multiple files to a branch.

        Uses Git Tree API to commit multiple files in a single commit.

        Args:
            repo: Repository in format "owner/name"
            branch: Branch name
            files: List of files to commit
            commit_message: Commit message
            author_name: Commit author name (optional)
            author_email: Commit author email (optional)

        Returns:
            Commit SHA

        Raises:
            GitHubAPIError: If commit fails
        """
        # Get current branch SHA
        branch_sha = await self.get_branch_sha(repo, branch)

        # Create tree with all files
        tree_items = []
        for file in files:
            # Encode content to base64 if needed
            if file.encoding == "utf-8":
                content = file.content
            else:
                content = base64.b64encode(file.content.encode()).decode()

            tree_items.append({
                "path": file.path,
                "mode": "100644",  # Regular file
                "type": "blob",
                "content": content,
            })

        # Create tree
        tree_endpoint = f"/repos/{repo}/git/trees"
        tree_data = await self._rest_request(
            "POST",
            tree_endpoint,
            json_data={"tree": tree_items},
        )
        tree_sha = tree_data["sha"]

        # Create commit
        commit_endpoint = f"/repos/{repo}/git/commits"
        commit_payload = {
            "message": commit_message,
            "tree": tree_sha,
            "parents": [branch_sha],
        }

        if author_name and author_email:
            commit_payload["author"] = {
                "name": author_name,
                "email": author_email,
            }

        commit_data = await self._rest_request(
            "POST",
            commit_endpoint,
            json_data=commit_payload,
        )
        commit_sha = commit_data["sha"]

        # Update branch reference
        ref_endpoint = f"/repos/{repo}/git/refs/heads/{branch}"
        await self._rest_request(
            "PATCH",
            ref_endpoint,
            json_data={"sha": commit_sha},
        )

        logger.info(
            f"Committed {len(files)} files to {branch}",
            extra={
                "repo": repo,
                "branch": branch,
                "commit_sha": commit_sha,
                "files": [f.path for f in files],
            },
        )

        return commit_sha

    async def create_pull_request(
        self,
        repo: str,
        branch_name: str,
        base_branch: str,
        files: List[GitHubCommit],
        commit_message: str,
        pr_title: str,
        pr_body: str,
        create_branch_if_missing: bool = True,
    ) -> PullRequest:
        """Create a pull request with artifacts.

        This is the main method for GitOps PR automation. It:
        1. Creates feature branch (if needed)
        2. Commits all files in a single commit
        3. Creates pull request

        Args:
            repo: Repository in format "owner/name"
            branch_name: Feature branch name (e.g., "slo-scout/payments-api-slos")
            base_branch: Base branch for PR (e.g., "main")
            files: Files to commit
            commit_message: Conventional commit message
            pr_title: Pull request title
            pr_body: Pull request body (supports Markdown)
            create_branch_if_missing: Create branch if it doesn't exist

        Returns:
            PullRequest object with URL and metadata

        Raises:
            GitHubAPIError: If any step fails
        """
        # Create branch if needed
        if create_branch_if_missing:
            try:
                await self.create_branch(repo, branch_name, base_branch)
            except GitHubAPIError as e:
                # Branch might already exist
                if "already exists" not in str(e).lower():
                    raise
                logger.info(f"Branch {branch_name} already exists, using existing branch")

        # Commit files
        await self.commit_files(
            repo=repo,
            branch=branch_name,
            files=files,
            commit_message=commit_message,
        )

        # Create pull request using GraphQL
        repo_id = await self.get_repository_id(repo)

        mutation = """
        mutation($repositoryId: ID!, $baseRefName: String!, $headRefName: String!, $title: String!, $body: String!) {
            createPullRequest(input: {
                repositoryId: $repositoryId
                baseRefName: $baseRefName
                headRefName: $headRefName
                title: $title
                body: $body
            }) {
                pullRequest {
                    number
                    url
                    title
                    state
                    createdAt
                }
            }
        }
        """

        data = await self._graphql_request(
            mutation,
            variables={
                "repositoryId": repo_id,
                "baseRefName": base_branch,
                "headRefName": branch_name,
                "title": pr_title,
                "body": pr_body,
            },
        )

        pr_data = data["createPullRequest"]["pullRequest"]

        pr = PullRequest(
            number=pr_data["number"],
            url=pr_data["url"],
            branch_name=branch_name,
            title=pr_data["title"],
            state=pr_data["state"],
            created_at=datetime.fromisoformat(pr_data["createdAt"].replace("Z", "+00:00")),
        )

        logger.info(
            f"Created PR #{pr.number}: {pr.title}",
            extra={
                "repo": repo,
                "pr_number": pr.number,
                "pr_url": pr.url,
                "branch": branch_name,
                "files_count": len(files),
            },
        )

        return pr
