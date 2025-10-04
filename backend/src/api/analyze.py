"""
Analysis API endpoints (T124-T125)
Per api-analyze.yaml contract
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime
from typing import Dict, Any
import logging

from .schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalysisStatusResponse,
    ErrorResponse,
)
from .deps import get_db
from ..models.service import Service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Analysis"])

# In-memory job storage (in production, use Redis or database)
_analysis_jobs: Dict[str, Dict[str, Any]] = {}


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    }
)
async def analyze_service(
    request: AnalyzeRequest,
    db: Session = Depends(get_db)
) -> AnalyzeResponse:
    """
    Trigger SLI/SLO analysis for a service (T124)

    Per api-analyze.yaml:
    - Accepts service_name, environment, analysis_window_days, force_refresh
    - Returns 202 with job_id and status
    - Returns 400 for invalid request
    - Returns 404 if service not found
    """
    # Validate service exists
    service = db.query(Service).filter(
        Service.name == request.service_name,
        Service.environment == request.environment.value
    ).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SERVICE_NOT_FOUND",
                "message": f"Service '{request.service_name}' in environment '{request.environment.value}' not found",
                "details": {
                    "service_name": request.service_name,
                    "environment": request.environment.value
                }
            }
        )

    # Create analysis job
    job_id = uuid4()
    job = {
        "job_id": str(job_id),
        "service_id": str(service.service_id),
        "service_name": request.service_name,
        "environment": request.environment.value,
        "analysis_window_days": request.analysis_window_days,
        "force_refresh": request.force_refresh,
        "status": "pending",
        "progress_percent": 0,
        "started_at": datetime.utcnow(),
        "completed_at": None,
        "result_url": None,
        "error_message": None,
    }

    # Store job (in production, queue to async worker)
    _analysis_jobs[str(job_id)] = job

    logger.info(
        f"Created analysis job {job_id} for service {request.service_name} "
        f"in {request.environment.value}"
    )

    # Estimate duration based on window (simplified)
    estimated_duration = min(request.analysis_window_days * 4, 300)  # Max 5 minutes

    return AnalyzeResponse(
        job_id=job_id,
        status="pending",
        estimated_duration_seconds=estimated_duration
    )


@router.get(
    "/analyze/{job_id}",
    response_model=AnalysisStatusResponse,
    responses={
        404: {"model": ErrorResponse},
    }
)
async def get_analysis_status(job_id: str) -> AnalysisStatusResponse:
    """
    Get analysis job status (T125)

    Per api-analyze.yaml:
    - Returns job status with progress_percent
    - Returns result_url when completed
    - Returns 404 if job not found
    """
    job = _analysis_jobs.get(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "JOB_NOT_FOUND",
                "message": f"Analysis job '{job_id}' not found",
                "details": {"job_id": job_id}
            }
        )

    return AnalysisStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        progress_percent=job["progress_percent"],
        started_at=job["started_at"],
        completed_at=job.get("completed_at"),
        result_url=job.get("result_url"),
        error_message=job.get("error_message"),
    )
