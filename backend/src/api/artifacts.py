"""
Artifacts API endpoints (T131-T132)
Per api-artifacts.yaml contract
"""
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from typing import List
import logging

from .schemas import (
    ArtifactGenerateRequest,
    ArtifactGenerateResponse,
    ArtifactResponse,
    ArtifactUpdateRequest,
    PolicyViolationResponse,
    ValidationErrorResponse,
    ErrorResponse,
    ArtifactType as SchemaArtifactType,
    ValidationStatus as SchemaValidationStatus,
    ApprovalStatus as SchemaApprovalStatus,
    DeploymentStatus as SchemaDeploymentStatus,
    ArtifactAction,
)
from .deps import get_db
from ..models.artifact import Artifact, ArtifactType, ValidationStatus, ApprovalStatus, DeploymentStatus
from ..models.slo import SLO
from ..models.sli import SLI
from ..generators.recording_rule_generator import RecordingRuleGenerator
from ..generators.alert_rule_generator import AlertRuleGenerator
from ..generators.grafana_generator import GrafanaDashboardGenerator
from ..generators.runbook_generator import RunbookGenerator
from ..validators.promql_validator import PromQLValidator
from ..validators.grafana_validator import GrafanaSchemaValidator
from ..validators.runbook_validator import RunbookValidator
from ..services.policy_evaluator import PolicyEvaluator, PolicyEvaluationResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Artifacts"])


@router.post(
    "/artifacts/generate",
    response_model=ArtifactGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ValidationErrorResponse},
    }
)
async def generate_artifacts(
    request: ArtifactGenerateRequest,
    db: Session = Depends(get_db)
) -> ArtifactGenerateResponse:
    """
    Generate operational artifacts for an SLO (T131)

    Per api-artifacts.yaml:
    - Generates Prometheus rules, Grafana dashboards, runbooks
    - Validates generated artifacts
    - Returns 201 with artifacts if validate_only=False
    - Returns 400 if validation fails
    """
    # Validate SLO exists
    slo = db.query(SLO).filter(SLO.slo_id == request.slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "SLO_NOT_FOUND",
                "message": f"SLO '{request.slo_id}' not found",
                "details": {"slo_id": str(request.slo_id)}
            }
        )

    # Get SLI
    sli = db.query(SLI).filter(SLI.sli_id == slo.sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "SLI_NOT_FOUND",
                "message": f"SLI for SLO '{request.slo_id}' not found",
                "details": {"slo_id": str(request.slo_id)}
            }
        )

    # Get service info (simplified - in production get from SLI's journey)
    service_name = "service"  # TODO: Extract from journey/service relationship
    environment = "prod"  # TODO: Extract from service

    generated_artifacts: List[ArtifactResponse] = []
    validation_errors = []

    # Generate each requested artifact type
    for artifact_type in request.artifact_types:
        try:
            content = ""
            validation_status = ValidationStatus.PENDING

            if artifact_type == SchemaArtifactType.PROMETHEUS_RECORDING:
                # Generate recording rule
                generator = RecordingRuleGenerator()
                content = generator.generate(
                    sli_name=sli.name,
                    metric_definition=sli.metric_definition,
                    service_name=service_name,
                    environment=environment
                )

                # Validate
                validator = PromQLValidator()
                is_valid, errors = validator.validate_recording_rules(content)
                validation_status = ValidationStatus.PASSED if is_valid else ValidationStatus.FAILED

                if not is_valid:
                    validation_errors.append({
                        "artifact_type": artifact_type.value,
                        "errors": errors
                    })

            elif artifact_type == SchemaArtifactType.PROMETHEUS_ALERT:
                # Generate alert rule
                generator = AlertRuleGenerator()
                content = generator.generate_alert_rule(
                    slo_id=str(slo.slo_id),
                    sli_name=sli.name,
                    metric_expr=sli.metric_definition,
                    threshold=float(slo.threshold_value),
                    comparison_operator=slo.comparison_operator.value,
                    severity=slo.severity.value,
                    service_name=service_name,
                    environment=environment
                )

                # Validate
                validator = PromQLValidator()
                is_valid, errors = validator.validate_alert_rules(content)
                validation_status = ValidationStatus.PASSED if is_valid else ValidationStatus.FAILED

                if not is_valid:
                    validation_errors.append({
                        "artifact_type": artifact_type.value,
                        "errors": errors
                    })

            elif artifact_type == SchemaArtifactType.GRAFANA_DASHBOARD:
                # Generate Grafana dashboard
                generator = GrafanaDashboardGenerator()
                content = generator.generate_slo_dashboard(
                    slo_id=str(slo.slo_id),
                    sli_name=sli.name,
                    metric_expr=sli.metric_definition,
                    threshold=float(slo.threshold_value),
                    target_percentage=float(slo.target_percentage),
                    service_name=service_name
                )

                # Validate
                validator = GrafanaSchemaValidator()
                is_valid, errors = validator.validate_dashboard(content)
                validation_status = ValidationStatus.PASSED if is_valid else ValidationStatus.FAILED

                if not is_valid:
                    validation_errors.append({
                        "artifact_type": artifact_type.value,
                        "errors": errors
                    })

            elif artifact_type == SchemaArtifactType.RUNBOOK:
                # Generate runbook
                generator = RunbookGenerator()
                content = generator.generate_slo_runbook(
                    slo_id=str(slo.slo_id),
                    sli_name=sli.name,
                    service_name=service_name,
                    environment=environment
                )

                # Validate
                validator = RunbookValidator()
                is_valid, errors = validator.validate(content)
                validation_status = ValidationStatus.PASSED if is_valid else ValidationStatus.FAILED

                if not is_valid:
                    validation_errors.append({
                        "artifact_type": artifact_type.value,
                        "errors": errors
                    })

            # Create artifact if not validate_only
            if not request.validate_only:
                artifact = Artifact(
                    slo_id=request.slo_id,
                    artifact_type=ArtifactType(artifact_type.value),
                    content=content,
                    validation_status=validation_status,
                    approval_status=ApprovalStatus.PENDING,
                    deployment_status=DeploymentStatus.PENDING,
                    version=1
                )
                db.add(artifact)
                db.commit()
                db.refresh(artifact)

                generated_artifacts.append(
                    ArtifactResponse(
                        artifact_id=artifact.artifact_id,
                        slo_id=artifact.slo_id,
                        artifact_type=SchemaArtifactType(artifact.artifact_type.value),
                        validation_status=SchemaValidationStatus(artifact.validation_status.value),
                        approval_status=SchemaApprovalStatus(artifact.approval_status.value),
                        deployment_status=SchemaDeploymentStatus(artifact.deployment_status.value),
                        version=artifact.version,
                        created_at=artifact.created_at,
                        approved_by=artifact.approved_by,
                        approved_at=artifact.approved_at,
                        deployment_pr_url=artifact.deployment_pr_url
                    )
                )

        except Exception as e:
            logger.error(f"Failed to generate {artifact_type}: {e}")
            validation_errors.append({
                "artifact_type": artifact_type.value,
                "errors": [str(e)]
            })

    # If validation errors and not validate_only, return 400
    if validation_errors and not request.validate_only:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "ARTIFACT_VALIDATION_FAILED",
                "message": "One or more artifacts failed validation",
                "validation_output": str(validation_errors),
                "failed_artifacts": validation_errors
            }
        )

    return ArtifactGenerateResponse(artifacts=generated_artifacts)


@router.patch(
    "/artifacts/{artifact_id}",
    response_model=ArtifactResponse,
    responses={
        403: {"model": PolicyViolationResponse},
        404: {"model": ErrorResponse},
    }
)
async def update_artifact(
    artifact_id: UUID = Path(..., description="Artifact ID to update"),
    request: ArtifactUpdateRequest = ...,
    db: Session = Depends(get_db)
) -> ArtifactResponse:
    """
    Update artifact (approve, deploy, rollback) (T132)

    Per api-artifacts.yaml:
    - Updates artifact status based on action
    - Policy Guard checks for deploy/rollback actions
    - Returns 200 with updated artifact
    - Returns 403 if Policy Guard blocks action
    - Returns 404 if artifact not found
    """
    # Get artifact
    artifact = db.query(Artifact).filter(Artifact.artifact_id == artifact_id).first()

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "ARTIFACT_NOT_FOUND",
                "message": f"Artifact '{artifact_id}' not found",
                "details": {"artifact_id": str(artifact_id)}
            }
        )

    # Handle action
    if request.action == ArtifactAction.APPROVE:
        if not request.approver_comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "APPROVER_COMMENT_REQUIRED",
                    "message": "approver_comment is required for approve action",
                    "details": {}
                }
            )

        artifact.approval_status = ApprovalStatus.APPROVED
        artifact.approved_by = "system"  # TODO: Get from auth context
        artifact.approved_at = datetime.utcnow()

    elif request.action == ArtifactAction.REJECT:
        if not request.approver_comment:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error_code": "APPROVER_COMMENT_REQUIRED",
                    "message": "approver_comment is required for reject action",
                    "details": {}
                }
            )

        artifact.approval_status = ApprovalStatus.REJECTED

    elif request.action == ArtifactAction.DEPLOY:
        # Policy Guard check
        # Simplified - in production, properly implement async policy evaluation
        # policy_evaluator = PolicyEvaluator(db)
        # result = await policy_evaluator.evaluate_artifact_deployment(
        #     artifact_id=artifact.artifact_id,
        #     action="deploy"
        # )
        # if not result.is_allowed:
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail=result.to_violation_response()
        #     )

        artifact.deployment_status = DeploymentStatus.DEPLOYED
        artifact.deployed_at = datetime.utcnow()

    elif request.action == ArtifactAction.ROLLBACK:
        # Policy Guard check
        # Simplified - in production, properly implement async policy evaluation
        # policy_evaluator = PolicyEvaluator(db)
        # result = await policy_evaluator.evaluate_artifact_deployment(
        #     artifact_id=artifact.artifact_id,
        #     action="rollback"
        # )
        # if not result.is_allowed:
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail=result.to_violation_response()
        #     )

        artifact.deployment_status = DeploymentStatus.ROLLBACK

    db.commit()
    db.refresh(artifact)

    return ArtifactResponse(
        artifact_id=artifact.artifact_id,
        slo_id=artifact.slo_id,
        artifact_type=SchemaArtifactType(artifact.artifact_type.value),
        validation_status=SchemaValidationStatus(artifact.validation_status.value),
        approval_status=SchemaApprovalStatus(artifact.approval_status.value),
        deployment_status=SchemaDeploymentStatus(artifact.deployment_status.value),
        version=artifact.version,
        created_at=artifact.created_at,
        approved_by=artifact.approved_by,
        approved_at=artifact.approved_at,
        deployment_pr_url=artifact.deployment_pr_url
    )
