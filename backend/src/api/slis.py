"""
SLI API router - Service Level Indicator recommendation and approval endpoints
Implements sli-api.yaml contract
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..models.sli import SLI
from ..models.user_journey import UserJourney
from .deps import get_db

# Create router
router = APIRouter(prefix="/api/v1", tags=["SLI"])


# Pydantic schemas per contract
class SLIApproval(BaseModel):
    """SLI approval request schema"""
    approved_by: str = Field(..., min_length=1, max_length=255)


class SLIUpdate(BaseModel):
    """SLI update request schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    promql_query: Optional[str] = None


class SLIResponse(BaseModel):
    """SLI response schema"""
    sli_id: str
    journey_id: str
    name: str
    description: Optional[str] = None
    promql_query: str
    confidence_score: float
    approved: bool
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: str

    @classmethod
    def from_orm(cls, sli: SLI):
        """Convert SQLAlchemy model to Pydantic schema"""
        return cls(
            sli_id=str(sli.sli_id),
            journey_id=str(sli.journey_id),
            name=sli.name,
            description=sli.description,
            promql_query=sli.promql_query,
            confidence_score=float(sli.confidence_score),
            approved=sli.approved,
            approved_by=sli.approved_by,
            approved_at=sli.approved_at.isoformat() if sli.approved_at else None,
            created_at=sli.created_at.isoformat()
        )


class SLIListResponse(BaseModel):
    """SLI list response schema"""
    slis: list[SLIResponse]
    total: int
    limit: int
    offset: int


class ValidationResult(BaseModel):
    """PromQL validation result schema"""
    valid: bool
    errors: list[str] = []
    sample_result: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Route handlers
@router.get("/sli", response_model=SLIListResponse, status_code=status.HTTP_200_OK)
async def list_slis(
    journey_id: Optional[UUID] = Query(None),
    approved: Optional[bool] = Query(None),
    min_confidence: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> SLIListResponse:
    """List SLI recommendations with optional filtering"""
    query = db.query(SLI)

    # Apply filters
    if journey_id:
        query = query.filter(SLI.journey_id == journey_id)

    if approved is not None:
        query = query.filter(SLI.approved == approved)

    if min_confidence is not None:
        query = query.filter(SLI.confidence_score >= min_confidence)

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    slis = query.offset(offset).limit(limit).all()

    return SLIListResponse(
        slis=[SLIResponse.from_orm(s) for s in slis],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/sli/{sli_id}", response_model=SLIResponse, status_code=status.HTTP_200_OK)
async def get_sli(
    sli_id: UUID,
    db: Session = Depends(get_db)
) -> SLIResponse:
    """Get SLI by ID"""
    sli = db.query(SLI).filter(SLI.sli_id == sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLI_NOT_FOUND",
                "message": f"SLI with ID '{sli_id}' not found",
                "details": {}
            }
        )

    return SLIResponse.from_orm(sli)


@router.patch("/sli/{sli_id}", response_model=SLIResponse, status_code=status.HTTP_200_OK)
async def update_sli(
    sli_id: UUID,
    update_data: SLIUpdate,
    db: Session = Depends(get_db)
) -> SLIResponse:
    """Update SLI details"""
    sli = db.query(SLI).filter(SLI.sli_id == sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLI_NOT_FOUND",
                "message": f"SLI with ID '{sli_id}' not found",
                "details": {}
            }
        )

    # Apply updates
    if update_data.name is not None:
        sli.name = update_data.name

    if update_data.description is not None:
        sli.description = update_data.description

    if update_data.promql_query is not None:
        # TODO: Validate PromQL query using promtool
        sli.promql_query = update_data.promql_query

    db.commit()
    db.refresh(sli)

    return SLIResponse.from_orm(sli)


@router.patch("/sli/{sli_id}/approve", response_model=SLIResponse, status_code=status.HTTP_200_OK)
async def approve_sli(
    sli_id: UUID,
    approval_data: SLIApproval,
    db: Session = Depends(get_db)
) -> SLIResponse:
    """Approve SLI recommendation"""
    sli = db.query(SLI).filter(SLI.sli_id == sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLI_NOT_FOUND",
                "message": f"SLI with ID '{sli_id}' not found",
                "details": {}
            }
        )

    # Check if already approved
    if sli.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ALREADY_APPROVED",
                "message": "SLI is already approved",
                "details": {
                    "approved_by": sli.approved_by,
                    "approved_at": sli.approved_at.isoformat() if sli.approved_at else None
                }
            }
        )

    # Approve SLI
    sli.approved = True
    sli.approved_by = approval_data.approved_by
    sli.approved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(sli)

    return SLIResponse.from_orm(sli)


@router.post("/sli/{sli_id}/validate", response_model=ValidationResult, status_code=status.HTTP_200_OK)
async def validate_sli(
    sli_id: UUID,
    db: Session = Depends(get_db)
) -> ValidationResult:
    """Validate PromQL query against target Prometheus instance"""
    sli = db.query(SLI).filter(SLI.sli_id == sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLI_NOT_FOUND",
                "message": f"SLI with ID '{sli_id}' not found",
                "details": {}
            }
        )

    # TODO: Implement actual PromQL validation against Prometheus
    # For now, return mock validation result
    return ValidationResult(
        valid=True,
        errors=[],
        sample_result={"metric": "example", "value": [1704672000, "0.99"]}
    )
