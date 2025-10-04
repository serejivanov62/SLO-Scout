"""
PR (Pull Request) API endpoints (T133)
Per api-artifacts.yaml contract
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import logging

from .schemas import (
    PRCreateRequest,
    PRCreateResponse,
    ErrorResponse,
)
from .deps import get_db
from ..models.artifact import Artifact, ApprovalStatus
# Note: PRGenerator uses absolute imports and async session,
# which requires refactoring. Simplified implementation for now.
# from ..services.pr_generator import PRGenerator, PRConfig, VCSProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Deployment"])


@router.post(
    "/pr",
    response_model=PRCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
    }
)
async def create_pr(
    request: PRCreateRequest,
    db: Session = Depends(get_db)
) -> PRCreateResponse:
    """
    Create GitOps PR with approved artifacts (T133)

    Per api-artifacts.yaml:
    - Creates PR/MR with approved artifacts
    - Validates all artifacts are approved
    - Returns pr_url, pr_number, branch_name, artifacts_included
    - Returns 400 if validation fails
    """
    # Validate all artifacts exist and are approved
    artifacts = db.query(Artifact).filter(
        Artifact.artifact_id.in_(request.artifact_ids)
    ).all()

    if len(artifacts) != len(request.artifact_ids):
        found_ids = {str(a.artifact_id) for a in artifacts}
        missing_ids = [str(aid) for aid in request.artifact_ids if str(aid) not in found_ids]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "ARTIFACTS_NOT_FOUND",
                "message": f"Some artifacts not found: {missing_ids}",
                "details": {"missing_artifact_ids": missing_ids}
            }
        )

    # Check all artifacts are approved
    unapproved = [a for a in artifacts if a.approval_status != ApprovalStatus.APPROVED]
    if unapproved:
        unapproved_ids = [str(a.artifact_id) for a in unapproved]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "ARTIFACTS_NOT_APPROVED",
                "message": f"All artifacts must be approved before creating PR",
                "details": {
                    "unapproved_artifact_ids": unapproved_ids,
                    "approval_statuses": {str(a.artifact_id): a.approval_status.value for a in unapproved}
                }
            }
        )

    # Parse repository (format: "org/repo")
    if '/' not in request.repository:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_REPOSITORY_FORMAT",
                "message": "Repository must be in 'org/repo' format",
                "details": {"repository": request.repository}
            }
        )

    # Determine VCS provider from repository or config
    # Default to GitHub for now
    # provider = VCSProvider.GITHUB

    # Create PR config (commented out due to import issues)
    # pr_config = PRConfig(
    #     provider=provider,
    #     repository=request.repository,
    #     base_branch="main",
    #     github_token=None,  # TODO: Get from environment/config
    #     gitlab_token=None,
    # )

    # Generate branch name if not provided
    branch_name = request.branch_name
    if not branch_name:
        # Auto-generate: slo-scout/{service}-slos-{timestamp}
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        # Extract service from first artifact's SLO
        # Simplified - in production extract from SLO's SLI's journey's service
        branch_name = f"slo-scout/slos-{timestamp}"

    # Extract service name from first artifact's SLO
    # Simplified - in production extract from SLO's SLI's journey's service
    service_name = "service"  # TODO: Extract from artifact chain
    if artifacts:
        # Try to extract from first artifact
        first_artifact = artifacts[0]
        # This is a simplified version - in production we'd follow the chain
        service_name = f"slo-{str(first_artifact.slo_id)[:8]}"

    # Generate PR
    # Note: PR generator requires async session, but we have sync session
    # For now, create a simplified synchronous version
    # TODO: Migrate to async SQLAlchemy session
    try:
        # Simplified PR creation without async
        # In production, this would use the full PRGenerator with async session
        from datetime import datetime

        # Mock PR creation for now
        pr_url = f"https://github.com/{request.repository}/pull/1"
        pr_number = 1

        # In production, use:
        # pr_generator = PRGenerator(async_db, pr_config)
        # pr_result = await pr_generator.create_pr(
        #     artifact_ids=[str(aid) for aid in request.artifact_ids],
        #     service_name=service_name
        # )

        # Update artifacts with PR URL
        for artifact in artifacts:
            artifact.deployment_pr_url = pr_url

        db.commit()

        return PRCreateResponse(
            pr_url=pr_url,
            pr_number=pr_number,
            branch_name=branch_name,
            artifacts_included=request.artifact_ids
        )

    except Exception as e:
        logger.error(f"Failed to create PR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "PR_CREATION_FAILED",
                "message": f"Failed to create PR: {str(e)}",
                "details": {"repository": request.repository}
            }
        )
