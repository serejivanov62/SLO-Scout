"""
Artifacts API router - Artifact generation and deployment endpoints
Implements artifacts-api.yaml contract
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..models.artifact import Artifact, ArtifactTypeEnum, ArtifactStatusEnum
from ..models.slo import SLO
from ..services.policy_evaluator import PolicyEvaluator
from .deps import get_db

# Create router
router = APIRouter(prefix="/api/v1", tags=["Artifacts"])


# Pydantic schemas per contract
class ArtifactGenerate(BaseModel):
    """Artifact generation request schema"""
    slo_id: UUID
    artifact_type: str = Field(..., pattern="^(prometheus_rule|grafana_dashboard|runbook)$")


class ArtifactUpdate(BaseModel):
    """Artifact update request schema"""
    content: str


class ArtifactDeploy(BaseModel):
    """Artifact deployment request schema"""
    repository: Optional[str] = Field(None, description="Target GitHub repository (org/repo format)")
    branch_prefix: Optional[str] = Field(default="slo-scout", description="Custom branch name prefix")


class PolicyResult(BaseModel):
    """Policy evaluation result schema"""
    blast_radius_score: float
    threshold: float
    passed: bool
    details: Dict[str, Any]


class ArtifactResponse(BaseModel):
    """Artifact response schema"""
    artifact_id: str
    slo_id: str
    artifact_type: str
    content: str
    confidence_score: float
    status: str
    pr_url: Optional[str] = None
    deployed_at: Optional[str] = None
    created_at: str

    @classmethod
    def from_orm(cls, artifact: Artifact):
        """Convert SQLAlchemy model to Pydantic schema"""
        return cls(
            artifact_id=str(artifact.artifact_id),
            slo_id=str(artifact.slo_id),
            artifact_type=artifact.artifact_type.value,
            content=artifact.content,
            confidence_score=float(artifact.confidence_score),
            status=artifact.status.value,
            pr_url=artifact.pr_url,
            deployed_at=artifact.deployed_at.isoformat() if artifact.deployed_at else None,
            created_at=artifact.created_at.isoformat()
        )


class ArtifactListResponse(BaseModel):
    """Artifact list response schema"""
    artifacts: list[ArtifactResponse]
    total: int
    limit: int
    offset: int


class DeploymentResponse(BaseModel):
    """Deployment initiation response schema"""
    artifact_id: str
    status: str
    pr_url: Optional[str] = None
    policy_result: Optional[PolicyResult] = None


class RollbackResponse(BaseModel):
    """Rollback response schema"""
    artifact_id: str
    status: str
    pr_url: str


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Route handlers
@router.get("/artifacts", response_model=ArtifactListResponse, status_code=status.HTTP_200_OK)
async def list_artifacts(
    slo_id: Optional[UUID] = Query(None),
    artifact_type: Optional[str] = Query(None, pattern="^(prometheus_rule|grafana_dashboard|runbook)$"),
    artifact_status: Optional[str] = Query(None, alias="status", pattern="^(draft|deployed|rolled_back)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> ArtifactListResponse:
    """List artifacts with optional filtering"""
    query = db.query(Artifact)

    # Apply filters
    if slo_id:
        query = query.filter(Artifact.slo_id == slo_id)

    if artifact_type:
        query = query.filter(Artifact.artifact_type == ArtifactTypeEnum(artifact_type))

    if artifact_status:
        query = query.filter(Artifact.status == ArtifactStatusEnum(artifact_status))

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    artifacts = query.offset(offset).limit(limit).all()

    return ArtifactListResponse(
        artifacts=[ArtifactResponse.from_orm(a) for a in artifacts],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/artifacts/generate", response_model=ArtifactResponse, status_code=status.HTTP_201_CREATED)
async def generate_artifact(
    artifact_data: ArtifactGenerate,
    db: Session = Depends(get_db)
) -> ArtifactResponse:
    """Generate a new configuration artifact from an SLO"""
    # Validate SLO exists
    slo = db.query(SLO).filter(SLO.slo_id == artifact_data.slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLO_NOT_FOUND",
                "message": f"SLO with ID '{artifact_data.slo_id}' not found",
                "details": {}
            }
        )

    # TODO: Integrate with ArtifactGenerator service to generate content
    # For now, create mock content based on type
    content = _generate_mock_content(artifact_data.artifact_type, slo)

    # Create artifact
    new_artifact = Artifact(
        slo_id=artifact_data.slo_id,
        artifact_type=ArtifactTypeEnum(artifact_data.artifact_type),
        content=content,
        confidence_score=Decimal("0.92"),  # Mock confidence score
        status=ArtifactStatusEnum.DRAFT
    )

    db.add(new_artifact)
    db.commit()
    db.refresh(new_artifact)

    return ArtifactResponse.from_orm(new_artifact)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse, status_code=status.HTTP_200_OK)
async def get_artifact(
    artifact_id: UUID,
    db: Session = Depends(get_db)
) -> ArtifactResponse:
    """Get artifact by ID"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    return ArtifactResponse.from_orm(artifact)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactResponse, status_code=status.HTTP_200_OK)
async def update_artifact(
    artifact_id: UUID,
    update_data: ArtifactUpdate,
    db: Session = Depends(get_db)
) -> ArtifactResponse:
    """Update artifact content (manual edits before deployment)"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    # Check if artifact is in draft status
    if artifact.status != ArtifactStatusEnum.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "CANNOT_UPDATE_DEPLOYED",
                "message": "Cannot update deployed artifact",
                "details": {"status": artifact.status.value}
            }
        )

    # Update content
    artifact.content = update_data.content

    db.commit()
    db.refresh(artifact)

    return ArtifactResponse.from_orm(artifact)


@router.delete("/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(
    artifact_id: UUID,
    db: Session = Depends(get_db)
) -> None:
    """Delete an artifact (only allowed for draft status)"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    # Check if artifact is deployed
    if artifact.status == ArtifactStatusEnum.DEPLOYED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "CANNOT_DELETE_DEPLOYED",
                "message": "Cannot delete deployed artifact (rollback first)",
                "details": {"status": artifact.status.value}
            }
        )

    # Delete artifact
    db.delete(artifact)
    db.commit()


@router.patch("/artifacts/{artifact_id}/deploy", response_model=DeploymentResponse, status_code=status.HTTP_200_OK)
async def deploy_artifact(
    artifact_id: UUID,
    deploy_data: Optional[ArtifactDeploy] = None,
    db: Session = Depends(get_db)
) -> DeploymentResponse:
    """Deploy artifact by creating GitHub PR (subject to policy guard)"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    # Check if already deployed
    if artifact.status == ArtifactStatusEnum.DEPLOYED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "ALREADY_DEPLOYED",
                "message": "Artifact already deployed",
                "details": {"pr_url": artifact.pr_url}
            }
        )

    # Check if artifact is ready for deployment
    if artifact.status != ArtifactStatusEnum.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "NOT_DEPLOYABLE",
                "message": f"Artifact in status '{artifact.status.value}' cannot be deployed",
                "details": {}
            }
        )

    # Evaluate against policy guard
    policy_evaluator = PolicyEvaluator(db)
    policy_result = await policy_evaluator.evaluate_artifact_deployment(
        artifact_id=artifact_id,
        action="deploy"
    )

    # If policy blocks, return pending approval status
    if not policy_result.is_allowed:
        policy_details = PolicyResult(
            blast_radius_score=float(policy_result.blast_radius_metrics.affected_services_percentage) if policy_result.blast_radius_metrics else 0.0,
            threshold=0.70,  # Mock threshold
            passed=False,
            details=policy_result.violated_invariants
        )

        return DeploymentResponse(
            artifact_id=str(artifact_id),
            status="pending_approval",
            pr_url=None,
            policy_result=policy_details
        )

    # TODO: Integrate with PR generator service to create GitHub PR
    pr_url = f"https://github.com/org/infrastructure/pull/{artifact_id.int % 1000}"

    # Update artifact status
    artifact.status = ArtifactStatusEnum.DEPLOYED
    artifact.pr_url = pr_url
    artifact.deployed_at = datetime.now(timezone.utc)

    db.commit()

    policy_details = PolicyResult(
        blast_radius_score=float(policy_result.blast_radius_metrics.affected_services_percentage) if policy_result.blast_radius_metrics else 0.0,
        threshold=0.70,
        passed=True,
        details={}
    ) if policy_result.blast_radius_metrics else None

    return DeploymentResponse(
        artifact_id=str(artifact_id),
        status="deployed",
        pr_url=pr_url,
        policy_result=policy_details
    )


@router.patch("/artifacts/{artifact_id}/rollback", response_model=RollbackResponse, status_code=status.HTTP_200_OK)
async def rollback_artifact(
    artifact_id: UUID,
    reason: Optional[str] = None,
    db: Session = Depends(get_db)
) -> RollbackResponse:
    """Rollback deployed artifact and create rollback PR"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    # Check if artifact is deployed
    if artifact.status != ArtifactStatusEnum.DEPLOYED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "NOT_DEPLOYED",
                "message": f"Artifact not in deployed status (current: {artifact.status.value})",
                "details": {}
            }
        )

    # TODO: Integrate with PR generator service to create rollback PR
    rollback_pr_url = f"https://github.com/org/infrastructure/pull/{(artifact_id.int % 1000) + 1}"

    # Update artifact status
    artifact.status = ArtifactStatusEnum.ROLLED_BACK

    db.commit()

    return RollbackResponse(
        artifact_id=str(artifact_id),
        status="rolled_back",
        pr_url=rollback_pr_url
    )


@router.get("/artifacts/{artifact_id}/preview", status_code=status.HTTP_200_OK)
async def preview_artifact(
    artifact_id: UUID,
    db: Session = Depends(get_db)
) -> Response:
    """Preview artifact content for review before deployment"""
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact with ID '{artifact_id}' not found",
                "details": {}
            }
        )

    # Return content with appropriate content type
    if artifact.artifact_type in [ArtifactTypeEnum.PROMETHEUS_RULE, ArtifactTypeEnum.RUNBOOK]:
        return Response(content=artifact.content, media_type="text/yaml")
    else:  # GRAFANA_DASHBOARD
        return Response(content=artifact.content, media_type="application/json")


def _generate_mock_content(artifact_type: str, slo: SLO) -> str:
    """Generate mock artifact content based on type"""
    if artifact_type == "prometheus_rule":
        return f"""groups:
  - name: {slo.name.lower().replace(' ', '-')}-slo
    rules:
      - record: slo:{slo.name.lower().replace(' ', '_')}:5m
        expr: sum(rate(http_requests_total{{}}[5m]))
      - alert: {slo.name}Budget
        expr: slo:{slo.name.lower().replace(' ', '_')}:5m < {float(slo.target_percentage) / 100}
        labels:
          severity: warning
"""
    elif artifact_type == "grafana_dashboard":
        return f'{{"title": "{slo.name} Dashboard", "panels": []}}'
    else:  # runbook
        return f"""# Runbook: {slo.name}

## Overview
This SLO monitors {slo.name} with a target of {slo.target_percentage}%.

## Investigation Steps
1. Check service health
2. Review recent deployments
3. Analyze error logs
"""
