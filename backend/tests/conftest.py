"""
Pytest fixtures for contract and integration tests
"""
import pytest
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from uuid import uuid4
from datetime import datetime

from src.models.base import Base
from src.api.deps import get_db


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create an in-memory SQLite database for testing

    Each test gets a fresh database session
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Only import models here to avoid early loading
    from src.models import service, user_journey, sli, slo, artifact

    # Create all tables
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        # Ignore SQLite-specific constraint errors
        print(f"Warning: Some constraints may not be supported in SQLite: {e}")

    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create session
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        try:
            Base.metadata.drop_all(bind=engine)
        except:
            pass


@pytest.fixture
async def async_client(test_db: Session) -> AsyncGenerator[AsyncClient, None]:
    """
    Async HTTP client for testing FastAPI endpoints

    Will import app once it's implemented in src.main:app
    For now, this will cause tests to fail (TDD requirement)
    """
    try:
        from src.main import app

        # Override database dependency
        def override_get_db():
            try:
                yield test_db
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            yield client

        # Clear overrides
        app.dependency_overrides.clear()

    except ImportError:
        # App not implemented yet - tests should fail
        pytest.fail("FastAPI app not implemented yet (src.main:app)")


@pytest.fixture
def sample_service(test_db: Session):
    """Create a sample service in the database"""
    from src.models.service import Service

    service = Service(
        service_id=uuid4(),
        name="payments-api",
        environment="prod",
        owner_team="payments-squad",
        telemetry_endpoints={
            "prometheus_url": "http://prometheus:9090",
            "otlp_endpoint": "grpc://otel-collector:4317"
        },
        status="active",
        organization_id=uuid4(),  # Added organization_id
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    test_db.add(service)
    test_db.commit()
    test_db.refresh(service)
    return service


@pytest.fixture
def sample_service_data():
    """Sample service registration data"""
    return {
        "service_name": "payments-api",
        "environment": "prod",
        "owner_team": "payments-squad",
        "telemetry_endpoints": {
            "prometheus_url": "http://prometheus:9090",
            "otlp_endpoint": "grpc://otel-collector:4317"
        }
    }


@pytest.fixture
def sample_user_journey(test_db: Session, sample_service):
    """Create a sample user journey in the database"""
    from src.models.user_journey import UserJourney

    journey = UserJourney(
        journey_id=uuid4(),
        service_id=sample_service.service_id,
        name="checkout-flow",
        entry_point="/api/cart",
        exit_point="/api/payment/confirm",
        step_sequence={
            "steps": [
                {"service": "payments-api", "endpoint": "/api/cart"},
                {"service": "payments-api", "endpoint": "/api/checkout"},
                {"service": "payments-api", "endpoint": "/api/payment/confirm"}
            ]
        },
        confidence_score=85.5,
        sample_trace_ids=["trace-123", "trace-456"],
        discovered_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow()
    )
    test_db.add(journey)
    test_db.commit()
    test_db.refresh(journey)
    return journey


@pytest.fixture
def sample_sli(test_db: Session, sample_user_journey):
    """Create a sample SLI in the database"""
    from src.models.sli import SLI

    sli = SLI(
        sli_id=uuid4(),
        journey_id=sample_user_journey.journey_id,
        name="checkout-latency-p95",
        metric_type="latency",
        metric_definition='histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{endpoint="/checkout"}[5m]))',
        measurement_window="5m",
        confidence_score=87.5,
        evidence_pointers={
            "capsules": ["capsule-1", "capsule-2"],
            "traces": ["trace-123", "trace-456"]
        },
        current_value=185.0,
        unit="ms",
        approved_by=None,
        approved_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    test_db.add(sli)
    test_db.commit()
    test_db.refresh(sli)
    return sli


@pytest.fixture
def sample_sli_data():
    """Sample SLI data"""
    return {
        "name": "checkout-latency-p95",
        "metric_type": "latency",
        "metric_definition": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{endpoint='/checkout'}[5m]))",
        "measurement_window": "5m",
        "unit": "ms",
        "confidence_score": 87.5
    }


@pytest.fixture
def sample_slo(test_db: Session, sample_sli):
    """Create a sample SLO in the database"""
    from src.models.slo import SLO

    slo = SLO(
        slo_id=uuid4(),
        sli_id=sample_sli.sli_id,
        threshold_value=200.0,
        comparison_operator="lt",
        time_window="30d",
        target_percentage=99.9,
        severity="critical",
        variant="conservative",
        error_budget_remaining=100.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    test_db.add(slo)
    test_db.commit()
    test_db.refresh(slo)
    return slo


@pytest.fixture
def sample_slo_data():
    """Sample SLO data"""
    return {
        "threshold_value": 200,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical",
        "variant": "conservative"
    }


@pytest.fixture
def sample_artifact(test_db: Session, sample_slo):
    """Create a sample artifact in the database"""
    from src.models.artifact import Artifact

    artifact = Artifact(
        artifact_id=uuid4(),
        slo_id=sample_slo.slo_id,
        artifact_type="prometheus_alert",
        content="""
groups:
  - name: slo_alerts
    rules:
      - alert: CheckoutLatencyHigh
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{endpoint="/checkout"}[5m])) > 0.2
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Checkout latency is high"
""",
        validation_status="passed",
        approval_status="pending",
        deployment_status="pending",
        version=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    test_db.add(artifact)
    test_db.commit()
    test_db.refresh(artifact)
    return artifact
