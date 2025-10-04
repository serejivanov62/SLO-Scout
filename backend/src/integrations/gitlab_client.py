"""GitLab client for GitOps MR automation.

This module provides a client for GitLab REST API to create merge requests,
branches, and commit artifacts as part of the GitOps deployment workflow.

Implementation follows research.md GitLab integration decisions:
- REST API v4 for MR creation
- OAuth token or PAT authentication
- Feature branch naming: slo-scout/{service}-slos
- Conventional commit messages
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


logger = logging.getLogger(__name__)


@dataclass
class GitLabConfig:
    """GitLab API configuration."""

    token: str
    api_url: str = "https://gitlab.com/api/v4"
    timeout: int = 30
    max_retries: int = 3


@dataclass
class MergeRequest:
    """Represents a created merge request."""

    iid: int  # Internal ID (shown in UI)
    web_url: str
    branch_name: str
    title: str
    state: str
    created_at: datetime


@dataclass
class GitLabCommit:
    """Represents a file action to commit."""

    path: str
    content: str
    action: str = "create"  # create, update, delete
    encoding: str = "text"  # text or base64


class GitLabAPIError(Exception):
    """Raised when GitLab API returns an error."""

    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class GitLabClient:
    """Client for GitLab REST API v4 for GitOps automation.

    Supports:
    - Creating feature branches from default branch
    - Committing multiple files in a single commit
    - Creating merge requests with templated body
    - Conventional commit message formatting

    Authentication:
    - OAuth token (recommended for apps)
    - Personal Access Token (PAT) for individual users

    Required token scopes:
    - api (full API access)
    - write_repository (commit to repositories)

    Example:
        >>> config = GitLabConfig(token="glpat-...")
        >>> client = GitLabClient(config)
        >>> mr = await client.create_merge_request(
        ...     project="org/observability-config",
        ...     branch_name="slo-scout/payments-api-slos",
        ...     target_branch="main",
        ...     files=[GitLabCommit(path="prometheus/rules.yml", content="...")],
        ...     commit_message="feat(slos): add SLOs for payments-api",
        ...     mr_title="Add SLOs for payments-api service",
        ...     mr_description="## Summary\\n- Add SLI/SLO definitions\\n- Add Prometheus rules"
        ... )
        >>> print(mr.web_url)
        https://gitlab.com/org/observability-config/-/merge_requests/123
    """

    def __init__(self, config: GitLabConfig):
        """Initialize GitLab client.

        Args:
            config: GitLab API configuration with authentication token
        """
        self.config = config
        self._client = httpx.AsyncClient(
            headers={
                "PRIVATE-TOKEN": config.token,
                "Content-Type": "application/json",
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
    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict:
        """Execute REST API request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint path (e.g., "/projects/123/repository/branches")
            json_data: Request JSON payload
            params: Query parameters

        Returns:
            Response JSON data

        Raises:
            GitLabAPIError: If API returns error response
        """
        url = f"{self.config.api_url}{endpoint}"

        response = await self._client.request(
            method=method,
            url=url,
            json=json_data,
            params=params,
        )

        if response.status_code not in (200, 201, 204):
            raise GitLabAPIError(
                f"GitLab API request failed: {response.text}",
                status_code=response.status_code,
                response_data=response.json() if response.text else None,
            )

        if response.status_code == 204:
            return {}

        return response.json()

    def _encode_project(self, project: str) -> str:
        """URL-encode project path for API calls.

        GitLab API requires project path to be URL-encoded.

        Args:
            project: Project in format "group/project" or "group/subgroup/project"

        Returns:
            URL-encoded project path
        """
        # GitLab accepts slash-encoded project paths
        return project.replace("/", "%2F")

    async def get_project_info(self, project: str) -> Dict:
        """Get project information including ID and default branch.

        Args:
            project: Project in format "group/project"

        Returns:
            Project data dictionary

        Raises:
            GitLabAPIError: If project not found
        """
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}"

        data = await self._request("GET", endpoint)

        logger.debug(
            f"Retrieved project info for {project}",
            extra={"project_id": data["id"], "default_branch": data["default_branch"]},
        )

        return data

    async def get_default_branch(self, project: str) -> str:
        """Get default branch name for project.

        Args:
            project: Project in format "group/project"

        Returns:
            Default branch name (e.g., "main" or "master")
        """
        project_info = await self.get_project_info(project)
        return project_info["default_branch"]

    async def get_branch_commit(self, project: str, branch: str) -> str:
        """Get latest commit SHA for a branch.

        Args:
            project: Project in format "group/project"
            branch: Branch name

        Returns:
            Commit SHA
        """
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/repository/branches/{branch}"

        data = await self._request("GET", endpoint)
        return data["commit"]["id"]

    async def create_branch(
        self,
        project: str,
        branch_name: str,
        from_branch: Optional[str] = None,
    ) -> str:
        """Create a new branch from base branch.

        Args:
            project: Project in format "group/project"
            branch_name: Name for new branch
            from_branch: Base branch name (defaults to project default branch)

        Returns:
            Created branch commit SHA

        Raises:
            GitLabAPIError: If branch already exists or base branch not found
        """
        if not from_branch:
            from_branch = await self.get_default_branch(project)

        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/repository/branches"

        data = await self._request(
            "POST",
            endpoint,
            json_data={
                "branch": branch_name,
                "ref": from_branch,
            },
        )

        logger.info(
            f"Created branch {branch_name} from {from_branch}",
            extra={
                "project": project,
                "branch": branch_name,
                "commit_sha": data["commit"]["id"],
            },
        )

        return data["commit"]["id"]

    async def commit_files(
        self,
        project: str,
        branch: str,
        files: List[GitLabCommit],
        commit_message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
    ) -> str:
        """Commit multiple files to a branch.

        Uses GitLab Commits API to commit multiple files in a single commit.

        Args:
            project: Project in format "group/project"
            branch: Branch name
            files: List of file actions to commit
            commit_message: Commit message
            author_name: Commit author name (optional)
            author_email: Commit author email (optional)

        Returns:
            Commit SHA

        Raises:
            GitLabAPIError: If commit fails
        """
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/repository/commits"

        # Build actions array
        actions = []
        for file in files:
            actions.append({
                "action": file.action,
                "file_path": file.path,
                "content": file.content,
                "encoding": file.encoding,
            })

        payload = {
            "branch": branch,
            "commit_message": commit_message,
            "actions": actions,
        }

        if author_name:
            payload["author_name"] = author_name
        if author_email:
            payload["author_email"] = author_email

        data = await self._request("POST", endpoint, json_data=payload)

        logger.info(
            f"Committed {len(files)} files to {branch}",
            extra={
                "project": project,
                "branch": branch,
                "commit_sha": data["id"],
                "files": [f.path for f in files],
            },
        )

        return data["id"]

    async def create_merge_request(
        self,
        project: str,
        branch_name: str,
        target_branch: str,
        files: List[GitLabCommit],
        commit_message: str,
        mr_title: str,
        mr_description: str,
        create_branch_if_missing: bool = True,
        remove_source_branch: bool = True,
        squash: bool = False,
    ) -> MergeRequest:
        """Create a merge request with artifacts.

        This is the main method for GitOps MR automation. It:
        1. Creates feature branch (if needed)
        2. Commits all files in a single commit
        3. Creates merge request

        Args:
            project: Project in format "group/project"
            branch_name: Source branch name (e.g., "slo-scout/payments-api-slos")
            target_branch: Target branch for MR (e.g., "main")
            files: Files to commit
            commit_message: Conventional commit message
            mr_title: Merge request title
            mr_description: Merge request description (supports Markdown)
            create_branch_if_missing: Create branch if it doesn't exist
            remove_source_branch: Delete source branch after merge
            squash: Enable squash commits on merge

        Returns:
            MergeRequest object with URL and metadata

        Raises:
            GitLabAPIError: If any step fails
        """
        # Create branch if needed
        if create_branch_if_missing:
            try:
                await self.create_branch(project, branch_name, target_branch)
            except GitLabAPIError as e:
                # Branch might already exist
                if "already exists" not in str(e).lower():
                    raise
                logger.info(f"Branch {branch_name} already exists, using existing branch")

        # Commit files
        await self.commit_files(
            project=project,
            branch=branch_name,
            files=files,
            commit_message=commit_message,
        )

        # Create merge request
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/merge_requests"

        mr_data = await self._request(
            "POST",
            endpoint,
            json_data={
                "source_branch": branch_name,
                "target_branch": target_branch,
                "title": mr_title,
                "description": mr_description,
                "remove_source_branch": remove_source_branch,
                "squash": squash,
            },
        )

        mr = MergeRequest(
            iid=mr_data["iid"],
            web_url=mr_data["web_url"],
            branch_name=branch_name,
            title=mr_data["title"],
            state=mr_data["state"],
            created_at=datetime.fromisoformat(mr_data["created_at"]),
        )

        logger.info(
            f"Created MR !{mr.iid}: {mr.title}",
            extra={
                "project": project,
                "mr_iid": mr.iid,
                "mr_url": mr.web_url,
                "branch": branch_name,
                "files_count": len(files),
            },
        )

        return mr

    async def update_merge_request(
        self,
        project: str,
        mr_iid: int,
        title: Optional[str] = None,
        description: Optional[str] = None,
        state_event: Optional[str] = None,
    ) -> MergeRequest:
        """Update merge request properties.

        Args:
            project: Project in format "group/project"
            mr_iid: Merge request internal ID
            title: New title (optional)
            description: New description (optional)
            state_event: State change: "close" or "reopen" (optional)

        Returns:
            Updated MergeRequest object
        """
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/merge_requests/{mr_iid}"

        payload = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if state_event is not None:
            payload["state_event"] = state_event

        mr_data = await self._request("PUT", endpoint, json_data=payload)

        mr = MergeRequest(
            iid=mr_data["iid"],
            web_url=mr_data["web_url"],
            branch_name=mr_data["source_branch"],
            title=mr_data["title"],
            state=mr_data["state"],
            created_at=datetime.fromisoformat(mr_data["created_at"]),
        )

        logger.info(f"Updated MR !{mr.iid}", extra={"project": project, "mr_iid": mr.iid})

        return mr

    async def add_merge_request_comment(
        self,
        project: str,
        mr_iid: int,
        comment: str,
    ) -> Dict:
        """Add a comment to a merge request.

        Args:
            project: Project in format "group/project"
            mr_iid: Merge request internal ID
            comment: Comment body (supports Markdown)

        Returns:
            Created comment data
        """
        encoded_project = self._encode_project(project)
        endpoint = f"/projects/{encoded_project}/merge_requests/{mr_iid}/notes"

        data = await self._request(
            "POST",
            endpoint,
            json_data={"body": comment},
        )

        logger.info(
            f"Added comment to MR !{mr_iid}",
            extra={"project": project, "mr_iid": mr_iid, "note_id": data["id"]},
        )

        return data
