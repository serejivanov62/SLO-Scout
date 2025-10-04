"""
Journey ranking service per T088
Ranks journeys by traffic volume, error rate, latency variance
Assigns confidence scores per data-model.md
"""
from typing import List, Dict
from dataclasses import dataclass
import math


@dataclass
class RankedJourney:
    """Journey with ranking metadata"""
    journey_id: str
    name: str
    rank: int
    confidence_score: float
    traffic_volume: int
    error_rate: float
    latency_p95: float
    latency_variance: float
    business_impact_score: float


class JourneyRanker:
    """
    Ranks user journeys by criticality

    Per data-model.md UserJourney.confidence_score:
    - Based on sample size, traffic volume, data quality
    """

    def __init__(self):
        self.journeys = []

    def rank_journeys(
        self,
        journeys: List[Dict],
        traffic_weight: float = 0.4,
        error_weight: float = 0.3,
        latency_weight: float = 0.3
    ) -> List[RankedJourney]:
        """
        Rank journeys by criticality

        Args:
            journeys: List of UserJourney dictionaries
            traffic_weight: Weight for traffic volume (0-1)
            error_weight: Weight for error rate (0-1)
            latency_weight: Weight for latency variance (0-1)

        Returns:
            List of ranked journeys, sorted by rank

        Ranking formula:
            score = (traffic_norm * traffic_weight)
                  + (error_rate * error_weight)
                  + (latency_var_norm * latency_weight)
        """
        if not journeys:
            return []

        # Normalize metrics
        max_traffic = max(j.get('traffic_volume', 0) for j in journeys)
        max_latency_var = max(
            self._calculate_latency_variance(j) for j in journeys
        )

        ranked = []

        for journey in journeys:
            traffic_volume = journey.get('traffic_volume', 0)
            error_rate = journey.get('error_rate', 0)
            latency_variance = self._calculate_latency_variance(journey)

            # Normalize to [0, 1]
            traffic_norm = traffic_volume / max_traffic if max_traffic > 0 else 0
            latency_var_norm = latency_variance / max_latency_var if max_latency_var > 0 else 0

            # Calculate criticality score
            criticality_score = (
                traffic_norm * traffic_weight +
                error_rate * error_weight +
                latency_var_norm * latency_weight
            )

            # Calculate confidence score (0-100)
            confidence_score = self._calculate_confidence(journey)

            ranked_journey = RankedJourney(
                journey_id=journey.get('journey_id', ''),
                name=journey['name'],
                rank=0,  # Will be set after sorting
                confidence_score=confidence_score,
                traffic_volume=traffic_volume,
                error_rate=error_rate,
                latency_p95=journey.get('avg_duration_ms', 0) * 1.5,  # Estimate p95
                latency_variance=latency_variance,
                business_impact_score=criticality_score * 100
            )

            ranked.append(ranked_journey)

        # Sort by business impact (descending)
        ranked.sort(key=lambda j: j.business_impact_score, reverse=True)

        # Assign ranks
        for i, journey in enumerate(ranked):
            journey.rank = i + 1

        return ranked

    def get_top_journeys(
        self,
        journeys: List[Dict],
        top_n: int = 5,
        min_confidence: float = 70.0
    ) -> List[RankedJourney]:
        """
        Get top N critical journeys

        Args:
            journeys: List of journeys
            top_n: Number of top journeys to return
            min_confidence: Minimum confidence score threshold

        Returns:
            Top N journeys with confidence >= threshold
        """
        ranked = self.rank_journeys(journeys)

        # Filter by confidence
        filtered = [j for j in ranked if j.confidence_score >= min_confidence]

        return filtered[:top_n]

    def _calculate_latency_variance(self, journey: Dict) -> float:
        """
        Calculate latency variance from step sequence

        Higher variance = more unstable = higher priority for monitoring
        """
        steps = journey.get('step_sequence', [])
        if not steps:
            return 0.0

        # Get durations
        durations = [step.get('duration_p50', 0) for step in steps]
        if not durations:
            return 0.0

        # Calculate variance
        mean = sum(durations) / len(durations)
        variance = sum((d - mean) ** 2 for d in durations) / len(durations)

        return math.sqrt(variance)  # Standard deviation

    def _calculate_confidence(self, journey: Dict) -> float:
        """
        Calculate confidence score (0-100)

        Based on:
        - Sample size (traffic volume)
        - Trace completeness
        - Data coverage
        """
        traffic_volume = journey.get('traffic_volume', 0)
        sample_trace_count = len(journey.get('sample_trace_ids', []))
        step_count = len(journey.get('step_sequence', []))

        # Base confidence from sample size
        # log10(traffic) * 10, capped at 70
        base_confidence = min(70, math.log10(max(1, traffic_volume)) * 10)

        # Boost from trace completeness
        trace_completeness = min(10, sample_trace_count)  # Up to +10

        # Boost from step sequence coverage
        step_coverage = min(20, step_count * 2)  # Up to +20

        confidence = base_confidence + trace_completeness + step_coverage

        return min(100, confidence)
