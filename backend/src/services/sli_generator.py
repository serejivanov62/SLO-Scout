"""
SLI Candidate Generator Service

Generates Service Level Indicators for each user journey including:
- Latency percentiles (p50, p95, p99)
- Error rate
- Availability

Per spec.md FR-002 and tasks.md T090
"""
from typing import List, Dict, Any, Optional
from datetime import timedelta
from decimal import Decimal
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from ..models.user_journey import UserJourney
from ..models.sli import SLI, MetricType


logger = logging.getLogger(__name__)


class SLICandidate:
    """
    Data class representing an SLI candidate before persistence
    """
    def __init__(
        self,
        name: str,
        metric_type: MetricType,
        metric_definition: str,
        measurement_window: timedelta,
        data_sources: Dict[str, Any],
        unit: str,
        description: str = "",
    ):
        self.name = name
        self.metric_type = metric_type
        self.metric_definition = metric_definition
        self.measurement_window = measurement_window
        self.data_sources = data_sources
        self.unit = unit
        self.description = description


class SLIGenerator:
    """
    Generate SLI candidates for user journeys

    Per spec.md FR-002:
    - Top 5 SLIs per journey
    - Latency percentiles (p50/p95/p99)
    - Error rate
    - Availability

    Per data-model.md:
    - metric_definition must be valid PromQL
    - confidence_score based on data coverage
    - evidence_pointers link to capsules
    """

    def __init__(self, db: Session):
        self.db = db
        self.default_measurement_window = timedelta(minutes=5)

    def generate_for_journey(
        self,
        journey: UserJourney,
        service_name: Optional[str] = None,
    ) -> List[SLICandidate]:
        """
        Generate SLI candidates for a specific user journey

        Args:
            journey: UserJourney entity to generate SLIs for
            service_name: Optional override for service name in PromQL

        Returns:
            List of SLICandidate objects (not yet persisted)

        Raises:
            ValueError: If journey has invalid configuration
        """
        if not journey.entry_point or not journey.exit_point:
            raise ValueError(f"Journey {journey.journey_id} missing entry/exit points")

        # Determine service name for PromQL queries
        if service_name is None:
            service_name = self._extract_service_name(journey)

        logger.info(
            f"Generating SLI candidates for journey {journey.name} "
            f"(service={service_name})"
        )

        candidates: List[SLICandidate] = []

        # Generate latency SLIs (p50, p95, p99)
        candidates.extend(self._generate_latency_slis(journey, service_name))

        # Generate error rate SLI
        candidates.append(self._generate_error_rate_sli(journey, service_name))

        # Generate availability SLI
        candidates.append(self._generate_availability_sli(journey, service_name))

        logger.info(f"Generated {len(candidates)} SLI candidates for journey {journey.name}")
        return candidates

    def _extract_service_name(self, journey: UserJourney) -> str:
        """
        Extract service name from journey relationship or entry point

        Args:
            journey: UserJourney entity

        Returns:
            Service name suitable for PromQL job label
        """
        # Prefer relationship if available
        if hasattr(journey, 'service') and journey.service:
            return journey.service.name

        # Fallback: extract from entry point (e.g., "/api/checkout" -> "api")
        entry_point = journey.entry_point.strip('/')
        parts = entry_point.split('/')
        return parts[0] if parts else "unknown"

    def _generate_latency_slis(
        self,
        journey: UserJourney,
        service_name: str,
    ) -> List[SLICandidate]:
        """
        Generate latency percentile SLIs (p50, p95, p99)

        Per spec.md FR-002: Latency percentiles are core SLI recommendations

        Args:
            journey: UserJourney entity
            service_name: Service name for PromQL queries

        Returns:
            List of 3 latency SLI candidates
        """
        percentiles = [
            (50, "p50", "median"),
            (95, "p95", "95th percentile"),
            (99, "p99", "99th percentile"),
        ]

        candidates = []

        for quantile_value, percentile_label, description in percentiles:
            # PromQL histogram_quantile query
            # Assumes http_request_duration_seconds histogram exists
            promql = self._build_latency_promql(
                service_name=service_name,
                endpoint=journey.entry_point,
                quantile=quantile_value / 100.0,
            )

            candidate = SLICandidate(
                name=f"{journey.name}-latency-{percentile_label}",
                metric_type=MetricType.LATENCY,
                metric_definition=promql,
                measurement_window=self.default_measurement_window,
                data_sources={
                    "prometheus": ["http_request_duration_seconds"],
                    "traces": [span["span_name"] for span in journey.step_sequence]
                        if journey.step_sequence else [],
                    "logs": [],
                },
                unit="ms",
                description=f"{description} latency for {journey.name}",
            )
            candidates.append(candidate)

        return candidates

    def _build_latency_promql(
        self,
        service_name: str,
        endpoint: str,
        quantile: float,
    ) -> str:
        """
        Build PromQL query for latency histogram quantile

        Args:
            service_name: Service job label
            endpoint: HTTP endpoint path
            quantile: Quantile value (0.5, 0.95, 0.99)

        Returns:
            Valid PromQL histogram_quantile query
        """
        # Standard Prometheus histogram quantile query
        # Converts seconds to milliseconds (* 1000)
        return (
            f'histogram_quantile({quantile}, '
            f'sum by (le) ('
            f'rate(http_request_duration_seconds_bucket{{'
            f'job="{service_name}", '
            f'endpoint="{endpoint}"'
            f'}}[5m])'
            f')) * 1000'
        )

    def _generate_error_rate_sli(
        self,
        journey: UserJourney,
        service_name: str,
    ) -> SLICandidate:
        """
        Generate error rate SLI

        Calculates percentage of requests with 5xx status codes

        Args:
            journey: UserJourney entity
            service_name: Service name for PromQL queries

        Returns:
            Error rate SLI candidate
        """
        # PromQL query: percentage of 5xx responses
        # Assumes http_requests_total counter with status_code label
        promql = self._build_error_rate_promql(
            service_name=service_name,
            endpoint=journey.entry_point,
        )

        return SLICandidate(
            name=f"{journey.name}-error-rate",
            metric_type=MetricType.ERROR_RATE,
            metric_definition=promql,
            measurement_window=self.default_measurement_window,
            data_sources={
                "prometheus": ["http_requests_total"],
                "traces": [span["span_name"] for span in journey.step_sequence]
                    if journey.step_sequence else [],
                "logs": ["error", "fatal"],  # Log severity levels
            },
            unit="%",
            description=f"Error rate (5xx responses) for {journey.name}",
        )

    def _build_error_rate_promql(
        self,
        service_name: str,
        endpoint: str,
    ) -> str:
        """
        Build PromQL query for error rate percentage

        Args:
            service_name: Service job label
            endpoint: HTTP endpoint path

        Returns:
            Valid PromQL error rate query (percentage)
        """
        # Error rate = (5xx requests / total requests) * 100
        return (
            f'('
            f'sum(rate(http_requests_total{{'
            f'job="{service_name}", '
            f'endpoint="{endpoint}", '
            f'status_code=~"5.."'
            f'}}[5m])) '
            f'/ '
            f'sum(rate(http_requests_total{{'
            f'job="{service_name}", '
            f'endpoint="{endpoint}"'
            f'}}[5m]))'
            f') * 100'
        )

    def _generate_availability_sli(
        self,
        journey: UserJourney,
        service_name: str,
    ) -> SLICandidate:
        """
        Generate availability SLI

        Calculates percentage of successful requests (non-5xx)

        Args:
            journey: UserJourney entity
            service_name: Service name for PromQL queries

        Returns:
            Availability SLI candidate
        """
        # PromQL query: percentage of non-5xx responses
        promql = self._build_availability_promql(
            service_name=service_name,
            endpoint=journey.entry_point,
        )

        return SLICandidate(
            name=f"{journey.name}-availability",
            metric_type=MetricType.AVAILABILITY,
            metric_definition=promql,
            measurement_window=self.default_measurement_window,
            data_sources={
                "prometheus": ["http_requests_total", "up"],
                "traces": [span["span_name"] for span in journey.step_sequence]
                    if journey.step_sequence else [],
                "logs": [],
            },
            unit="%",
            description=f"Availability (successful requests) for {journey.name}",
        )

    def _build_availability_promql(
        self,
        service_name: str,
        endpoint: str,
    ) -> str:
        """
        Build PromQL query for availability percentage

        Args:
            service_name: Service job label
            endpoint: HTTP endpoint path

        Returns:
            Valid PromQL availability query (percentage)
        """
        # Availability = (non-5xx requests / total requests) * 100
        return (
            f'('
            f'sum(rate(http_requests_total{{'
            f'job="{service_name}", '
            f'endpoint="{endpoint}", '
            f'status_code!~"5.."'
            f'}}[5m])) '
            f'/ '
            f'sum(rate(http_requests_total{{'
            f'job="{service_name}", '
            f'endpoint="{endpoint}"'
            f'}}[5m]))'
            f') * 100'
        )

    def persist_candidates(
        self,
        candidates: List[SLICandidate],
        journey_id: UUID,
        confidence_score: Decimal,
        evidence_pointers: List[Dict[str, Any]],
    ) -> List[SLI]:
        """
        Persist SLI candidates to database

        Args:
            candidates: List of SLICandidate objects
            journey_id: UUID of parent UserJourney
            confidence_score: Confidence score (0-100) from confidence scorer
            evidence_pointers: Evidence references from evidence linker

        Returns:
            List of persisted SLI entities

        Raises:
            ValueError: If validation fails
        """
        persisted_slis: List[SLI] = []

        for candidate in candidates:
            sli = SLI(
                journey_id=journey_id,
                name=candidate.name,
                metric_type=candidate.metric_type,
                metric_definition=candidate.metric_definition,
                measurement_window=candidate.measurement_window,
                data_sources=candidate.data_sources,
                confidence_score=confidence_score,
                evidence_pointers=evidence_pointers,
                current_value=None,  # Populated by monitoring
                unit=candidate.unit,
            )

            self.db.add(sli)
            persisted_slis.append(sli)

            logger.info(f"Persisted SLI: {sli.name} (confidence={confidence_score})")

        self.db.commit()

        return persisted_slis
