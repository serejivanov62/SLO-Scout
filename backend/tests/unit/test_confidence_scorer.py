"""
Unit tests for Confidence Scorer Service

Tests T091: Confidence scoring based on sample size, coverage, completeness
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4
import math

from src.services.confidence_scorer import ConfidenceScorer, ConfidenceMetrics
from src.models.user_journey import UserJourney
from src.models.service import Service, Environment
from src.models.capsule import Capsule


class TestConfidenceScorer:
    """Test confidence score calculation"""

    @pytest.fixture
    def sample_service(self, db_session):
        """Create sample service"""
        service = Service(
            service_id=uuid4(),
            name="test-service",
            environment=Environment.PRODUCTION,
            owner_team="test-team",
            telemetry_endpoints={},
            status="active",
        )
        db_session.add(service)
        db_session.commit()
        return service

    @pytest.fixture
    def sample_journey_high_quality(self, db_session, sample_service):
        """Create journey with high-quality data"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="high-quality-journey",
            entry_point="/api/checkout",
            exit_point="/api/orders",
            step_sequence=[
                {"span_name": "step1", "duration_p50": 100.0, "error_rate": 0.01},
                {"span_name": "step2", "duration_p50": 150.0, "error_rate": 0.02},
                {"span_name": "step3", "duration_p50": 80.0, "error_rate": 0.01},
            ],
            traffic_volume_per_day=100000,
            confidence_score=Decimal("0.0"),  # Will be calculated
            sample_trace_ids=[f"trace-{i:04d}" for i in range(15000)],  # Excellent sample size
            discovered_at=datetime.utcnow() - timedelta(days=30),
            last_seen_at=datetime.utcnow(),
        )
        db_session.add(journey)
        db_session.commit()
        return journey

    @pytest.fixture
    def sample_journey_low_quality(self, db_session, sample_service):
        """Create journey with low-quality data"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="low-quality-journey",
            entry_point="/api/test",
            exit_point="/api/test/done",
            step_sequence=[
                {"span_name": "step1", "duration_p50": None, "error_rate": None},  # Missing data
            ],
            traffic_volume_per_day=500,
            confidence_score=Decimal("0.0"),
            sample_trace_ids=[f"trace-{i}" for i in range(50)],  # Low sample size
            discovered_at=datetime.utcnow() - timedelta(days=3),  # Short window
            last_seen_at=datetime.utcnow(),
        )
        db_session.add(journey)
        db_session.commit()
        return journey

    @pytest.fixture
    def capsules_high_coverage(self, db_session, sample_service, sample_journey_high_quality):
        """Create capsules with high coverage"""
        capsules = []
        start_time = datetime.utcnow() - timedelta(days=30)

        # Create hourly capsules for 30 days (720 capsules)
        for hour in range(720):
            time_bucket = start_time + timedelta(hours=hour)
            capsule = Capsule(
                capsule_id=uuid4(),
                fingerprint_hash=f"hash-{hour}",
                template="User logged in from {{IP}}",
                count=100,
                severity_distribution={"INFO": 90, "WARN": 10},
                sample_array=[{"message": "test", "trace_id": f"trace-{hour}"}],
                service_id=sample_service.service_id,
                first_seen_at=time_bucket,
                last_seen_at=time_bucket,
                time_bucket=time_bucket,
                redaction_applied=True,
            )
            capsules.append(capsule)
            db_session.add(capsule)

        db_session.commit()
        return capsules

    @pytest.fixture
    def scorer(self, db_session):
        """Create confidence scorer instance"""
        return ConfidenceScorer(db_session)

    def test_calculate_confidence_high_quality_data(
        self, scorer, sample_journey_high_quality, capsules_high_coverage
    ):
        """Test confidence calculation with high-quality data"""
        confidence = scorer.calculate_confidence(sample_journey_high_quality)

        # High quality should yield high confidence (> 80%)
        assert confidence > Decimal("80.0"), f"Expected >80% confidence, got {confidence}"
        assert confidence <= Decimal("100.0"), "Confidence should not exceed 100%"

    def test_calculate_confidence_low_quality_data(self, scorer, sample_journey_low_quality):
        """Test confidence calculation with low-quality data"""
        confidence = scorer.calculate_confidence(sample_journey_low_quality)

        # Low quality should yield low confidence (< 50%)
        assert confidence < Decimal("50.0"), f"Expected <50% confidence, got {confidence}"
        assert confidence >= Decimal("0.0"), "Confidence should not be negative"

    def test_sample_size_scoring_logarithmic(self, scorer):
        """Test sample size scoring uses logarithmic scale"""
        # Test key thresholds
        score_50 = scorer._score_sample_size(50)
        score_100 = scorer._score_sample_size(100)  # MIN_SAMPLE_SIZE
        score_1000 = scorer._score_sample_size(1000)  # GOOD_SAMPLE_SIZE
        score_10000 = scorer._score_sample_size(10000)  # EXCELLENT_SAMPLE_SIZE

        # Below minimum should be low score
        assert score_50 < Decimal("30.0")

        # Minimum threshold should be ~30
        assert Decimal("25.0") < score_100 < Decimal("35.0")

        # Good sample size should be ~70
        assert Decimal("65.0") < score_1000 < Decimal("75.0")

        # Excellent sample size should be ~95
        assert Decimal("90.0") < score_10000 < Decimal("100.0")

        # Diminishing returns
        assert score_1000 - score_100 > score_10000 - score_1000

    def test_data_coverage_scoring_linear(self, scorer):
        """Test data coverage scoring is linear with penalties"""
        # Full coverage
        score_100 = scorer._score_data_coverage(Decimal("100.0"))
        assert score_100 == Decimal("100.0")

        # Good coverage (no penalty)
        score_80 = scorer._score_data_coverage(Decimal("80.0"))
        assert score_80 == Decimal("80.0")

        # Poor coverage (with penalty)
        score_40 = scorer._score_data_coverage(Decimal("40.0"))
        assert score_40 < Decimal("40.0"), "Should apply penalty for sparse coverage"
        assert score_40 == Decimal("40.0") * Decimal("0.8")  # 20% penalty

    def test_trace_completeness_scoring_with_penalty(self, scorer):
        """Test trace completeness scoring applies severe penalty for incomplete traces"""
        # Complete traces
        score_100 = scorer._score_trace_completeness(Decimal("100.0"))
        assert score_100 == Decimal("100.0")

        # Good completeness (no penalty)
        score_90 = scorer._score_trace_completeness(Decimal("90.0"))
        assert score_90 == Decimal("90.0")

        # Incomplete traces (severe penalty)
        score_70 = scorer._score_trace_completeness(Decimal("70.0"))
        assert score_70 < Decimal("70.0"), "Should apply penalty for incomplete traces"
        assert score_70 == Decimal("70.0") * Decimal("0.7")  # 30% penalty

    def test_confidence_metrics_data_class(self):
        """Test ConfidenceMetrics data class initialization"""
        metrics = ConfidenceMetrics(
            sample_size=5000,
            data_coverage_pct=Decimal("85.5"),
            trace_completeness_pct=Decimal("92.0"),
            time_window_days=30,
            rum_coverage_pct=Decimal("60.0"),
            log_coverage_pct=Decimal("75.0"),
        )

        assert metrics.sample_size == 5000
        assert metrics.data_coverage_pct == Decimal("85.5")
        assert metrics.trace_completeness_pct == Decimal("92.0")
        assert metrics.time_window_days == 30
        assert metrics.rum_coverage_pct == Decimal("60.0")

    def test_gather_metrics_from_journey(
        self, scorer, sample_journey_high_quality, capsules_high_coverage
    ):
        """Test gathering metrics from journey data"""
        metrics = scorer._gather_metrics(sample_journey_high_quality)

        assert metrics.sample_size == 15000  # From sample_trace_ids
        assert metrics.data_coverage_pct > Decimal("0")
        assert metrics.trace_completeness_pct == Decimal("100.0")  # All steps have duration
        assert metrics.time_window_days == 30

    def test_calculate_data_coverage_hourly_buckets(
        self, scorer, sample_journey_high_quality, capsules_high_coverage
    ):
        """Test data coverage calculation based on hourly capsule buckets"""
        coverage = scorer._calculate_data_coverage(sample_journey_high_quality)

        # 30 days = 720 hours, with 720 capsules = 100% coverage
        assert coverage >= 95.0, f"Expected ~100% coverage, got {coverage}"

    def test_calculate_trace_completeness_from_steps(self, scorer, sample_journey_high_quality):
        """Test trace completeness calculation from step sequence"""
        completeness = scorer._calculate_trace_completeness(sample_journey_high_quality)

        # All 3 steps have duration_p50 data
        assert completeness == 100.0

    def test_calculate_trace_completeness_partial_data(self, scorer, sample_journey_low_quality):
        """Test trace completeness with missing step data"""
        completeness = scorer._calculate_trace_completeness(sample_journey_low_quality)

        # 0 of 1 steps have duration data
        assert completeness == 0.0

    def test_apply_penalties_small_sample_size(self, scorer):
        """Test penalty applied for very small sample size"""
        base_confidence = Decimal("80.0")
        metrics = ConfidenceMetrics(
            sample_size=50,  # Below MIN_SAMPLE_SIZE (100)
            data_coverage_pct=Decimal("90.0"),
            trace_completeness_pct=Decimal("90.0"),
            time_window_days=30,
        )

        adjusted = scorer._apply_penalties(base_confidence, metrics)

        # Should apply 50% penalty
        expected = float(base_confidence) * 0.5
        assert float(adjusted) == pytest.approx(expected, rel=0.01)

    def test_apply_penalties_short_time_window(self, scorer):
        """Test penalty applied for short time window"""
        base_confidence = Decimal("80.0")
        metrics = ConfidenceMetrics(
            sample_size=1000,
            data_coverage_pct=Decimal("90.0"),
            trace_completeness_pct=Decimal("90.0"),
            time_window_days=3,  # < 7 days
        )

        adjusted = scorer._apply_penalties(base_confidence, metrics)

        # Should apply 20% penalty
        expected = float(base_confidence) * 0.8
        assert float(adjusted) == pytest.approx(expected, rel=0.01)

    def test_apply_penalties_missing_rum(self, scorer):
        """Test penalty applied for missing RUM data"""
        base_confidence = Decimal("80.0")
        metrics = ConfidenceMetrics(
            sample_size=1000,
            data_coverage_pct=Decimal("90.0"),
            trace_completeness_pct=Decimal("90.0"),
            time_window_days=30,
            rum_coverage_pct=Decimal("5.0"),  # < 10%
        )

        adjusted = scorer._apply_penalties(base_confidence, metrics)

        # Should apply 10% penalty
        expected = float(base_confidence) * 0.9
        assert float(adjusted) == pytest.approx(expected, rel=0.01)

    def test_apply_bonus_excellent_data(self, scorer):
        """Test bonus applied for excellent data quality"""
        base_confidence = Decimal("85.0")
        metrics = ConfidenceMetrics(
            sample_size=15000,  # > EXCELLENT_SAMPLE_SIZE (10000)
            data_coverage_pct=Decimal("95.0"),  # > 90%
            trace_completeness_pct=Decimal("95.0"),  # > 90%
            time_window_days=30,
        )

        adjusted = scorer._apply_penalties(base_confidence, metrics)

        # Should apply 10% bonus
        expected = min(100.0, float(base_confidence) * 1.1)
        assert float(adjusted) == pytest.approx(expected, rel=0.01)

    def test_confidence_clamped_to_range(self, scorer):
        """Test confidence score is clamped to 0-100 range"""
        # Test with journey that might produce >100
        metrics = ConfidenceMetrics(
            sample_size=50000,
            data_coverage_pct=Decimal("100.0"),
            trace_completeness_pct=Decimal("100.0"),
            time_window_days=90,
        )

        # Mock journey for calculation
        from src.models.user_journey import UserJourney
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=uuid4(),
            name="test",
            entry_point="/test",
            exit_point="/test",
            step_sequence=[],
            traffic_volume_per_day=1000,
            confidence_score=Decimal("0"),
            sample_trace_ids=[],
        )

        confidence = scorer.calculate_confidence(journey, metrics)

        assert confidence >= Decimal("0.0")
        assert confidence <= Decimal("100.0")

    def test_estimate_confidence_uplift(self, scorer):
        """Test confidence uplift estimation for instrumentation improvements"""
        current_metrics = ConfidenceMetrics(
            sample_size=1000,
            data_coverage_pct=Decimal("60.0"),
            trace_completeness_pct=Decimal("70.0"),
            time_window_days=14,
        )

        proposed_improvement = {
            "rum_coverage_increase": 30.0,  # +30% RUM coverage
            "trace_sampling_increase": 20.0,  # +20% trace coverage
        }

        uplift = scorer.estimate_confidence_uplift(current_metrics, proposed_improvement)

        # Should show positive uplift
        assert uplift > Decimal("0.0")
        assert uplift < Decimal("50.0"), "Uplift should be reasonable"

    def test_estimate_uplift_with_maxed_metrics(self, scorer):
        """Test uplift estimation when metrics already maxed"""
        current_metrics = ConfidenceMetrics(
            sample_size=10000,
            data_coverage_pct=Decimal("98.0"),
            trace_completeness_pct=Decimal("99.0"),
            time_window_days=30,
        )

        proposed_improvement = {
            "rum_coverage_increase": 1.0,  # Small increase
            "trace_sampling_increase": 1.0,
        }

        uplift = scorer.estimate_confidence_uplift(current_metrics, proposed_improvement)

        # Should show minimal uplift
        assert uplift >= Decimal("0.0")
        assert uplift < Decimal("5.0"), "Uplift should be small for already-good metrics"

    def test_weighted_combination_formula(self, scorer):
        """Test confidence uses correct weighted combination"""
        # Create controlled metrics
        sample_score = Decimal("60.0")
        coverage_score = Decimal("80.0")
        completeness_score = Decimal("90.0")

        # Calculate expected weighted average
        expected = (
            sample_score * Decimal(str(scorer.WEIGHT_SAMPLE_SIZE))
            + coverage_score * Decimal(str(scorer.WEIGHT_DATA_COVERAGE))
            + completeness_score * Decimal(str(scorer.WEIGHT_TRACE_COMPLETENESS))
        )

        # Weights should sum to 1.0
        total_weight = (
            scorer.WEIGHT_SAMPLE_SIZE
            + scorer.WEIGHT_DATA_COVERAGE
            + scorer.WEIGHT_TRACE_COMPLETENESS
        )
        assert total_weight == pytest.approx(1.0)

    def test_confidence_score_range_validation(self, scorer, sample_journey_high_quality):
        """Test confidence score always in valid range per data-model.md"""
        confidence = scorer.calculate_confidence(sample_journey_high_quality)

        # Per data-model.md: confidence_score 0-100
        assert confidence >= Decimal("0.0")
        assert confidence <= Decimal("100.0")

    def test_calculate_confidence_with_no_capsules(
        self, scorer, db_session, sample_service
    ):
        """Test confidence calculation with no capsule data"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="no-data-journey",
            entry_point="/api/test",
            exit_point="/api/test",
            step_sequence=[],
            traffic_volume_per_day=100,
            confidence_score=Decimal("0.0"),
            sample_trace_ids=[],
            discovered_at=datetime.utcnow() - timedelta(days=1),
            last_seen_at=datetime.utcnow(),
        )

        confidence = scorer.calculate_confidence(journey)

        # Should return low confidence but not error
        assert confidence >= Decimal("0.0")
        assert confidence < Decimal("30.0"), "No data should yield low confidence"
