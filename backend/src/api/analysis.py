"""
Analysis API router - Asynchronous analysis job management endpoints
Implements analysis-api.yaml contract
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from enum import Enum

from ..models.service import Service
from .deps import get_db

# Create router
router = APIRouter(prefix="/api/v1", tags=["Analysis"])

# In-memory job storage (in production, use database or Redis)
_analysis_jobs: Dict[str, Dict[str, Any]] = {}


# Enums
class JobStatusEnum(str, Enum):
    """Analysis job status enum"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Pydantic schemas per contract
class AnalysisJobCreate(BaseModel):
    """Analysis job creation request schema"""
    service_id: UUID
    lookback_days: int = Field(default=7, ge=1, le=30)


class AnalysisJobResults(BaseModel):
    """Analysis job results schema"""
    journeys_discovered: int
    slis_generated: int
    telemetry_events_analyzed: int
    capsules_created: int


class AnalysisJobResponse(BaseModel):
    """Analysis job response schema"""
    job_id: str
    service_id: str
    status: str
    lookback_days: int
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    results: Optional[AnalysisJobResults] = None
    retry_count: int = 0


class AnalysisJobListResponse(BaseModel):
    """Analysis job list response schema"""
    jobs: list[AnalysisJobResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Route handlers
@router.post("/analyze", response_model=AnalysisJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_analysis_job(
    job_data: AnalysisJobCreate,
    db: Session = Depends(get_db)
) -> AnalysisJobResponse:
    """Create an asynchronous analysis job"""
    # Validate service exists
    service = db.query(Service).filter(Service.id == job_data.service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Service with ID '{job_data.service_id}' not found",
                "details": {}
            }
        )

    # Check concurrent jobs limit (NFR-007: max 10 concurrent)
    running_jobs = sum(1 for job in _analysis_jobs.values()
                      if job["status"] in ["pending", "running"])

    if running_jobs >= 10:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "CONCURRENT_LIMIT_EXCEEDED",
                "message": "Maximum 10 concurrent analysis jobs allowed (NFR-007)",
                "details": {"current_running": running_jobs, "limit": 10}
            }
        )

    # Create job
    from uuid import uuid4
    job_id = str(uuid4())

    job = {
        "job_id": job_id,
        "service_id": str(job_data.service_id),
        "status": JobStatusEnum.PENDING.value,
        "lookback_days": job_data.lookback_days,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "results": None,
        "retry_count": 0
    }

    _analysis_jobs[job_id] = job

    return AnalysisJobResponse(**job)


@router.get("/analyze/{job_id}", response_model=AnalysisJobResponse, status_code=status.HTTP_200_OK)
async def get_analysis_job(
    job_id: UUID
) -> AnalysisJobResponse:
    """Get analysis job status and results"""
    job_id_str = str(job_id)

    if job_id_str not in _analysis_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "JOB_NOT_FOUND",
                "message": f"Analysis job '{job_id}' not found",
                "details": {}
            }
        )

    job = _analysis_jobs[job_id_str]
    return AnalysisJobResponse(**job)


@router.delete("/analyze/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_analysis_job(
    job_id: UUID
) -> None:
    """Cancel a pending or running analysis job"""
    job_id_str = str(job_id)

    if job_id_str not in _analysis_jobs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "JOB_NOT_FOUND",
                "message": f"Analysis job '{job_id}' not found",
                "details": {}
            }
        )

    job = _analysis_jobs[job_id_str]

    # Check if job can be cancelled
    if job["status"] in [JobStatusEnum.COMPLETED.value, JobStatusEnum.FAILED.value]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "CANNOT_CANCEL",
                "message": f"Job already {job['status']} (cannot cancel)",
                "details": {"status": job["status"]}
            }
        )

    # Mark as cancelled
    job["status"] = JobStatusEnum.CANCELLED.value
    job["completed_at"] = datetime.now(timezone.utc).isoformat()


@router.get("/analyze/jobs", response_model=AnalysisJobListResponse, status_code=status.HTTP_200_OK)
async def list_analysis_jobs(
    service_id: Optional[UUID] = Query(None),
    job_status: Optional[str] = Query(None, alias="status", pattern="^(pending|running|completed|failed|cancelled)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0)
) -> AnalysisJobListResponse:
    """List analysis jobs with optional filtering"""
    jobs = list(_analysis_jobs.values())

    # Apply filters
    if service_id:
        jobs = [j for j in jobs if j["service_id"] == str(service_id)]

    if job_status:
        jobs = [j for j in jobs if j["status"] == job_status]

    # Get total before pagination
    total = len(jobs)

    # Apply pagination
    jobs = jobs[offset:offset + limit]

    return AnalysisJobListResponse(
        jobs=[AnalysisJobResponse(**j) for j in jobs],
        total=total,
        limit=limit,
        offset=offset
    )
