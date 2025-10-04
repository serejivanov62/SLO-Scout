"""
Journey persistence service per T089
Saves UserJourney to DB, links sample trace IDs, updates last_seen_at
"""
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session

from ..models.user_journey import UserJourney
from ..storage.timescale_manager import get_timescale_manager


class JourneyService:
    """
    Service for persisting and managing user journeys

    Per data-model.md UserJourney entity
    """

    def __init__(self):
        self.db_manager = get_timescale_manager()

    def save_journey(
        self,
        service_id: UUID,
        name: str,
        entry_point: str,
        exit_point: str,
        step_sequence: List[dict],
        traffic_volume_per_day: int,
        confidence_score: float,
        sample_trace_ids: List[str]
    ) -> UserJourney:
        """
        Save user journey to database

        Args:
            service_id: Service UUID
            name: Journey name (e.g., "checkout-flow")
            entry_point: Starting endpoint/span
            exit_point: Terminal endpoint/span
            step_sequence: Ordered list of steps
            traffic_volume_per_day: Daily request count
            confidence_score: Discovery confidence (0-100)
            sample_trace_ids: Representative trace IDs

        Returns:
            Saved UserJourney instance
        """
        with self.db_manager.get_session() as session:
            # Check if journey exists
            existing = session.query(UserJourney).filter(
                UserJourney.service_id == service_id,
                UserJourney.name == name
            ).first()

            if existing:
                # Update existing journey
                existing.traffic_volume_per_day = traffic_volume_per_day
                existing.confidence_score = confidence_score
                existing.sample_trace_ids = sample_trace_ids
                existing.last_seen_at = datetime.utcnow()
                session.commit()
                return existing
            else:
                # Create new journey
                journey = UserJourney(
                    service_id=service_id,
                    name=name,
                    entry_point=entry_point,
                    exit_point=exit_point,
                    step_sequence=step_sequence,
                    traffic_volume_per_day=traffic_volume_per_day,
                    confidence_score=confidence_score,
                    sample_trace_ids=sample_trace_ids
                )
                session.add(journey)
                session.commit()
                return journey

    def get_journey(self, journey_id: UUID) -> Optional[UserJourney]:
        """Get journey by ID"""
        with self.db_manager.get_session() as session:
            return session.query(UserJourney).filter(
                UserJourney.journey_id == journey_id
            ).first()

    def get_journeys_for_service(
        self,
        service_id: UUID,
        min_confidence: float = 50.0
    ) -> List[UserJourney]:
        """
        Get all journeys for a service

        Args:
            service_id: Service UUID
            min_confidence: Minimum confidence threshold

        Returns:
            List of journeys sorted by confidence (descending)
        """
        with self.db_manager.get_session() as session:
            return session.query(UserJourney).filter(
                UserJourney.service_id == service_id,
                UserJourney.confidence_score >= min_confidence
            ).order_by(
                UserJourney.confidence_score.desc()
            ).all()

    def update_last_seen(
        self,
        journey_id: UUID,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Update last_seen_at timestamp

        Args:
            journey_id: Journey UUID
            timestamp: Timestamp (defaults to now)
        """
        with self.db_manager.get_session() as session:
            journey = session.query(UserJourney).filter(
                UserJourney.journey_id == journey_id
            ).first()

            if journey:
                journey.last_seen_at = timestamp or datetime.utcnow()
                session.commit()

    def deprecate_stale_journeys(
        self,
        service_id: UUID,
        threshold_days: int = 7
    ) -> int:
        """
        Mark journeys as deprecated if not seen recently

        Args:
            service_id: Service UUID
            threshold_days: Days since last seen

        Returns:
            Number of deprecated journeys
        """
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(days=threshold_days)

        with self.db_manager.get_session() as session:
            stale_journeys = session.query(UserJourney).filter(
                UserJourney.service_id == service_id,
                UserJourney.last_seen_at < cutoff_time
            ).all()

            # Mark as deprecated (reduce confidence)
            for journey in stale_journeys:
                journey.confidence_score = journey.confidence_score * 0.5

            session.commit()
            return len(stale_journeys)
