"""
Journeys API endpoints (T126)
Per api-analyze.yaml contract
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from .schemas import JourneysListResponse, UserJourneyResponse, Environment
from .deps import get_db
from ..models.user_journey import UserJourney
from ..models.service import Service

router = APIRouter(prefix="/api/v1", tags=["Journeys"])


@router.get(
    "/journeys",
    response_model=JourneysListResponse
)
async def list_journeys(
    service_name: str = Query(..., description="Service name to filter journeys"),
    environment: Environment = Query(..., description="Environment to filter journeys"),
    min_confidence: float = Query(default=50, ge=0, le=100, description="Minimum confidence threshold"),
    db: Session = Depends(get_db)
) -> JourneysListResponse:
    """
    List discovered user journeys for a service (T126)

    Per api-analyze.yaml:
    - Filters by service_name and environment (required)
    - Filters by min_confidence (optional, default 50)
    - Returns journeys array with total_count
    """
    # Get service ID
    service = db.query(Service).filter(
        Service.name == service_name,
        Service.environment == environment.value
    ).first()

    if not service:
        # Return empty list if service not found (per contract, not 404)
        return JourneysListResponse(journeys=[], total_count=0)

    # Query journeys
    query = db.query(UserJourney).filter(
        UserJourney.service_id == service.service_id,
        UserJourney.confidence_score >= min_confidence
    ).order_by(UserJourney.confidence_score.desc())

    journeys = query.all()

    # Map to response schema
    journey_responses = [
        UserJourneyResponse(
            journey_id=j.journey_id,
            name=j.name,
            entry_point=j.entry_point,
            exit_point=j.exit_point,
            traffic_volume_per_day=j.traffic_volume_per_day,
            confidence_score=float(j.confidence_score),
            discovered_at=j.discovered_at
        )
        for j in journeys
    ]

    return JourneysListResponse(
        journeys=journey_responses,
        total_count=len(journey_responses)
    )
