"""
Blast radius calculator for artifact deployment impact analysis.

Per research.md FR-034: Multi-dimensional blast radius calculation
- Affected services percentage
- Endpoint count
- Traffic percentage
- Cost impact estimation
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Set
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..models.artifact import Artifact, ArtifactTypeEnum
from ..models.slo import SLO
from ..models.sli import SLI
from ..models.user_journey import UserJourney
from ..models.service import Service

logger = logging.getLogger(__name__)


@dataclass
class BlastRadiusMetrics:
    """
    Multi-dimensional blast radius calculation result.

    Per research.md FR-034 decision:
    - Percentage alone fails for small deployments
    - Absolute count fails for large deployments
    - Cost impact prevents expensive actions
    """
    affected_services_count: int
    affected_services_percentage: float
    total_services_count: int
    affected_endpoints_count: int
    affected_traffic_percentage: float
    estimated_cost_impact_usd: Decimal
    affected_service_ids: Set[UUID]

    def __post_init__(self) -> None:
        """Validate metrics are within expected ranges."""
        if self.affected_services_percentage < 0 or self.affected_services_percentage > 100:
            raise ValueError(f"Invalid services percentage: {self.affected_services_percentage}")
        if self.affected_traffic_percentage < 0 or self.affected_traffic_percentage > 100:
            raise ValueError(f"Invalid traffic percentage: {self.affected_traffic_percentage}")
        if self.estimated_cost_impact_usd < 0:
            raise ValueError(f"Invalid cost impact: {self.estimated_cost_impact_usd}")


class BlastRadiusCalculator:
    """
    Calculate multi-dimensional blast radius for artifact deployment.

    Implements FR-034 decision logic:
    - Calculate affected services % (percentage)
    - Calculate endpoint count (absolute)
    - Calculate traffic % (weighted impact)
    - Estimate cost impact (monetary)
    """

    def __init__(self, db_session: Session):
        """
        Initialize blast radius calculator.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self._cost_model = self._initialize_cost_model()

    def _initialize_cost_model(self) -> Dict[str, Decimal]:
        """
        Initialize cost model for artifact types.

        Returns:
            Dictionary mapping artifact types to base cost multipliers
        """
        return {
            ArtifactTypeEnum.PROMETHEUS_RECORDING.value: Decimal("5.0"),  # $5 per service
            ArtifactTypeEnum.PROMETHEUS_ALERT.value: Decimal("10.0"),     # $10 per service
            ArtifactTypeEnum.GRAFANA_DASHBOARD.value: Decimal("2.0"),     # $2 per service
            ArtifactTypeEnum.RUNBOOK.value: Decimal("1.0"),               # $1 per service (minimal)
        }

    async def calculate_from_artifact(
        self,
        artifact_id: UUID,
        organization_id: Optional[UUID] = None
    ) -> BlastRadiusMetrics:
        """
        Calculate blast radius for a specific artifact deployment.

        Args:
            artifact_id: UUID of artifact to analyze
            organization_id: Optional organization scope filter

        Returns:
            BlastRadiusMetrics with calculated impact

        Raises:
            ValueError: If artifact not found
        """
        # Fetch artifact and related entities
        artifact = self.db.query(Artifact).filter(
            Artifact.artifact_id == artifact_id
        ).first()

        if not artifact:
            raise ValueError(f"Artifact {artifact_id} not found")

        # Get SLO and traverse to service
        slo = self.db.query(SLO).filter(SLO.slo_id == artifact.slo_id).first()
        if not slo:
            raise ValueError(f"SLO {artifact.slo_id} not found for artifact {artifact_id}")

        sli = self.db.query(SLI).filter(SLI.sli_id == slo.sli_id).first()
        if not sli:
            raise ValueError(f"SLI {slo.sli_id} not found for SLO {slo.slo_id}")

        journey = self.db.query(UserJourney).filter(
            UserJourney.journey_id == sli.journey_id
        ).first()
        if not journey:
            raise ValueError(f"Journey {sli.journey_id} not found for SLI {sli.sli_id}")

        service = self.db.query(Service).filter(
            Service.service_id == journey.service_id
        ).first()
        if not service:
            raise ValueError(f"Service {journey.service_id} not found for journey {journey.journey_id}")

        # Calculate affected services (this artifact affects its service)
        affected_service_ids = {service.service_id}

        # Calculate total services in scope
        total_services_query = select(func.count(Service.service_id)).select_from(Service)
        if organization_id:
            total_services_query = total_services_query.where(
                Service.organization_id == organization_id
            )

        total_services_count = self.db.execute(total_services_query).scalar() or 1

        # Calculate affected services percentage
        affected_services_count = len(affected_service_ids)
        affected_services_pct = (affected_services_count / total_services_count) * 100

        # Calculate affected endpoints (from journey step sequence)
        affected_endpoints_count = self._calculate_affected_endpoints(journey)

        # Calculate traffic percentage (based on journey traffic volume)
        affected_traffic_pct = await self._calculate_traffic_percentage(
            journey,
            organization_id
        )

        # Calculate cost impact
        cost_impact = self._calculate_cost_impact(
            artifact.artifact_type,
            affected_services_count
        )

        logger.info(
            f"Calculated blast radius for artifact {artifact_id}: "
            f"{affected_services_count} services ({affected_services_pct:.2f}%), "
            f"{affected_endpoints_count} endpoints, "
            f"{affected_traffic_pct:.2f}% traffic, "
            f"${cost_impact} cost"
        )

        return BlastRadiusMetrics(
            affected_services_count=affected_services_count,
            affected_services_percentage=round(affected_services_pct, 2),
            total_services_count=total_services_count,
            affected_endpoints_count=affected_endpoints_count,
            affected_traffic_percentage=round(affected_traffic_pct, 2),
            estimated_cost_impact_usd=cost_impact,
            affected_service_ids=affected_service_ids
        )

    def _calculate_affected_endpoints(self, journey: UserJourney) -> int:
        """
        Calculate number of affected endpoints from journey.

        Args:
            journey: UserJourney with step_sequence

        Returns:
            Count of unique endpoints in journey
        """
        step_sequence = journey.step_sequence or []

        # Count unique span names as endpoints
        unique_endpoints = set()
        for step in step_sequence:
            if isinstance(step, dict) and 'span_name' in step:
                unique_endpoints.add(step['span_name'])

        return len(unique_endpoints) if unique_endpoints else 1

    async def _calculate_traffic_percentage(
        self,
        journey: UserJourney,
        organization_id: Optional[UUID] = None
    ) -> float:
        """
        Calculate percentage of total traffic affected by this journey.

        Args:
            journey: UserJourney with traffic_volume_per_day
            organization_id: Optional organization scope

        Returns:
            Percentage of total traffic (0-100)
        """
        journey_traffic = journey.traffic_volume_per_day or 0

        # Get total traffic across all journeys in scope
        total_traffic_query = select(func.sum(UserJourney.traffic_volume_per_day)).select_from(
            UserJourney
        ).join(Service)

        if organization_id:
            total_traffic_query = total_traffic_query.where(
                Service.organization_id == organization_id
            )

        total_traffic = self.db.execute(total_traffic_query).scalar() or 1

        traffic_pct = (journey_traffic / total_traffic) * 100 if total_traffic > 0 else 0

        return traffic_pct

    def _calculate_cost_impact(
        self,
        artifact_type: ArtifactTypeEnum,
        affected_services_count: int
    ) -> Decimal:
        """
        Estimate cost impact of deploying artifact.

        Per research.md FR-034: Cost model prevents expensive actions

        Args:
            artifact_type: Type of artifact being deployed
            affected_services_count: Number of services affected

        Returns:
            Estimated cost in USD
        """
        base_cost = self._cost_model.get(artifact_type.value, Decimal("1.0"))

        # Linear cost scaling with service count
        # Could be enhanced with non-linear models (e.g., volume discounts)
        total_cost = base_cost * Decimal(str(affected_services_count))

        return total_cost.quantize(Decimal("0.01"))  # Round to cents

    async def calculate_batch_impact(
        self,
        artifact_ids: List[UUID],
        organization_id: Optional[UUID] = None
    ) -> BlastRadiusMetrics:
        """
        Calculate combined blast radius for multiple artifacts.

        Args:
            artifact_ids: List of artifact UUIDs
            organization_id: Optional organization scope

        Returns:
            Aggregated BlastRadiusMetrics
        """
        if not artifact_ids:
            raise ValueError("No artifact IDs provided")

        all_affected_services: Set[UUID] = set()
        total_endpoints = 0
        total_cost = Decimal("0.0")
        max_traffic_pct = 0.0

        for artifact_id in artifact_ids:
            metrics = await self.calculate_from_artifact(artifact_id, organization_id)
            all_affected_services.update(metrics.affected_service_ids)
            total_endpoints += metrics.affected_endpoints_count
            total_cost += metrics.estimated_cost_impact_usd
            max_traffic_pct = max(max_traffic_pct, metrics.affected_traffic_percentage)

        # Recalculate percentages based on combined set
        total_services_query = select(func.count(Service.service_id)).select_from(Service)
        if organization_id:
            total_services_query = total_services_query.where(
                Service.organization_id == organization_id
            )
        total_services_count = self.db.execute(total_services_query).scalar() or 1

        affected_count = len(all_affected_services)
        affected_pct = (affected_count / total_services_count) * 100

        logger.info(
            f"Calculated batch blast radius for {len(artifact_ids)} artifacts: "
            f"{affected_count} services, {total_endpoints} endpoints, "
            f"${total_cost} total cost"
        )

        return BlastRadiusMetrics(
            affected_services_count=affected_count,
            affected_services_percentage=round(affected_pct, 2),
            total_services_count=total_services_count,
            affected_endpoints_count=total_endpoints,
            affected_traffic_percentage=round(max_traffic_pct, 2),
            estimated_cost_impact_usd=total_cost.quantize(Decimal("0.01")),
            affected_service_ids=all_affected_services
        )
