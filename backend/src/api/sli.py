"""
SLI API endpoints (T127-T128)
Per api-sli.yaml contract
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import datetime
from typing import List

from .schemas import (
    SLIResponse,
    SLIDetailResponse,
    SLIListResponse,
    SLIUpdateRequest,
    EvidencePointer,
    ErrorResponse,
    MetricType,
)
from .deps import get_db
from ..models.sli import SLI
from ..models.evidence_pointer import EvidencePointer as EvidencePointerModel

router = APIRouter(prefix="/api/v1", tags=["SLI"])


@router.get(
    "/sli",
    response_model=SLIListResponse
)
async def list_slis(
    journey_id: UUID = Query(..., description="Journey ID to filter SLIs"),
    include_evidence: bool = Query(default=False, description="Include evidence pointers in response"),
    db: Session = Depends(get_db)
) -> SLIListResponse:
    """
    List SLI recommendations for a journey (T127)

    Per api-sli.yaml:
    - Filters by journey_id (required)
    - Optionally includes evidence pointers
    - Returns list of SLIs
    """
    # Query SLIs for journey
    slis = db.query(SLI).filter(
        SLI.journey_id == journey_id
    ).all()

    # Map to response schema
    if include_evidence:
        # Include evidence pointers
        sli_responses = []
        for sli in slis:
            # Get evidence pointers
            evidence_pointers = db.query(EvidencePointerModel).filter(
                EvidencePointerModel.sli_id == sli.sli_id
            ).all()

            evidence_list = [
                EvidencePointer(
                    capsule_id=ep.capsule_id,
                    trace_id=ep.trace_id,
                    timestamp=ep.created_at,
                    confidence_contribution=float(ep.confidence_contribution)
                )
                for ep in evidence_pointers
            ]

            sli_detail = SLIDetailResponse(
                sli_id=sli.sli_id,
                journey_id=sli.journey_id,
                name=sli.name,
                metric_type=MetricType(sli.metric_type.value),
                metric_definition=sli.metric_definition,
                confidence_score=float(sli.confidence_score),
                current_value=float(sli.current_value) if sli.current_value else None,
                unit=sli.unit,
                approved_by=sli.approved_by,
                approved_at=sli.approved_at,
                evidence_pointers=evidence_list
            )
            sli_responses.append(sli_detail)
    else:
        # Just basic SLI info
        sli_responses = [
            SLIResponse(
                sli_id=sli.sli_id,
                journey_id=sli.journey_id,
                name=sli.name,
                metric_type=MetricType(sli.metric_type.value),
                metric_definition=sli.metric_definition,
                confidence_score=float(sli.confidence_score),
                current_value=float(sli.current_value) if sli.current_value else None,
                unit=sli.unit,
                approved_by=sli.approved_by,
                approved_at=sli.approved_at
            )
            for sli in slis
        ]

    return SLIListResponse(slis=sli_responses)


@router.patch(
    "/sli/{sli_id}",
    response_model=SLIResponse,
    responses={
        404: {"model": ErrorResponse},
    }
)
async def update_sli(
    sli_id: UUID = Path(..., description="SLI ID to update"),
    request: SLIUpdateRequest = ...,
    db: Session = Depends(get_db)
) -> SLIResponse:
    """
    Update SLI (e.g., approve recommendation) (T128)

    Per api-sli.yaml:
    - Updates approved status and/or metric_definition_override
    - Returns updated SLI
    - Returns 404 if SLI not found
    """
    # Get SLI
    sli = db.query(SLI).filter(SLI.sli_id == sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SLI_NOT_FOUND",
                "message": f"SLI '{sli_id}' not found",
                "details": {"sli_id": str(sli_id)}
            }
        )

    # Update fields
    if request.approved is not None:
        if request.approved:
            sli.approved_by = "system"  # TODO: Get from auth context
            sli.approved_at = datetime.utcnow()
        else:
            sli.approved_by = None
            sli.approved_at = None

    if request.metric_definition_override is not None:
        sli.metric_definition = request.metric_definition_override

    db.commit()
    db.refresh(sli)

    # Return updated SLI
    return SLIResponse(
        sli_id=sli.sli_id,
        journey_id=sli.journey_id,
        name=sli.name,
        metric_type=MetricType(sli.metric_type.value),
        metric_definition=sli.metric_definition,
        confidence_score=float(sli.confidence_score),
        current_value=float(sli.current_value) if sli.current_value else None,
        unit=sli.unit,
        approved_by=sli.approved_by,
        approved_at=sli.approved_at
    )
