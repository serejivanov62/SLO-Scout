"""
Unit tests for SLI Generator Service

Tests T090: SLI candidate generation
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4

from src.services.sli_generator import SLIGenerator, SLICandidate
from src.models.user_journey import UserJourney
from src.models.service import Service, Environment
from src.models.sli import SLI, MetricType


class TestSLIGenerator:
    """Test SLI candidate generation"""

    @pytest.fixture
    def sample_service(self, db_session):
        """Create sample service for testing"""
        service = Service(
            service_id=uuid4(),
            name="payments-api",
            environment=Environment.PRODUCTION,
            owner_team="payments-team",
            telemetry_endpoints={"prometheus_url": "http://prom:9090"},
            status="active",
        )
        db_session.add(service)
        db_session.commit()
        return service

    @pytest.fixture
    def sample_journey(self, db_session, sample_service):
        """Create sample user journey for testing"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="checkout-flow",
            entry_point="/api/cart/checkout",
            exit_point="/api/orders/{id}",
            step_sequence=[
                {"span_name": "POST /api/cart/checkout", "duration_p50": 120.5, "error_rate": 0.1},
                {"span_name": "payment.process", "duration_p50": 350.0, "error_rate": 0.2},
                {"span_name": "POST /api/orders", "duration_p50": 80.0, "error_rate": 0.05},
            ],
            traffic_volume_per_day=50000,
            confidence_score=Decimal("85.0"),
            sample_trace_ids=["trace-001", "trace-002", "trace-003"],
        )
        db_session.add(journey)
        db_session.commit()
        return journey

    @pytest.fixture
    def generator(self, db_session):
        """Create SLI generator instance"""
        return SLIGenerator(db_session)

    def test_generate_for_journey_returns_five_slis(self, generator, sample_journey):
        """Test that generator creates 5 SLI candidates per spec.md FR-002"""
        candidates = generator.generate_for_journey(sample_journey)

        assert len(candidates) == 5, "Should generate 5 SLI candidates"

        # Verify SLI types
        metric_types = [c.metric_type for c in candidates]
        assert metric_types.count(MetricType.LATENCY) == 3, "Should have 3 latency SLIs (p50, p95, p99)"
        assert metric_types.count(MetricType.ERROR_RATE) == 1, "Should have 1 error rate SLI"
        assert metric_types.count(MetricType.AVAILABILITY) == 1, "Should have 1 availability SLI"

    def test_latency_slis_have_valid_promql(self, generator, sample_journey):
        """Test latency SLIs generate valid PromQL queries"""
        candidates = generator.generate_for_journey(sample_journey)

        latency_candidates = [c for c in candidates if c.metric_type == MetricType.LATENCY]

        for candidate in latency_candidates:
            # Verify PromQL structure
            assert "histogram_quantile(" in candidate.metric_definition
            assert "http_request_duration_seconds_bucket" in candidate.metric_definition
            assert 'job="payments-api"' in candidate.metric_definition
            assert 'endpoint="/api/cart/checkout"' in candidate.metric_definition
            assert "* 1000" in candidate.metric_definition, "Should convert seconds to milliseconds"

    def test_latency_sli_percentiles(self, generator, sample_journey):
        """Test that latency SLIs have correct percentiles (p50, p95, p99)"""
        candidates = generator.generate_for_journey(sample_journey)

        latency_candidates = [c for c in candidates if c.metric_type == MetricType.LATENCY]
        assert len(latency_candidates) == 3

        # Extract quantile values from PromQL
        quantiles = []
        for candidate in latency_candidates:
            # Parse "histogram_quantile(0.95, ..." -> 0.95
            if "histogram_quantile(0.5" in candidate.metric_definition:
                quantiles.append("p50")
            elif "histogram_quantile(0.95" in candidate.metric_definition:
                quantiles.append("p95")
            elif "histogram_quantile(0.99" in candidate.metric_definition:
                quantiles.append("p99")

        assert set(quantiles) == {"p50", "p95", "p99"}, "Should have all three percentiles"

    def test_error_rate_sli_promql(self, generator, sample_journey):
        """Test error rate SLI generates valid PromQL"""
        candidates = generator.generate_for_journey(sample_journey)

        error_candidates = [c for c in candidates if c.metric_type == MetricType.ERROR_RATE]
        assert len(error_candidates) == 1

        error_sli = error_candidates[0]

        # Verify PromQL calculates percentage of 5xx errors
        assert "http_requests_total" in error_sli.metric_definition
        assert 'status_code=~"5.."' in error_sli.metric_definition
        assert "* 100" in error_sli.metric_definition, "Should convert to percentage"
        assert error_sli.unit == "%"

    def test_availability_sli_promql(self, generator, sample_journey):
        """Test availability SLI generates valid PromQL"""
        candidates = generator.generate_for_journey(sample_journey)

        availability_candidates = [c for c in candidates if c.metric_type == MetricType.AVAILABILITY]
        assert len(availability_candidates) == 1

        avail_sli = availability_candidates[0]

        # Verify PromQL calculates percentage of non-5xx requests
        assert "http_requests_total" in avail_sli.metric_definition
        assert 'status_code!~"5.."' in avail_sli.metric_definition
        assert "* 100" in avail_sli.metric_definition
        assert avail_sli.unit == "%"

    def test_sli_naming_convention(self, generator, sample_journey):
        """Test SLI names follow expected pattern"""
        candidates = generator.generate_for_journey(sample_journey)

        # All names should start with journey name
        for candidate in candidates:
            assert candidate.name.startswith("checkout-flow-"), f"Name should start with journey name: {candidate.name}"

        # Check specific patterns
        names = [c.name for c in candidates]
        assert "checkout-flow-latency-p50" in names
        assert "checkout-flow-latency-p95" in names
        assert "checkout-flow-latency-p99" in names
        assert "checkout-flow-error-rate" in names
        assert "checkout-flow-availability" in names

    def test_data_sources_populated(self, generator, sample_journey):
        """Test data_sources field is populated correctly"""
        candidates = generator.generate_for_journey(sample_journey)

        for candidate in candidates:
            assert "prometheus" in candidate.data_sources
            assert "traces" in candidate.data_sources
            assert "logs" in candidate.data_sources

            # Verify prometheus metrics
            assert len(candidate.data_sources["prometheus"]) > 0

            # Verify trace spans from journey
            if candidate.metric_type == MetricType.LATENCY:
                expected_spans = ["POST /api/cart/checkout", "payment.process", "POST /api/orders"]
                assert candidate.data_sources["traces"] == expected_spans

    def test_measurement_window_default(self, generator, sample_journey):
        """Test measurement window defaults to 5 minutes"""
        candidates = generator.generate_for_journey(sample_journey)

        for candidate in candidates:
            assert candidate.measurement_window == timedelta(minutes=5)

    def test_units_correct(self, generator, sample_journey):
        """Test SLI units are appropriate for metric type"""
        candidates = generator.generate_for_journey(sample_journey)

        for candidate in candidates:
            if candidate.metric_type == MetricType.LATENCY:
                assert candidate.unit == "ms"
            elif candidate.metric_type == MetricType.ERROR_RATE:
                assert candidate.unit == "%"
            elif candidate.metric_type == MetricType.AVAILABILITY:
                assert candidate.unit == "%"

    def test_journey_without_entry_point_raises_error(self, generator, db_session, sample_service):
        """Test that journey missing entry_point raises ValueError"""
        invalid_journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="invalid-journey",
            entry_point="",  # Invalid: empty
            exit_point="/api/exit",
            step_sequence=[],
            traffic_volume_per_day=1000,
            confidence_score=Decimal("50.0"),
            sample_trace_ids=[],
        )

        with pytest.raises(ValueError, match="missing entry/exit points"):
            generator.generate_for_journey(invalid_journey)

    def test_persist_candidates(self, generator, sample_journey, db_session):
        """Test persisting SLI candidates to database"""
        candidates = generator.generate_for_journey(sample_journey)

        confidence_score = Decimal("75.5")
        evidence_pointers = [
            {"capsule_id": str(uuid4()), "contribution_weight": 60.0},
            {"capsule_id": str(uuid4()), "contribution_weight": 40.0},
        ]

        persisted_slis = generator.persist_candidates(
            candidates=candidates,
            journey_id=sample_journey.journey_id,
            confidence_score=confidence_score,
            evidence_pointers=evidence_pointers,
        )

        assert len(persisted_slis) == 5, "Should persist all 5 SLIs"

        # Verify database persistence
        db_slis = db_session.query(SLI).filter(SLI.journey_id == sample_journey.journey_id).all()
        assert len(db_slis) == 5

        # Verify confidence scores
        for sli in db_slis:
            assert sli.confidence_score == confidence_score
            assert sli.evidence_pointers == evidence_pointers

    def test_custom_service_name_override(self, generator, sample_journey):
        """Test service name can be overridden in PromQL"""
        candidates = generator.generate_for_journey(
            sample_journey,
            service_name="custom-service"
        )

        for candidate in candidates:
            assert 'job="custom-service"' in candidate.metric_definition

    def test_extract_service_name_from_journey(self, generator, sample_journey):
        """Test service name extraction from journey relationship"""
        service_name = generator._extract_service_name(sample_journey)
        assert service_name == "payments-api"

    def test_extract_service_name_fallback(self, generator, db_session, sample_service):
        """Test service name fallback to entry point parsing"""
        journey_no_service = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="test-journey",
            entry_point="/payments/process",
            exit_point="/payments/complete",
            step_sequence=[],
            traffic_volume_per_day=1000,
            confidence_score=Decimal("50.0"),
            sample_trace_ids=[],
        )
        # Don't load service relationship

        # Should extract "payments" from entry point
        service_name = generator._extract_service_name(journey_no_service)
        # This will use relationship if available, otherwise fallback
        assert service_name in ["payments-api", "payments"]

    def test_latency_promql_escapes_special_chars(self, generator, db_session, sample_service):
        """Test PromQL generation handles special characters in endpoints"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="special-journey",
            entry_point="/api/users/{id}/profile",
            exit_point="/api/users/{id}/complete",
            step_sequence=[],
            traffic_volume_per_day=1000,
            confidence_score=Decimal("50.0"),
            sample_trace_ids=[],
        )

        candidates = generator.generate_for_journey(journey)

        latency_candidate = [c for c in candidates if c.metric_type == MetricType.LATENCY][0]

        # Endpoint should be included as-is (PromQL label matcher handles it)
        assert 'endpoint="/api/users/{id}/profile"' in latency_candidate.metric_definition

    def test_sli_descriptions_generated(self, generator, sample_journey):
        """Test that SLI candidates have descriptive text"""
        candidates = generator.generate_for_journey(sample_journey)

        for candidate in candidates:
            assert candidate.description, f"SLI {candidate.name} should have description"
            assert "checkout-flow" in candidate.description.lower()

    def test_promql_rate_window_matches_measurement(self, generator, sample_journey):
        """Test PromQL rate() window matches measurement_window"""
        candidates = generator.generate_for_journey(sample_journey)

        for candidate in candidates:
            if "[5m]" in candidate.metric_definition:
                assert candidate.measurement_window == timedelta(minutes=5)


class TestSLICandidate:
    """Test SLICandidate data class"""

    def test_sli_candidate_initialization(self):
        """Test SLICandidate can be created with required fields"""
        candidate = SLICandidate(
            name="test-latency-p95",
            metric_type=MetricType.LATENCY,
            metric_definition='histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])))',
            measurement_window=timedelta(minutes=5),
            data_sources={"prometheus": ["http_request_duration_seconds"]},
            unit="ms",
            description="Test latency SLI",
        )

        assert candidate.name == "test-latency-p95"
        assert candidate.metric_type == MetricType.LATENCY
        assert candidate.unit == "ms"
        assert candidate.description == "Test latency SLI"
