"""
Dry-run Evaluator (T103)

Query Prometheus API for historical evaluation, estimate breach frequency.
Per spec.md FR-010: Perform dry-run evaluation of generated alerts.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import requests
from urllib.parse import urljoin
import logging


logger = logging.getLogger(__name__)


@dataclass
class BreachEvent:
    """Represents a single SLO breach event from historical data"""
    timestamp: datetime
    value: float
    threshold: float
    duration: timedelta


@dataclass
class DryRunResult:
    """Results from dry-run evaluation"""
    breach_count: int
    breach_events: List[BreachEvent]
    breach_percentage: float
    evaluation_period: timedelta
    total_samples: int
    breach_timestamps: List[datetime]


class DryRunEvaluator:
    """
    Evaluates alert rules against historical Prometheus data.

    Per FR-010: System MUST perform dry-run evaluation of generated alerts
    against historical metrics to estimate historical trigger frequency.
    """

    def __init__(self, prometheus_url: str, timeout: int = 30):
        """
        Initialize dry-run evaluator.

        Args:
            prometheus_url: Base URL of Prometheus server (e.g., http://localhost:9090)
            timeout: Request timeout in seconds
        """
        self.prometheus_url = prometheus_url.rstrip('/')
        self.timeout = timeout

    def evaluate_alert(
        self,
        metric_expr: str,
        threshold: float,
        comparison_operator: str,
        lookback_days: int = 30,
        step: timedelta = timedelta(minutes=1)
    ) -> DryRunResult:
        """
        Evaluate an alert condition against historical data.

        Args:
            metric_expr: PromQL expression for the metric
            threshold: Threshold value
            comparison_operator: Comparison operator (lt, lte, gt, gte, eq)
            lookback_days: Number of days of history to evaluate
            step: Step size for range queries

        Returns:
            DryRunResult with breach statistics

        Raises:
            PrometheusAPIError: If Prometheus API call fails
        """
        end_time = datetime.now()
        start_time = end_time - timedelta(days=lookback_days)

        # Query Prometheus for historical data
        values = self._query_range(
            query=metric_expr,
            start_time=start_time,
            end_time=end_time,
            step=step
        )

        # Evaluate breaches
        breach_events = []
        breach_timestamps = []

        for timestamp, value in values:
            if self._check_breach(value, threshold, comparison_operator):
                breach_event = BreachEvent(
                    timestamp=timestamp,
                    value=value,
                    threshold=threshold,
                    duration=step  # Simplified: each point is one step
                )
                breach_events.append(breach_event)
                breach_timestamps.append(timestamp)

        # Calculate statistics
        total_samples = len(values)
        breach_count = len(breach_events)
        breach_percentage = (breach_count / total_samples * 100) if total_samples > 0 else 0

        return DryRunResult(
            breach_count=breach_count,
            breach_events=breach_events,
            breach_percentage=breach_percentage,
            evaluation_period=timedelta(days=lookback_days),
            total_samples=total_samples,
            breach_timestamps=breach_timestamps
        )

    def estimate_breach_frequency(
        self,
        metric_expr: str,
        threshold: float,
        comparison_operator: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Estimate breach frequency for SLO simulation (FR-010).

        Args:
            metric_expr: PromQL expression
            threshold: Threshold value
            comparison_operator: Comparison operator
            lookback_days: Historical period to analyze

        Returns:
            Dict with breach frequency statistics:
            - breaches_per_day: Average breaches per day
            - breach_percentage: Percentage of time in breach
            - expected_monthly_breaches: Projected monthly breaches
            - confidence: Confidence in estimate (0-100)
        """
        result = self.evaluate_alert(
            metric_expr=metric_expr,
            threshold=threshold,
            comparison_operator=comparison_operator,
            lookback_days=lookback_days
        )

        breaches_per_day = result.breach_count / lookback_days
        expected_monthly_breaches = breaches_per_day * 30

        # Calculate confidence based on sample size
        # More samples = higher confidence
        confidence = min(100, (result.total_samples / 1000) * 100)

        return {
            "breaches_per_day": breaches_per_day,
            "breach_percentage": result.breach_percentage,
            "expected_monthly_breaches": expected_monthly_breaches,
            "total_breaches": result.breach_count,
            "evaluation_days": lookback_days,
            "total_samples": result.total_samples,
            "confidence": confidence,
            "breach_timestamps": [ts.isoformat() for ts in result.breach_timestamps]
        }

    def _query_range(
        self,
        query: str,
        start_time: datetime,
        end_time: datetime,
        step: timedelta
    ) -> List[tuple[datetime, float]]:
        """
        Execute a Prometheus range query.

        Args:
            query: PromQL query
            start_time: Start of time range
            end_time: End of time range
            step: Step size

        Returns:
            List of (timestamp, value) tuples

        Raises:
            PrometheusAPIError: If API call fails
        """
        url = urljoin(self.prometheus_url, '/api/v1/query_range')

        params = {
            'query': query,
            'start': start_time.timestamp(),
            'end': end_time.timestamp(),
            'step': f"{int(step.total_seconds())}s"
        }

        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'success':
                raise PrometheusAPIError(f"Query failed: {data.get('error', 'Unknown error')}")

            # Parse results
            results = []
            result_data = data.get('data', {}).get('result', [])

            if not result_data:
                logger.warning(f"No data returned for query: {query}")
                return results

            # Take first series (assuming single metric)
            # TODO: Handle multiple series if needed
            series = result_data[0]
            values = series.get('values', [])

            for timestamp, value in values:
                try:
                    dt = datetime.fromtimestamp(timestamp)
                    val = float(value)
                    results.append((dt, val))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Skipping invalid data point: {e}")
                    continue

            return results

        except requests.RequestException as e:
            raise PrometheusAPIError(f"Failed to query Prometheus: {str(e)}")

    def _check_breach(self, value: float, threshold: float, operator: str) -> bool:
        """
        Check if a value breaches the threshold.

        Args:
            value: Metric value
            threshold: Threshold to compare against
            operator: Comparison operator (lt, lte, gt, gte, eq)

        Returns:
            True if breach detected
        """
        op_map = {
            "lt": lambda v, t: v < t,
            "lte": lambda v, t: v <= t,
            "gt": lambda v, t: v > t,
            "gte": lambda v, t: v >= t,
            "eq": lambda v, t: v == t
        }

        check_func = op_map.get(operator)
        if not check_func:
            logger.error(f"Unknown operator: {operator}")
            return False

        return check_func(value, threshold)


class PrometheusAPIError(Exception):
    """Exception raised for Prometheus API errors"""
    pass


def evaluate_slo_historical_breaches(
    prometheus_url: str,
    metric_expr: str,
    threshold: float,
    comparison_operator: str,
    lookback_days: int = 30
) -> Dict[str, Any]:
    """
    Convenience function to estimate SLO breach frequency.

    Args:
        prometheus_url: Prometheus server URL
        metric_expr: PromQL expression
        threshold: SLO threshold
        comparison_operator: Comparison operator
        lookback_days: Days of history to analyze

    Returns:
        Dict with breach frequency statistics
    """
    evaluator = DryRunEvaluator(prometheus_url)
    return evaluator.estimate_breach_frequency(
        metric_expr=metric_expr,
        threshold=threshold,
        comparison_operator=comparison_operator,
        lookback_days=lookback_days
    )
