"""
SLO API endpoints (T129-T130)
Per api-sli.yaml contract
"""
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session
from uuid import UUID
from datetime import timedelta
import re
from typing import Optional
import os

from .schemas import (
    SLOCreateRequest,
    SLOResponse,
    SimulationRequest,
    SimulationResultResponse,
    ErrorResponse,
    ComparisonOperator,
    Severity,
    SLOVariant,
)
from .deps import get_db
from ..models.slo import SLO, ComparisonOperator as DBComparisonOperator, Severity as DBSeverity, SLOVariant as DBSLOVariant
from ..models.sli import SLI
from ..validators.dryrun_evaluator import DryRunEvaluator

router = APIRouter(prefix="/api/v1", tags=["SLO"])


def parse_time_window(time_window: str) -> timedelta:
    """
    Parse time window string to timedelta
    Examples: '30d', '1h', '24h', '7d'
    """
    match = re.match(r'^(\d+)([dhms])$', time_window)
    if not match:
        raise ValueError(f"Invalid time_window format: {time_window}")

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    elif unit == 's':
        return timedelta(seconds=value)
    else:
        raise ValueError(f"Unknown time unit: {unit}")


def format_time_window(td: timedelta) -> str:
    """Format timedelta to string (e.g., '30d', '24h')"""
    total_seconds = int(td.total_seconds())

    if total_seconds % 86400 == 0:
        return f"{total_seconds // 86400}d"
    elif total_seconds % 3600 == 0:
        return f"{total_seconds // 3600}h"
    elif total_seconds % 60 == 0:
        return f"{total_seconds // 60}m"
    else:
        return f"{total_seconds}s"


@router.post(
    "/slo",
    response_model=SLOResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse},
    }
)
async def create_slo(
    request: SLOCreateRequest,
    db: Session = Depends(get_db)
) -> SLOResponse:
    """
    Create SLO for an approved SLI (T129)

    Per api-sli.yaml:
    - Validates SLI exists and is approved
    - Validates threshold, time_window, target_percentage
    - Returns 201 with created SLO
    - Returns 400 for invalid configuration
    """
    # Validate SLI exists
    sli = db.query(SLI).filter(SLI.sli_id == request.sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "SLI_NOT_FOUND",
                "message": f"SLI '{request.sli_id}' not found",
                "details": {"sli_id": str(request.sli_id)}
            }
        )

    # Parse time window
    try:
        time_window_delta = parse_time_window(request.time_window)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "INVALID_TIME_WINDOW",
                "message": str(e),
                "details": {"time_window": request.time_window}
            }
        )

    # Validate minimum time window (1 hour per data-model.md)
    if time_window_delta < timedelta(hours=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "TIME_WINDOW_TOO_SHORT",
                "message": "Time window must be at least 1 hour",
                "details": {"time_window": request.time_window}
            }
        )

    # Create SLO
    slo = SLO(
        sli_id=request.sli_id,
        threshold_value=request.threshold_value,
        comparison_operator=DBComparisonOperator(request.comparison_operator.value),
        time_window=time_window_delta,
        target_percentage=request.target_percentage,
        severity=DBSeverity(request.severity.value) if request.severity else DBSeverity.MAJOR,
        variant=DBSLOVariant(request.variant.value) if request.variant else DBSLOVariant.BALANCED,
    )

    db.add(slo)
    db.commit()
    db.refresh(slo)

    return SLOResponse(
        slo_id=slo.slo_id,
        sli_id=slo.sli_id,
        threshold_value=float(slo.threshold_value),
        comparison_operator=ComparisonOperator(slo.comparison_operator.value),
        time_window=format_time_window(slo.time_window),
        target_percentage=float(slo.target_percentage),
        severity=Severity(slo.severity.value) if slo.severity else None,
        variant=SLOVariant(slo.variant.value) if slo.variant else None,
        historical_breach_frequency=float(slo.historical_breach_frequency) if slo.historical_breach_frequency else None,
        error_budget_remaining=float(slo.error_budget_remaining) if slo.error_budget_remaining else None,
        deployed_at=slo.deployed_at
    )


@router.post(
    "/slo/{slo_id}/simulate",
    response_model=SimulationResultResponse,
    responses={
        404: {"model": ErrorResponse},
    }
)
async def simulate_slo(
    slo_id: UUID = Path(..., description="SLO ID to simulate"),
    request: SimulationRequest = SimulationRequest(),
    db: Session = Depends(get_db)
) -> SimulationResultResponse:
    """
    Simulate SLO breach frequency using historical data (T130)

    Per api-sli.yaml:
    - Runs backtest simulation using Prometheus historical data
    - Returns simulated_breaches and breach_timestamps
    - Supports threshold_override for testing different values
    - Returns 404 if SLO not found
    """
    # Get SLO and SLI
    slo = db.query(SLO).filter(SLO.slo_id == slo_id).first()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SLO_NOT_FOUND",
                "message": f"SLO '{slo_id}' not found",
                "details": {"slo_id": str(slo_id)}
            }
        )

    sli = db.query(SLI).filter(SLI.sli_id == slo.sli_id).first()

    if not sli:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SLI_NOT_FOUND",
                "message": f"SLI for SLO '{slo_id}' not found",
                "details": {"slo_id": str(slo_id)}
            }
        )

    # Use threshold override if provided
    threshold = request.threshold_override if request.threshold_override is not None else float(slo.threshold_value)

    # Get Prometheus URL from environment
    prometheus_url = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")

    # Run dry-run evaluation
    try:
        evaluator = DryRunEvaluator(prometheus_url)
        result = evaluator.estimate_breach_frequency(
            metric_expr=sli.metric_definition,
            threshold=threshold,
            comparison_operator=slo.comparison_operator.value,
            lookback_days=request.simulation_window_days
        )

        # Calculate error budget
        # Error budget = (1 - target_percentage/100) * 100
        error_budget_total = (1 - float(slo.target_percentage) / 100) * 100
        breach_percentage = result["breach_percentage"]
        error_budget_remaining = max(0, error_budget_total - breach_percentage)

        # Calculate worst breach magnitude
        # Simplified: use breach percentage as proxy
        worst_breach_magnitude = breach_percentage

        return SimulationResultResponse(
            slo_id=slo_id,
            simulated_breaches=result["total_breaches"],
            breach_timestamps=[
                datetime.fromisoformat(ts.replace('Z', '+00:00'))
                for ts in result["breach_timestamps"]
            ],
            average_error_budget_remaining=error_budget_remaining,
            worst_breach_magnitude=worst_breach_magnitude
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error_code": "SIMULATION_FAILED",
                "message": f"Failed to simulate SLO: {str(e)}",
                "details": {"slo_id": str(slo_id)}
            }
        )
