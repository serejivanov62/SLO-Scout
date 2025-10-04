"""
Data Quality Calculator Service

Calculates telemetry quality metrics per service:
- RUM coverage percentage
- Trace coverage percentage
- Structured log percentage
- request_id presence percentage

Per spec.md FR-018 and tasks.md T092a
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import UUID
import logging
import json

from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from prometheus_client import Gauge, Info

from ..models.service import Service
from ..models.capsule import Capsule


logger = logging.getLogger(__name__)


# Prometheus metrics for data quality
data_quality_rum_coverage = Gauge(
    'slo_scout_data_quality_rum_coverage_percent',
    'Percentage of user sessions with RUM data',
    ['service_name', 'environment']
)

data_quality_trace_coverage = Gauge(
    'slo_scout_data_quality_trace_coverage_percent',
    'Percentage of requests with trace data',
    ['service_name', 'environment']
)

data_quality_structured_log = Gauge(
    'slo_scout_data_quality_structured_log_percent',
    'Percentage of logs in structured JSON format',
    ['service_name', 'environment']
)

data_quality_request_id_presence = Gauge(
    'slo_scout_data_quality_request_id_percent',
    'Percentage of logs with request_id field',
    ['service_name', 'environment']
)


class DataQualityMetrics:
    """
    Data class holding quality metrics for a service
    """
    def __init__(
        self,
        service_id: UUID,
        service_name: str,
        environment: str,
        rum_coverage_pct: Decimal,
        trace_coverage_pct: Decimal,
        structured_log_pct: Decimal,
        request_id_presence_pct: Decimal,
        calculated_at: datetime,
        total_samples: int,
    ):
        self.service_id = service_id
        self.service_name = service_name
        self.environment = environment
        self.rum_coverage_pct = rum_coverage_pct
        self.trace_coverage_pct = trace_coverage_pct
        self.structured_log_pct = structured_log_pct
        self.request_id_presence_pct = request_id_presence_pct
        self.calculated_at = calculated_at
        self.total_samples = total_samples

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "service_id": str(self.service_id),
            "service_name": self.service_name,
            "environment": self.environment,
            "rum_coverage_pct": float(self.rum_coverage_pct),
            "trace_coverage_pct": float(self.trace_coverage_pct),
            "structured_log_pct": float(self.structured_log_pct),
            "request_id_presence_pct": float(self.request_id_presence_pct),
            "calculated_at": self.calculated_at.isoformat(),
            "total_samples": self.total_samples,
            "overall_quality_score": self._calculate_overall_score(),
        }

    def _calculate_overall_score(self) -> float:
        """Calculate weighted overall quality score"""
        weights = {
            "rum": 0.30,
            "trace": 0.35,
            "structured": 0.20,
            "request_id": 0.15,
        }

        score = (
            float(self.rum_coverage_pct) * weights["rum"]
            + float(self.trace_coverage_pct) * weights["trace"]
            + float(self.structured_log_pct) * weights["structured"]
            + float(self.request_id_presence_pct) * weights["request_id"]
        )

        return round(score, 2)


class DataQualityCalculator:
    """
    Calculate and export data quality metrics

    Per spec.md:
    - FR-018: Display data quality metrics for analyzed services
    - FR-019: Generate instrumentation recommendations when quality < threshold

    Per tasks.md T092a:
    - Calculate RUM coverage %, trace coverage %, structured log %, request_id %
    - Export to /metrics/data_quality endpoint
    - Update daily via cron job
    """

    # Quality thresholds for recommendations
    MIN_RUM_COVERAGE = 50.0  # Below this triggers RUM recommendation
    MIN_TRACE_COVERAGE = 5.0  # Below this triggers tracing recommendation
    MIN_STRUCTURED_LOG = 70.0  # Below this triggers structured logging recommendation
    MIN_REQUEST_ID = 80.0  # Below this triggers request_id recommendation

    # Lookback window for quality calculation
    DEFAULT_LOOKBACK_DAYS = 7

    def __init__(self, db: Session):
        self.db = db

    def calculate_for_service(
        self,
        service_id: UUID,
        lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ) -> DataQualityMetrics:
        """
        Calculate data quality metrics for a service

        Args:
            service_id: UUID of service to analyze
            lookback_days: Number of days to analyze

        Returns:
            DataQualityMetrics object

        Raises:
            ValueError: If service not found
        """
        service = self.db.query(Service).filter(Service.service_id == service_id).first()
        if not service:
            raise ValueError(f"Service {service_id} not found")

        logger.info(
            f"Calculating data quality for service {service.name} "
            f"(lookback={lookback_days} days)"
        )

        # Time range for analysis
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=lookback_days)

        # Query capsules in time range
        capsules = (
            self.db.query(Capsule)
            .filter(
                and_(
                    Capsule.service_id == service_id,
                    Capsule.time_bucket >= start_time,
                    Capsule.time_bucket <= end_time,
                )
            )
            .all()
        )

        if not capsules:
            logger.warning(f"No capsules found for service {service.name} in time range")
            return self._empty_metrics(service)

        # Calculate individual metrics
        rum_coverage = self._calculate_rum_coverage(capsules)
        trace_coverage = self._calculate_trace_coverage(capsules)
        structured_log_pct = self._calculate_structured_log_percentage(capsules)
        request_id_pct = self._calculate_request_id_percentage(capsules)

        metrics = DataQualityMetrics(
            service_id=service_id,
            service_name=service.name,
            environment=service.environment.value,
            rum_coverage_pct=rum_coverage,
            trace_coverage_pct=trace_coverage,
            structured_log_pct=structured_log_pct,
            request_id_presence_pct=request_id_pct,
            calculated_at=datetime.utcnow(),
            total_samples=len(capsules),
        )

        logger.info(
            f"Data quality for {service.name}: "
            f"RUM={rum_coverage:.1f}%, trace={trace_coverage:.1f}%, "
            f"structured={structured_log_pct:.1f}%, request_id={request_id_pct:.1f}%"
        )

        return metrics

    def _empty_metrics(self, service: Service) -> DataQualityMetrics:
        """Return zero metrics for services with no data"""
        return DataQualityMetrics(
            service_id=service.service_id,
            service_name=service.name,
            environment=service.environment.value,
            rum_coverage_pct=Decimal(0),
            trace_coverage_pct=Decimal(0),
            structured_log_pct=Decimal(0),
            request_id_presence_pct=Decimal(0),
            calculated_at=datetime.utcnow(),
            total_samples=0,
        )

    def _calculate_rum_coverage(self, capsules: List[Capsule]) -> Decimal:
        """
        Calculate percentage of samples with RUM data

        RUM data presence indicated by:
        - user_id or session_id in sample metadata
        - page_url or screen_name fields
        - client-side performance metrics

        Args:
            capsules: List of Capsule entities

        Returns:
            Coverage percentage (0-100)
        """
        rum_indicators = ["user_id", "session_id", "page_url", "screen_name", "client_timing"]
        total_capsules = len(capsules)
        rum_capsules = 0

        for capsule in capsules:
            if not capsule.sample_array:
                continue

            # Check if any sample has RUM indicators
            for sample in capsule.sample_array:
                if any(indicator in sample for indicator in rum_indicators):
                    rum_capsules += 1
                    break

        coverage = (rum_capsules / total_capsules * 100) if total_capsules > 0 else 0
        return Decimal(str(coverage))

    def _calculate_trace_coverage(self, capsules: List[Capsule]) -> Decimal:
        """
        Calculate percentage of samples with trace data

        Trace data presence indicated by:
        - trace_id field
        - span_id field
        - parent_span_id field

        Args:
            capsules: List of Capsule entities

        Returns:
            Coverage percentage (0-100)
        """
        total_capsules = len(capsules)
        traced_capsules = 0

        for capsule in capsules:
            if not capsule.sample_array:
                continue

            # Check if any sample has trace_id
            for sample in capsule.sample_array:
                if sample.get("trace_id") or sample.get("span_id"):
                    traced_capsules += 1
                    break

        coverage = (traced_capsules / total_capsules * 100) if total_capsules > 0 else 0
        return Decimal(str(coverage))

    def _calculate_structured_log_percentage(self, capsules: List[Capsule]) -> Decimal:
        """
        Calculate percentage of logs in structured JSON format

        Structured logs have:
        - Parseable JSON in sample
        - Multiple fields beyond just message
        - Standard fields like timestamp, level, message

        Args:
            capsules: List of Capsule entities

        Returns:
            Structured percentage (0-100)
        """
        total_samples = 0
        structured_samples = 0

        for capsule in capsules:
            if not capsule.sample_array:
                continue

            for sample in capsule.sample_array:
                total_samples += 1

                # Check if sample is structured (has multiple fields)
                if isinstance(sample, dict) and len(sample) >= 3:
                    # At least 3 fields suggests structure (timestamp, level, message)
                    structured_samples += 1

        percentage = (structured_samples / total_samples * 100) if total_samples > 0 else 0
        return Decimal(str(percentage))

    def _calculate_request_id_percentage(self, capsules: List[Capsule]) -> Decimal:
        """
        Calculate percentage of logs with request_id field

        Request IDs enable request correlation across services

        Args:
            capsules: List of Capsule entities

        Returns:
            Presence percentage (0-100)
        """
        total_samples = 0
        request_id_samples = 0

        for capsule in capsules:
            if not capsule.sample_array:
                continue

            for sample in capsule.sample_array:
                total_samples += 1

                # Check for request_id variants
                if any(
                    key in sample
                    for key in ["request_id", "requestId", "req_id", "correlation_id"]
                ):
                    request_id_samples += 1

        percentage = (request_id_samples / total_samples * 100) if total_samples > 0 else 0
        return Decimal(str(percentage))

    def export_metrics_to_prometheus(
        self,
        metrics: DataQualityMetrics,
    ) -> None:
        """
        Export metrics to Prometheus for /metrics endpoint

        Args:
            metrics: DataQualityMetrics to export
        """
        labels = {
            "service_name": metrics.service_name,
            "environment": metrics.environment,
        }

        data_quality_rum_coverage.labels(**labels).set(float(metrics.rum_coverage_pct))
        data_quality_trace_coverage.labels(**labels).set(float(metrics.trace_coverage_pct))
        data_quality_structured_log.labels(**labels).set(float(metrics.structured_log_pct))
        data_quality_request_id_presence.labels(**labels).set(float(metrics.request_id_presence_pct))

        logger.debug(f"Exported data quality metrics for {metrics.service_name}")

    def calculate_all_services(self) -> List[DataQualityMetrics]:
        """
        Calculate data quality for all active services

        Used by daily cron job (tasks.md T092a)

        Returns:
            List of DataQualityMetrics for all services
        """
        logger.info("Calculating data quality for all active services")

        services = (
            self.db.query(Service)
            .filter(Service.status == "active")
            .all()
        )

        all_metrics = []

        for service in services:
            try:
                metrics = self.calculate_for_service(service.service_id)
                self.export_metrics_to_prometheus(metrics)
                all_metrics.append(metrics)
            except Exception as e:
                logger.error(f"Failed to calculate metrics for {service.name}: {e}")
                continue

        logger.info(f"Calculated data quality for {len(all_metrics)} services")

        return all_metrics

    def identify_quality_gaps(
        self,
        metrics: DataQualityMetrics,
    ) -> List[Dict[str, Any]]:
        """
        Identify data quality gaps requiring instrumentation improvements

        Per spec.md FR-019: Generate instrumentation recommendations

        Args:
            metrics: DataQualityMetrics to analyze

        Returns:
            List of quality gap dictionaries with:
                - metric_name: str
                - current_value: float
                - threshold: float
                - severity: str (critical, important, nice_to_have)
                - recommendation_type: str
        """
        gaps = []

        # Check RUM coverage
        if metrics.rum_coverage_pct < Decimal(self.MIN_RUM_COVERAGE):
            gaps.append({
                "metric_name": "rum_coverage",
                "current_value": float(metrics.rum_coverage_pct),
                "threshold": self.MIN_RUM_COVERAGE,
                "severity": "important" if metrics.rum_coverage_pct < 20 else "nice_to_have",
                "recommendation_type": "enable_rum",
                "expected_uplift": min(30.0, self.MIN_RUM_COVERAGE - float(metrics.rum_coverage_pct)),
            })

        # Check trace coverage
        if metrics.trace_coverage_pct < Decimal(self.MIN_TRACE_COVERAGE):
            gaps.append({
                "metric_name": "trace_coverage",
                "current_value": float(metrics.trace_coverage_pct),
                "threshold": self.MIN_TRACE_COVERAGE,
                "severity": "critical",  # Traces are essential
                "recommendation_type": "add_tracing",
                "expected_uplift": min(40.0, self.MIN_TRACE_COVERAGE - float(metrics.trace_coverage_pct)),
            })

        # Check structured logging
        if metrics.structured_log_pct < Decimal(self.MIN_STRUCTURED_LOG):
            gaps.append({
                "metric_name": "structured_log",
                "current_value": float(metrics.structured_log_pct),
                "threshold": self.MIN_STRUCTURED_LOG,
                "severity": "important",
                "recommendation_type": "add_structured_logging",
                "expected_uplift": min(25.0, self.MIN_STRUCTURED_LOG - float(metrics.structured_log_pct)),
            })

        # Check request_id presence
        if metrics.request_id_presence_pct < Decimal(self.MIN_REQUEST_ID):
            gaps.append({
                "metric_name": "request_id_presence",
                "current_value": float(metrics.request_id_presence_pct),
                "threshold": self.MIN_REQUEST_ID,
                "severity": "important",
                "recommendation_type": "add_request_id",
                "expected_uplift": min(20.0, self.MIN_REQUEST_ID - float(metrics.request_id_presence_pct)),
            })

        logger.info(f"Identified {len(gaps)} quality gaps for {metrics.service_name}")

        return gaps
