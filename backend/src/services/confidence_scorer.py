"""
Confidence Scorer Service

Calculates confidence scores for SLI recommendations based on:
- Sample size (statistical significance)
- Data coverage percentage
- Trace completeness
- Time window stability

Per spec.md FR-003 and tasks.md T091
"""
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime, timedelta
import logging
import math

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models.user_journey import UserJourney
from ..models.capsule import Capsule


logger = logging.getLogger(__name__)


class ConfidenceMetrics:
    """
    Data class holding confidence calculation metrics
    """
    def __init__(
        self,
        sample_size: int,
        data_coverage_pct: Decimal,
        trace_completeness_pct: Decimal,
        time_window_days: int,
        rum_coverage_pct: Optional[Decimal] = None,
        log_coverage_pct: Optional[Decimal] = None,
    ):
        self.sample_size = sample_size
        self.data_coverage_pct = data_coverage_pct
        self.trace_completeness_pct = trace_completeness_pct
        self.time_window_days = time_window_days
        self.rum_coverage_pct = rum_coverage_pct or Decimal(0)
        self.log_coverage_pct = log_coverage_pct or Decimal(0)


class ConfidenceScorer:
    """
    Calculate confidence scores for SLI recommendations

    Per data-model.md:
    - confidence_score: float 0-100
    - Based on sample size, data coverage %, trace completeness

    Scoring algorithm:
    - Sample size score: Log scale with diminishing returns
    - Coverage score: Linear percentage
    - Completeness score: Trace span coverage
    - Weighted combination: 40% sample + 30% coverage + 30% completeness
    """

    # Scoring weights
    WEIGHT_SAMPLE_SIZE = 0.40
    WEIGHT_DATA_COVERAGE = 0.30
    WEIGHT_TRACE_COMPLETENESS = 0.30

    # Sample size thresholds for confidence levels
    MIN_SAMPLE_SIZE = 100  # Minimum for any confidence
    GOOD_SAMPLE_SIZE = 1000  # Threshold for high confidence
    EXCELLENT_SAMPLE_SIZE = 10000  # Threshold for excellent confidence

    def __init__(self, db: Session):
        self.db = db

    def calculate_confidence(
        self,
        journey: UserJourney,
        metrics: Optional[ConfidenceMetrics] = None,
    ) -> Decimal:
        """
        Calculate overall confidence score for a journey's SLI recommendations

        Args:
            journey: UserJourney entity
            metrics: Optional pre-calculated metrics (if None, will fetch)

        Returns:
            Confidence score from 0-100

        Raises:
            ValueError: If journey has insufficient data
        """
        if metrics is None:
            metrics = self._gather_metrics(journey)

        logger.info(
            f"Calculating confidence for journey {journey.name}: "
            f"samples={metrics.sample_size}, "
            f"coverage={metrics.data_coverage_pct}%, "
            f"completeness={metrics.trace_completeness_pct}%"
        )

        # Calculate component scores
        sample_score = self._score_sample_size(metrics.sample_size)
        coverage_score = self._score_data_coverage(metrics.data_coverage_pct)
        completeness_score = self._score_trace_completeness(metrics.trace_completeness_pct)

        # Weighted combination
        confidence = (
            sample_score * self.WEIGHT_SAMPLE_SIZE
            + coverage_score * self.WEIGHT_DATA_COVERAGE
            + completeness_score * self.WEIGHT_TRACE_COMPLETENESS
        )

        # Apply penalties for insufficient data
        confidence = self._apply_penalties(confidence, metrics)

        # Clamp to 0-100 range
        confidence = max(Decimal(0), min(Decimal(100), confidence))

        logger.info(
            f"Confidence score for {journey.name}: {confidence:.2f} "
            f"(sample={sample_score:.2f}, coverage={coverage_score:.2f}, "
            f"completeness={completeness_score:.2f})"
        )

        return confidence

    def _gather_metrics(self, journey: UserJourney) -> ConfidenceMetrics:
        """
        Gather telemetry metrics for confidence calculation

        Args:
            journey: UserJourney entity

        Returns:
            ConfidenceMetrics with collected data
        """
        # Sample size: total trace count
        sample_size = len(journey.sample_trace_ids) if journey.sample_trace_ids else 0

        # Data coverage: percentage of time window with data
        data_coverage_pct = self._calculate_data_coverage(journey)

        # Trace completeness: percentage of journey steps with trace data
        trace_completeness_pct = self._calculate_trace_completeness(journey)

        # Calculate time window
        time_window_days = (
            (journey.last_seen_at - journey.discovered_at).days
            if journey.last_seen_at and journey.discovered_at
            else 0
        )

        return ConfidenceMetrics(
            sample_size=sample_size,
            data_coverage_pct=Decimal(str(data_coverage_pct)),
            trace_completeness_pct=Decimal(str(trace_completeness_pct)),
            time_window_days=time_window_days,
        )

    def _calculate_data_coverage(self, journey: UserJourney) -> float:
        """
        Calculate percentage of time window with available data

        Args:
            journey: UserJourney entity

        Returns:
            Coverage percentage (0-100)
        """
        if not journey.discovered_at or not journey.last_seen_at:
            return 0.0

        # Query capsule data points within journey time range
        capsule_count = (
            self.db.query(func.count(Capsule.capsule_id))
            .filter(
                Capsule.service_id == journey.service_id,
                Capsule.time_bucket >= journey.discovered_at,
                Capsule.time_bucket <= journey.last_seen_at,
            )
            .scalar()
        )

        # Expected data points: one per hour in time range
        time_range = journey.last_seen_at - journey.discovered_at
        expected_hours = max(1, time_range.total_seconds() / 3600)

        # Coverage = actual / expected
        coverage = min(100.0, (capsule_count / expected_hours) * 100.0)

        return coverage

    def _calculate_trace_completeness(self, journey: UserJourney) -> float:
        """
        Calculate percentage of journey steps with trace data

        Args:
            journey: UserJourney entity

        Returns:
            Completeness percentage (0-100)
        """
        if not journey.step_sequence:
            return 0.0

        # Count steps with duration data (indicates trace presence)
        steps_with_data = sum(
            1 for step in journey.step_sequence
            if step.get("duration_p50") is not None
        )

        total_steps = len(journey.step_sequence)
        completeness = (steps_with_data / total_steps) * 100.0 if total_steps > 0 else 0.0

        return completeness

    def _score_sample_size(self, sample_size: int) -> Decimal:
        """
        Score sample size using logarithmic scale

        Statistical confidence increases logarithmically with sample size.
        Diminishing returns after EXCELLENT_SAMPLE_SIZE threshold.

        Args:
            sample_size: Number of samples

        Returns:
            Score from 0-100
        """
        if sample_size < self.MIN_SAMPLE_SIZE:
            # Linear scaling below minimum threshold
            return Decimal(str((sample_size / self.MIN_SAMPLE_SIZE) * 30.0))

        # Logarithmic scaling with base transition at GOOD_SAMPLE_SIZE
        if sample_size < self.GOOD_SAMPLE_SIZE:
            # Range: 30-70 for MIN to GOOD
            log_range = math.log10(self.GOOD_SAMPLE_SIZE) - math.log10(self.MIN_SAMPLE_SIZE)
            log_progress = math.log10(sample_size) - math.log10(self.MIN_SAMPLE_SIZE)
            score = 30.0 + (log_progress / log_range) * 40.0
        elif sample_size < self.EXCELLENT_SAMPLE_SIZE:
            # Range: 70-95 for GOOD to EXCELLENT
            log_range = math.log10(self.EXCELLENT_SAMPLE_SIZE) - math.log10(self.GOOD_SAMPLE_SIZE)
            log_progress = math.log10(sample_size) - math.log10(self.GOOD_SAMPLE_SIZE)
            score = 70.0 + (log_progress / log_range) * 25.0
        else:
            # Asymptotic approach to 100
            excess = sample_size - self.EXCELLENT_SAMPLE_SIZE
            score = 95.0 + min(5.0, (excess / self.EXCELLENT_SAMPLE_SIZE) * 5.0)

        return Decimal(str(score))

    def _score_data_coverage(self, coverage_pct: Decimal) -> Decimal:
        """
        Score data coverage percentage

        Linear scoring with threshold penalties

        Args:
            coverage_pct: Coverage percentage (0-100)

        Returns:
            Score from 0-100
        """
        # Direct linear mapping
        score = float(coverage_pct)

        # Penalty for sparse coverage
        if score < 50.0:
            score *= 0.8  # 20% penalty

        return Decimal(str(score))

    def _score_trace_completeness(self, completeness_pct: Decimal) -> Decimal:
        """
        Score trace completeness percentage

        Critical metric - incomplete traces reduce confidence significantly

        Args:
            completeness_pct: Completeness percentage (0-100)

        Returns:
            Score from 0-100
        """
        score = float(completeness_pct)

        # Severe penalty for incomplete traces
        if score < 80.0:
            score *= 0.7  # 30% penalty for incomplete journeys

        return Decimal(str(score))

    def _apply_penalties(
        self,
        base_confidence: Decimal,
        metrics: ConfidenceMetrics,
    ) -> Decimal:
        """
        Apply penalties for insufficient or low-quality data

        Args:
            base_confidence: Base confidence score
            metrics: ConfidenceMetrics

        Returns:
            Adjusted confidence score
        """
        confidence = float(base_confidence)

        # Penalty for very small sample size
        if metrics.sample_size < self.MIN_SAMPLE_SIZE:
            confidence *= 0.5  # 50% penalty

        # Penalty for very short time window (< 7 days)
        if metrics.time_window_days < 7:
            confidence *= 0.8  # 20% penalty

        # Penalty for missing RUM data
        if metrics.rum_coverage_pct < Decimal(10):
            confidence *= 0.9  # 10% penalty

        # Bonus for excellent data quality (all metrics > 90%)
        if (
            metrics.data_coverage_pct > Decimal(90)
            and metrics.trace_completeness_pct > Decimal(90)
            and metrics.sample_size > self.EXCELLENT_SAMPLE_SIZE
        ):
            confidence = min(100.0, confidence * 1.1)  # 10% bonus

        return Decimal(str(confidence))

    def estimate_confidence_uplift(
        self,
        current_metrics: ConfidenceMetrics,
        proposed_improvement: Dict[str, Any],
    ) -> Decimal:
        """
        Estimate confidence improvement from instrumentation changes

        Used for instrumentation recommendations (FR-020)

        Args:
            current_metrics: Current telemetry metrics
            proposed_improvement: Dict with keys like:
                - rum_coverage_increase: float (percentage points)
                - trace_sampling_increase: float
                - log_structured_increase: float

        Returns:
            Estimated confidence uplift (0-100)
        """
        # Calculate current score
        current_score = (
            self._score_sample_size(current_metrics.sample_size) * self.WEIGHT_SAMPLE_SIZE
            + self._score_data_coverage(current_metrics.data_coverage_pct) * self.WEIGHT_DATA_COVERAGE
            + self._score_trace_completeness(current_metrics.trace_completeness_pct) * self.WEIGHT_TRACE_COMPLETENESS
        )

        # Simulate improved metrics
        improved_coverage = min(
            Decimal(100),
            current_metrics.data_coverage_pct + Decimal(str(proposed_improvement.get("rum_coverage_increase", 0)))
        )
        improved_completeness = min(
            Decimal(100),
            current_metrics.trace_completeness_pct + Decimal(str(proposed_improvement.get("trace_sampling_increase", 0)))
        )

        # Calculate improved score
        improved_score = (
            self._score_sample_size(current_metrics.sample_size) * self.WEIGHT_SAMPLE_SIZE
            + self._score_data_coverage(improved_coverage) * self.WEIGHT_DATA_COVERAGE
            + self._score_trace_completeness(improved_completeness) * self.WEIGHT_TRACE_COMPLETENESS
        )

        uplift = improved_score - current_score

        logger.info(
            f"Estimated confidence uplift: {uplift:.2f} "
            f"(current={current_score:.2f}, improved={improved_score:.2f})"
        )

        return max(Decimal(0), uplift)
