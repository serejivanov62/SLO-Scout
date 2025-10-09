"""
SLO API router - Service Level Objective management endpoints
Implements slo-api.yaml contract
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..models.slo import SLO, ThresholdVariantEnum
from ..models.sli import SLI
from ..models.artifact import Artifact, ArtifactStatusEnum
from .deps import get_db

# Create router
router = APIRouter(prefix="/api/v1", tags=["SLO"])


# Pydantic schemas per contract
class SLOCreate(BaseModel):
    """SLO creation request schema"""
    sli_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    target_percentage: float = Field(..., ge=0.0, le=100.0)
    time_window: str = Field(..., pattern=r"^[0-9]+[dhw]$")
    threshold_variant: str = Field(default="balanced", pattern="^(conservative|balanced|aggressive)$")


class SLOUpdate(BaseModel):
    """SLO update request schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    target_percentage: Optional[float] = Field(None, ge=0.0, le=100.0)
    time_window: Optional[str] = Field(None, pattern=r"^[0-9]+[dhw]$")
    threshold_variant: Optional[str] = Field(None, pattern="^(conservative|balanced|aggressive)$")


class SLOResponse(BaseModel):
    """SLO response schema"""
    slo_id: str
    sli_id: str
    name: str
    target_percentage: float
    time_window: str
    threshold_variant: str
    created_at: str

    @classmethod
    def from_orm(cls, slo: SLO):
        """Convert SQLAlchemy model to Pydantic schema"""
        return cls(
            slo_id=str(slo.slo_id),
            sli_id=str(slo.sli_id),
            name=slo.name,
            target_percentage=float(slo.target_percentage),
            time_window=slo.time_window,
            threshold_variant=slo.threshold_variant.value,
            created_at=slo.created_at.isoformat()
        )


class SLOListResponse(BaseModel):
    """SLO list response schema"""
    slos: list[SLOResponse]
    total: int
    limit: int
    offset: int


class ErrorBudgetResponse(BaseModel):
    """Error budget calculation response schema"""
    slo_id: str
    target_percentage: float
    current_percentage: float
    error_budget_remaining: float
    time_window: str
    calculation_timestamp: str


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Route handlers
@router.get("/slo", response_model=SLOListResponse, status_code=status.HTTP_200_OK)
async def list_slos(
    sli_id: Optional[UUID] = Query(None),
    threshold_variant: Optional[str] = Query(None, pattern="^(conservative|balanced|aggressive)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> SLOListResponse:
    """List SLOs with optional filtering"""
    query = db.query(SLO)

    # Apply filters
    if sli_id:
        query = query.filter(SLO.sli_id == sli_id)

    if threshold_variant:
        query = query.filter(SLO.threshold_variant == ThresholdVariantEnum(threshold_variant))

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    slos = query.offset(offset).limit(limit).all()

    return SLOListResponse(
        slos=[SLOResponse.from_orm(s) for s in slos],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("/slo", response_model=SLOResponse, status_code=status.HTTP_201_CREATED)
async def create_slo(
    slo_data: SLOCreate,
    db: Session = Depends(get_db)
) -> SLOResponse:
    """Create a new SLO based on an approved SLI"""
    # Validate SLI exists and is approved
    sli = db.query(SLI).filter(SLI.sli_id == slo_data.sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLI_NOT_FOUND",
                "message": f"SLI with ID '{slo_data.sli_id}' not found",
                "details": {}
            }
        )

    if not sli.approved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "SLI_NOT_APPROVED",
                "message": "Cannot create SLO for unapproved SLI",
                "details": {"sli_id": str(slo_data.sli_id)}
            }
        )

    # Create new SLO
    new_slo = SLO(
        sli_id=slo_data.sli_id,
        name=slo_data.name,
        target_percentage=Decimal(str(slo_data.target_percentage)),
        time_window=slo_data.time_window,
        threshold_variant=ThresholdVariantEnum(slo_data.threshold_variant)
    )

    db.add(new_slo)
    db.commit()
    db.refresh(new_slo)

    return SLOResponse.from_orm(new_slo)


@router.get("/slo/{slo_id}", response_model=SLOResponse, status_code=status.HTTP_200_OK)
async def get_slo(
    slo_id: UUID,
    db: Session = Depends(get_db)
) -> SLOResponse:
    """Get SLO by ID"""
    slo = db.query(SLO).filter(SLO.slo_id == slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLO_NOT_FOUND",
                "message": f"SLO with ID '{slo_id}' not found",
                "details": {}
            }
        )

    return SLOResponse.from_orm(slo)


@router.patch("/slo/{slo_id}", response_model=SLOResponse, status_code=status.HTTP_200_OK)
async def update_slo(
    slo_id: UUID,
    update_data: SLOUpdate,
    db: Session = Depends(get_db)
) -> SLOResponse:
    """Update SLO configuration"""
    slo = db.query(SLO).filter(SLO.slo_id == slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLO_NOT_FOUND",
                "message": f"SLO with ID '{slo_id}' not found",
                "details": {}
            }
        )

    # Apply updates
    if update_data.name is not None:
        slo.name = update_data.name

    if update_data.target_percentage is not None:
        slo.target_percentage = Decimal(str(update_data.target_percentage))

    if update_data.time_window is not None:
        slo.time_window = update_data.time_window

    if update_data.threshold_variant is not None:
        slo.threshold_variant = ThresholdVariantEnum(update_data.threshold_variant)

    db.commit()
    db.refresh(slo)

    return SLOResponse.from_orm(slo)


@router.delete("/slo/{slo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slo(
    slo_id: UUID,
    db: Session = Depends(get_db)
) -> None:
    """Delete an SLO"""
    slo = db.query(SLO).filter(SLO.slo_id == slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLO_NOT_FOUND",
                "message": f"SLO with ID '{slo_id}' not found",
                "details": {}
            }
        )

    # Check for deployed artifacts
    deployed_artifacts = db.query(Artifact).filter(
        Artifact.slo_id == slo_id,
        Artifact.status == ArtifactStatusEnum.DEPLOYED
    ).count()

    if deployed_artifacts > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "HAS_DEPLOYED_ARTIFACTS",
                "message": "Cannot delete SLO with deployed artifacts",
                "details": {"deployed_artifacts_count": deployed_artifacts}
            }
        )

    # Delete SLO (cascades to artifacts)
    db.delete(slo)
    db.commit()


@router.get("/slo/{slo_id}/error-budget", response_model=ErrorBudgetResponse, status_code=status.HTTP_200_OK)
async def get_error_budget(
    slo_id: UUID,
    db: Session = Depends(get_db)
) -> ErrorBudgetResponse:
    """Calculate error budget status for SLO"""
    slo = db.query(SLO).filter(SLO.slo_id == slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SLO_NOT_FOUND",
                "message": f"SLO with ID '{slo_id}' not found",
                "details": {}
            }
        )

    # TODO: Implement actual error budget calculation from Prometheus
    # For now, return mock data
    target = float(slo.target_percentage)
    current = 99.95  # Mock current percentage
    error_budget_remaining = ((current - target) / (100 - target)) * 100 if target < 100 else 100.0

    return ErrorBudgetResponse(
        slo_id=str(slo.slo_id),
        target_percentage=target,
        current_percentage=current,
        error_budget_remaining=max(0.0, min(100.0, error_budget_remaining)),
        time_window=slo.time_window,
        calculation_timestamp=datetime.now(timezone.utc).isoformat()
    )
