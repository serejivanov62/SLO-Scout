"""
Unit tests for SLI model

Tests SLI model constraints:
- Approval workflow (approved=True requires approved_by+approved_at)
- Confidence score range (0.0-1.0)
- Foreign key relationships
- Nullable/non-nullable fields
- CHECK constraints
"""
import pytest
from uuid import uuid4
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from decimal import Decimal

from src.models.sli import SLI
from src.models.user_journey import UserJourney
from src.models.service import Service, ServiceStatusEnum, EnvironmentEnum


class TestSLIModelConstraints:
    """Test SLI model CHECK constraints and validations"""

    def test_sli_creation_with_valid_data(self, test_db):
        """Test creating an SLI with all valid fields"""
        # Create parent service and user journey first
        service = Service(
            name="test-service",
            environment=EnvironmentEnum.PROD,
            owner_team="test-team",
            telemetry_endpoints={"prometheus_url": "http://test"},
            label_mappings={"prometheus": {}}
        )
        test_db.add(service)
        test_db.commit()

        journey = UserJourney(
            service_id=service.id,
            name="checkout-flow",
            entry_point="/api/cart",
            critical_path=True,
            confidence_score=Decimal("0.855")
        )
        test_db.add(journey)
        test_db.commit()

        sli = SLI(
            journey_id=journey.journey_id,
            name="checkout-latency-p95",
            description="95th percentile latency for checkout flow",
            promql_query='histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))',
            confidence_score=Decimal("0.875")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.sli_id is not None
        assert sli.name == "checkout-latency-p95"
        assert sli.confidence_score == Decimal("0.875")

    def test_confidence_score_within_range(self, test_db, sample_user_journey):
        """Test that confidence score must be between 0 and 1"""
        valid_scores = [Decimal("0.0"), Decimal("0.5"), Decimal("0.999"), Decimal("1.0")]

        for idx, score in enumerate(valid_scores):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name=f"test-sli-{idx}",
                promql_query="test_metric",
                confidence_score=score
            )
            test_db.add(sli)
            test_db.commit()
            test_db.refresh(sli)

            assert sli.confidence_score == score

    def test_confidence_score_below_range(self, test_db, sample_user_journey):
        """Test that confidence score below 0 is rejected"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query="test_metric",
                confidence_score=Decimal("-0.1")  # Should fail
            )
            test_db.add(sli)
            test_db.commit()

    def test_confidence_score_above_range(self, test_db, sample_user_journey):
        """Test that confidence score above 1 is rejected"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query="test_metric",
                confidence_score=Decimal("1.1")  # Should fail
            )
            test_db.add(sli)
            test_db.commit()


class TestSLIApprovalWorkflow:
    """Test SLI approval workflow constraints"""

    def test_unapproved_sli_defaults(self, test_db, sample_user_journey):
        """Test that unapproved SLI has approved=False by default"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved is False
        assert sli.approved_by is None
        assert sli.approved_at is None

    def test_approved_sli_requires_approved_by_and_at(self, test_db, sample_user_journey):
        """Test that approved=True requires approved_by and approved_at"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            approved=True,
            approved_by="john.doe@example.com",
            approved_at=datetime.utcnow()
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved is True
        assert sli.approved_by == "john.doe@example.com"
        assert sli.approved_at is not None

    def test_approved_without_approved_by_fails(self, test_db, sample_user_journey):
        """Test that approved=True without approved_by fails"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query="test_metric",
                confidence_score=Decimal("0.85"),
                approved=True,
                approved_by=None,  # Should fail
                approved_at=datetime.utcnow()
            )
            test_db.add(sli)
            test_db.commit()

    def test_approved_without_approved_at_fails(self, test_db, sample_user_journey):
        """Test that approved=True without approved_at fails"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query="test_metric",
                confidence_score=Decimal("0.85"),
                approved=True,
                approved_by="john.doe@example.com",
                approved_at=None  # Should fail
            )
            test_db.add(sli)
            test_db.commit()

    def test_unapproved_with_approved_by_allowed(self, test_db, sample_user_journey):
        """Test that approved=False allows NULL approved_by and approved_at"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            approved=False,
            approved_by=None,
            approved_at=None
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved is False
        assert sli.approved_by is None
        assert sli.approved_at is None


class TestSLIModelDefaults:
    """Test SLI model default values"""

    def test_sli_approved_defaults_to_false(self, test_db, sample_user_journey):
        """Test that approved defaults to False"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved is False

    def test_sli_created_at_auto_set(self, test_db, sample_user_journey):
        """Test that created_at is automatically set"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.created_at is not None
        assert isinstance(sli.created_at, datetime)

    def test_sli_id_auto_generated(self, test_db, sample_user_journey):
        """Test that sli_id is auto-generated if not provided"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.sli_id is not None


class TestSLIModelNullability:
    """Test SLI model nullable and non-nullable fields"""

    def test_name_not_nullable(self, test_db, sample_user_journey):
        """Test that name cannot be NULL"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name=None,  # Should fail
                promql_query="test_metric",
                confidence_score=Decimal("0.85")
            )
            test_db.add(sli)
            test_db.commit()

    def test_promql_query_not_nullable(self, test_db, sample_user_journey):
        """Test that promql_query cannot be NULL"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query=None,  # Should fail
                confidence_score=Decimal("0.85")
            )
            test_db.add(sli)
            test_db.commit()

    def test_confidence_score_not_nullable(self, test_db, sample_user_journey):
        """Test that confidence_score cannot be NULL"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=sample_user_journey.journey_id,
                name="test-sli",
                promql_query="test_metric",
                confidence_score=None  # Should fail
            )
            test_db.add(sli)
            test_db.commit()

    def test_description_nullable(self, test_db, sample_user_journey):
        """Test that description can be NULL"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            description=None  # Should succeed
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.description is None

    def test_approved_by_nullable(self, test_db, sample_user_journey):
        """Test that approved_by can be NULL when approved=False"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            approved=False,
            approved_by=None
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved_by is None

    def test_approved_at_nullable(self, test_db, sample_user_journey):
        """Test that approved_at can be NULL when approved=False"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            approved=False,
            approved_at=None
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.approved_at is None


class TestSLIModelRelationships:
    """Test SLI model foreign key relationships"""

    def test_sli_journey_foreign_key(self, test_db, sample_user_journey):
        """Test that SLI has valid foreign key to UserJourney"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()
        test_db.refresh(sli)

        assert sli.journey_id == sample_user_journey.journey_id
        assert sli.user_journey == sample_user_journey

    def test_sli_invalid_journey_id(self, test_db):
        """Test that invalid journey_id causes foreign key error"""
        with pytest.raises(IntegrityError):
            sli = SLI(
                journey_id=uuid4(),  # Non-existent journey
                name="test-sli",
                promql_query="test_metric",
                confidence_score=Decimal("0.85")
            )
            test_db.add(sli)
            test_db.commit()

    def test_sli_slos_relationship(self, test_db, sample_user_journey):
        """Test that SLI has slos relationship"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()

        assert hasattr(sli, 'slos')
        assert sli.slos == []

    def test_sli_cascade_delete_from_journey(self, test_db, sample_user_journey):
        """Test that deleting journey cascades to SLI"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()

        sli_id = sli.sli_id

        # Delete the journey
        test_db.delete(sample_user_journey)
        test_db.commit()

        # SLI should also be deleted
        deleted_sli = test_db.query(SLI).filter_by(sli_id=sli_id).first()
        assert deleted_sli is None


class TestSLIModelStringRepresentation:
    """Test SLI model __repr__ method"""

    def test_unapproved_sli_repr(self, test_db, sample_user_journey):
        """Test string representation of unapproved SLI"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85")
        )
        test_db.add(sli)
        test_db.commit()

        repr_str = repr(sli)
        assert "test-sli" in repr_str
        assert "pending" in repr_str

    def test_approved_sli_repr(self, test_db, sample_user_journey):
        """Test string representation of approved SLI"""
        sli = SLI(
            journey_id=sample_user_journey.journey_id,
            name="test-sli",
            promql_query="test_metric",
            confidence_score=Decimal("0.85"),
            approved=True,
            approved_by="john.doe@example.com",
            approved_at=datetime.utcnow()
        )
        test_db.add(sli)
        test_db.commit()

        repr_str = repr(sli)
        assert "test-sli" in repr_str
        assert "approved" in repr_str
