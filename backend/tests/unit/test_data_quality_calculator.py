"""
Unit tests for Data Quality Calculator Service

Tests T092a: Data quality calculation and metrics export
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch, Mock

from src.services.data_quality_calculator import (
    DataQualityCalculator,
    DataQualityMetrics,
)
from src.models.service import Service, Environment
from src.models.capsule import Capsule


class TestDataQualityCalculator:
    """Test data quality metric calculation"""

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
    def high_quality_capsules(self, db_session, sample_service):
        """Create capsules representing high-quality telemetry"""
        capsules = []
        start_time = datetime.utcnow() - timedelta(days=7)

        for hour in range(168):  # 7 days * 24 hours
            capsule = Capsule(
                capsule_id=uuid4(),
                fingerprint_hash=f"hash-{hour}",
                template="User {{USER_ID}} completed action",
                count=100,
                severity_distribution={"INFO": 90, "WARN": 10},
                sample_array=[
                    {
                        "message": "User 123 completed action",
                        "trace_id": f"trace-{hour}",
                        "span_id": f"span-{hour}",
                        "user_id": "user123",
                        "session_id": f"session-{hour}",
                        "request_id": f"req-{hour}",
                        "timestamp": "2024-01-01T10:00:00Z",
                        "level": "INFO",
                    }
                ],
                service_id=sample_service.service_id,
                first_seen_at=start_time + timedelta(hours=hour),
                last_seen_at=start_time + timedelta(hours=hour),
                time_bucket=start_time + timedelta(hours=hour),
                redaction_applied=True,
            )
            capsules.append(capsule)
            db_session.add(capsule)

        db_session.commit()
        return capsules

    @pytest.fixture
    def low_quality_capsules(self, db_session, sample_service):
        """Create capsules representing low-quality telemetry"""
        capsules = []
        start_time = datetime.utcnow() - timedelta(days=7)

        for i in range(10):  # Sparse data
            capsule = Capsule(
                capsule_id=uuid4(),
                fingerprint_hash=f"hash-low-{i}",
                template="Unstructured log message",
                count=50,
                severity_distribution={"INFO": 100},
                sample_array=[
                    {
                        "message": "Unstructured log message",
                        # Missing: trace_id, user_id, session_id, request_id
                    }
                ],
                service_id=sample_service.service_id,
                first_seen_at=start_time + timedelta(days=i),
                last_seen_at=start_time + timedelta(days=i),
                time_bucket=start_time + timedelta(days=i),
                redaction_applied=False,
            )
            capsules.append(capsule)
            db_session.add(capsule)

        db_session.commit()
        return capsules

    @pytest.fixture
    def calculator(self, db_session):
        """Create data quality calculator instance"""
        return DataQualityCalculator(db_session)

    def test_calculate_for_service_high_quality(
        self, calculator, sample_service, high_quality_capsules
    ):
        """Test calculation for service with high-quality telemetry"""
        metrics = calculator.calculate_for_service(sample_service.service_id)

        assert metrics.service_id == sample_service.service_id
        assert metrics.service_name == "test-service"
        assert metrics.environment == "production"

        # High quality data should yield high percentages
        assert metrics.rum_coverage_pct > Decimal("90.0")
        assert metrics.trace_coverage_pct > Decimal("90.0")
        assert metrics.structured_log_pct > Decimal("90.0")
        assert metrics.request_id_presence_pct > Decimal("90.0")

    def test_calculate_for_service_low_quality(
        self, calculator, sample_service, low_quality_capsules
    ):
        """Test calculation for service with low-quality telemetry"""
        metrics = calculator.calculate_for_service(sample_service.service_id)

        # Low quality data should yield low percentages
        assert metrics.rum_coverage_pct < Decimal("10.0")
        assert metrics.trace_coverage_pct < Decimal("10.0")

    def test_calculate_rum_coverage(self, calculator, high_quality_capsules):
        """Test RUM coverage calculation"""
        coverage = calculator._calculate_rum_coverage(high_quality_capsules)

        # All high-quality capsules have user_id and session_id
        assert coverage == Decimal("100.0")

    def test_calculate_rum_coverage_partial(self, calculator, db_session, sample_service):
        """Test RUM coverage with partial data"""
        capsules = [
            Capsule(
                capsule_id=uuid4(),
                fingerprint_hash="hash-1",
                template="Test",
                count=100,
                severity_distribution={"INFO": 100},
                sample_array=[{"user_id": "user123"}],  # Has RUM
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow(),
                redaction_applied=True,
            ),
            Capsule(
                capsule_id=uuid4(),
                fingerprint_hash="hash-2",
                template="Test",
                count=100,
                severity_distribution={"INFO": 100},
                sample_array=[{"message": "test"}],  # No RUM
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow(),
                redaction_applied=True,
            ),
        ]
        db_session.add_all(capsules)
        db_session.commit()

        coverage = calculator._calculate_rum_coverage(capsules)

        # 1 of 2 capsules has RUM
        assert coverage == Decimal("50.0")

    def test_calculate_trace_coverage(self, calculator, high_quality_capsules):
        """Test trace coverage calculation"""
        coverage = calculator._calculate_trace_coverage(high_quality_capsules)

        # All high-quality capsules have trace_id
        assert coverage == Decimal("100.0")

    def test_calculate_trace_coverage_with_span_id_only(self, calculator, db_session, sample_service):
        """Test trace coverage counts span_id even without trace_id"""
        capsule = Capsule(
            capsule_id=uuid4(),
            fingerprint_hash="hash-span",
            template="Test",
            count=100,
            severity_distribution={"INFO": 100},
            sample_array=[{"span_id": "span-123"}],  # Has span_id but no trace_id
            service_id=sample_service.service_id,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            time_bucket=datetime.utcnow(),
            redaction_applied=True,
        )
        db_session.add(capsule)
        db_session.commit()

        coverage = calculator._calculate_trace_coverage([capsule])

        assert coverage == Decimal("100.0")

    def test_calculate_structured_log_percentage(self, calculator, high_quality_capsules):
        """Test structured log percentage calculation"""
        percentage = calculator._calculate_structured_log_percentage(high_quality_capsules)

        # All samples are structured dicts with multiple fields
        assert percentage > Decimal("90.0")

    def test_calculate_structured_log_unstructured_data(self, calculator, db_session, sample_service):
        """Test structured log calculation with unstructured data"""
        capsules = [
            # Structured: 3+ fields
            Capsule(
                capsule_id=uuid4(),
                fingerprint_hash="hash-struct",
                template="Test",
                count=100,
                severity_distribution={"INFO": 100},
                sample_array=[{"timestamp": "...", "level": "INFO", "message": "test"}],
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow(),
                redaction_applied=True,
            ),
            # Unstructured: < 3 fields
            Capsule(
                capsule_id=uuid4(),
                fingerprint_hash="hash-unstruct",
                template="Test",
                count=100,
                severity_distribution={"INFO": 100},
                sample_array=[{"message": "plain text log"}],
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow(),
                redaction_applied=True,
            ),
        ]
        db_session.add_all(capsules)
        db_session.commit()

        percentage = calculator._calculate_structured_log_percentage(capsules)

        # 1 of 2 samples is structured
        assert percentage == Decimal("50.0")

    def test_calculate_request_id_percentage(self, calculator, high_quality_capsules):
        """Test request_id presence calculation"""
        percentage = calculator._calculate_request_id_percentage(high_quality_capsules)

        # All high-quality capsules have request_id
        assert percentage == Decimal("100.0")

    def test_calculate_request_id_variants(self, calculator, db_session, sample_service):
        """Test request_id calculation recognizes different field names"""
        capsules = []
        variants = ["request_id", "requestId", "req_id", "correlation_id"]

        for variant in variants:
            capsule = Capsule(
                capsule_id=uuid4(),
                fingerprint_hash=f"hash-{variant}",
                template="Test",
                count=100,
                severity_distribution={"INFO": 100},
                sample_array=[{variant: "123456"}],
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow(),
                redaction_applied=True,
            )
            capsules.append(capsule)
            db_session.add(capsule)

        db_session.commit()

        percentage = calculator._calculate_request_id_percentage(capsules)

        # All variants should be recognized
        assert percentage == Decimal("100.0")

    def test_service_not_found_raises_error(self, calculator):
        """Test calculation for non-existent service raises error"""
        fake_service_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            calculator.calculate_for_service(fake_service_id)

    def test_empty_metrics_for_no_data(self, calculator, sample_service):
        """Test service with no capsules returns zero metrics"""
        metrics = calculator.calculate_for_service(sample_service.service_id)

        assert metrics.total_samples == 0
        assert metrics.rum_coverage_pct == Decimal("0")
        assert metrics.trace_coverage_pct == Decimal("0")
        assert metrics.structured_log_pct == Decimal("0")
        assert metrics.request_id_presence_pct == Decimal("0")

    def test_export_metrics_to_prometheus(self, calculator):
        """Test Prometheus metrics export"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("85.5"),
            trace_coverage_pct=Decimal("92.0"),
            structured_log_pct=Decimal("78.5"),
            request_id_presence_pct=Decimal("88.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        # Should not raise
        calculator.export_metrics_to_prometheus(metrics)

        # Verify metrics can be exported (integration with prometheus_client)
        # In production, these would be scraped by Prometheus

    def test_calculate_all_services(self, calculator, sample_service, high_quality_capsules):
        """Test calculating quality for all active services"""
        all_metrics = calculator.calculate_all_services()

        assert len(all_metrics) >= 1

        # Find our test service
        test_metrics = [m for m in all_metrics if m.service_id == sample_service.service_id]
        assert len(test_metrics) == 1

    def test_calculate_all_services_skips_inactive(self, calculator, db_session):
        """Test calculation skips inactive services"""
        inactive_service = Service(
            service_id=uuid4(),
            name="inactive-service",
            environment=Environment.PRODUCTION,
            owner_team="test-team",
            telemetry_endpoints={},
            status="archived",  # Not active
        )
        db_session.add(inactive_service)
        db_session.commit()

        all_metrics = calculator.calculate_all_services()

        # Should not include inactive service
        inactive_metrics = [m for m in all_metrics if m.service_id == inactive_service.service_id]
        assert len(inactive_metrics) == 0

    def test_identify_quality_gaps_rum_coverage(self, calculator):
        """Test quality gap identification for RUM coverage"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("20.0"),  # Below MIN_RUM_COVERAGE (50%)
            trace_coverage_pct=Decimal("90.0"),
            structured_log_pct=Decimal("80.0"),
            request_id_presence_pct=Decimal("85.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        gaps = calculator.identify_quality_gaps(metrics)

        rum_gaps = [g for g in gaps if g['recommendation_type'] == 'enable_rum']
        assert len(rum_gaps) == 1
        assert rum_gaps[0]['current_value'] == 20.0
        assert rum_gaps[0]['threshold'] == 50.0

    def test_identify_quality_gaps_trace_coverage(self, calculator):
        """Test quality gap identification for trace coverage"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("60.0"),
            trace_coverage_pct=Decimal("2.0"),  # Below MIN_TRACE_COVERAGE (5%)
            structured_log_pct=Decimal("80.0"),
            request_id_presence_pct=Decimal("85.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        gaps = calculator.identify_quality_gaps(metrics)

        trace_gaps = [g for g in gaps if g['recommendation_type'] == 'add_tracing']
        assert len(trace_gaps) == 1
        assert trace_gaps[0]['severity'] == 'critical'  # Traces are essential

    def test_identify_quality_gaps_structured_logs(self, calculator):
        """Test quality gap identification for structured logging"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("60.0"),
            trace_coverage_pct=Decimal("90.0"),
            structured_log_pct=Decimal("40.0"),  # Below MIN_STRUCTURED_LOG (70%)
            request_id_presence_pct=Decimal("85.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        gaps = calculator.identify_quality_gaps(metrics)

        log_gaps = [g for g in gaps if g['recommendation_type'] == 'add_structured_logging']
        assert len(log_gaps) == 1

    def test_identify_quality_gaps_request_id(self, calculator):
        """Test quality gap identification for request_id"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("60.0"),
            trace_coverage_pct=Decimal("90.0"),
            structured_log_pct=Decimal("80.0"),
            request_id_presence_pct=Decimal("50.0"),  # Below MIN_REQUEST_ID (80%)
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        gaps = calculator.identify_quality_gaps(metrics)

        req_id_gaps = [g for g in gaps if g['recommendation_type'] == 'add_request_id']
        assert len(req_id_gaps) == 1

    def test_identify_quality_gaps_no_gaps(self, calculator):
        """Test no gaps identified for high-quality service"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("95.0"),
            trace_coverage_pct=Decimal("98.0"),
            structured_log_pct=Decimal("92.0"),
            request_id_presence_pct=Decimal("96.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        gaps = calculator.identify_quality_gaps(metrics)

        assert len(gaps) == 0

    def test_quality_thresholds_constants(self, calculator):
        """Test quality threshold constants per FR-018"""
        assert calculator.MIN_RUM_COVERAGE == 50.0
        assert calculator.MIN_TRACE_COVERAGE == 5.0
        assert calculator.MIN_STRUCTURED_LOG == 70.0
        assert calculator.MIN_REQUEST_ID == 80.0

    def test_default_lookback_days(self, calculator):
        """Test default lookback window is 7 days"""
        assert calculator.DEFAULT_LOOKBACK_DAYS == 7


class TestDataQualityMetrics:
    """Test DataQualityMetrics data class"""

    def test_to_dict(self):
        """Test conversion to dictionary for API responses"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("85.5"),
            trace_coverage_pct=Decimal("92.0"),
            structured_log_pct=Decimal("78.5"),
            request_id_presence_pct=Decimal("88.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        result = metrics.to_dict()

        assert result['service_name'] == "test-service"
        assert result['environment'] == "production"
        assert result['rum_coverage_pct'] == 85.5
        assert result['trace_coverage_pct'] == 92.0
        assert result['total_samples'] == 1000
        assert 'overall_quality_score' in result

    def test_overall_quality_score_calculation(self):
        """Test overall quality score is weighted average"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("80.0"),
            trace_coverage_pct=Decimal("90.0"),
            structured_log_pct=Decimal("70.0"),
            request_id_presence_pct=Decimal("85.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        # Weighted: 30% RUM + 35% trace + 20% structured + 15% request_id
        expected = 80.0 * 0.30 + 90.0 * 0.35 + 70.0 * 0.20 + 85.0 * 0.15

        result = metrics.to_dict()
        assert result['overall_quality_score'] == pytest.approx(expected, rel=0.01)

    def test_overall_quality_score_range(self):
        """Test overall score is within 0-100 range"""
        metrics = DataQualityMetrics(
            service_id=uuid4(),
            service_name="test-service",
            environment="production",
            rum_coverage_pct=Decimal("100.0"),
            trace_coverage_pct=Decimal("100.0"),
            structured_log_pct=Decimal("100.0"),
            request_id_presence_pct=Decimal("100.0"),
            calculated_at=datetime.utcnow(),
            total_samples=1000,
        )

        score = metrics._calculate_overall_score()
        assert 0.0 <= score <= 100.0
