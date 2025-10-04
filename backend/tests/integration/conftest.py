"""
Integration test fixtures for workflow testing

Provides TestClient with mocked external dependencies
"""
import pytest
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from uuid import uuid4
from datetime import datetime, timedelta

from src.main import app
from src.models.base import Base
from src.api.deps import get_db


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Create an in-memory SQLite database for integration testing

    Each test gets a fresh database session
    """
    # Create in-memory SQLite database
    engine = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False}
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Create session factory
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create session
    session = SessionLocal()

    try:
        yield session
    finally:
        session.rollback()
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(test_db: Session) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with database dependency override
    """
    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


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


@pytest.fixture
def mock_prometheus():
    """Mock Prometheus API for SLO simulation"""
    with patch('src.validators.dryrun_evaluator.PrometheusClient') as mock:
        mock_instance = Mock()
        mock_instance.query_range.return_value = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {},
                        "values": [
                            [1609459200, "150"],  # Below threshold
                            [1609545600, "180"],  # Below threshold
                            [1609632000, "250"],  # Above threshold - breach!
                            [1609718400, "190"],  # Below threshold
                        ]
                    }
                ]
            }
        }
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_github():
    """Mock GitHub client for PR creation"""
    with patch('src.integrations.github_client.GitHubClient') as mock:
        mock_instance = Mock()
        mock_instance.create_pull_request = Mock(
            return_value={
                "url": "https://github.com/org/repo/pull/123",
                "number": 123,
                "branch": "slo-scout/add-checkout-latency-slo"
            }
        )
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_llm():
    """Mock LLM client for journey discovery"""
    with patch('src.services.llm_client.LLMClient') as mock:
        mock_instance = Mock()
        mock_instance.generate_completion = Mock(
            return_value={
                "journeys": [
                    {
                        "name": "checkout-flow",
                        "entry_point": "/api/cart",
                        "exit_point": "/api/payment/confirm",
                        "confidence": 85.5
                    }
                ],
                "slis": [
                    {
                        "name": "checkout-latency-p95",
                        "metric_type": "latency",
                        "metric_definition": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
                    }
                ]
            }
        )
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_vector_search():
    """Mock vector search for evidence linking"""
    with patch('src.services.vector_search.VectorSearchService') as mock:
        mock_instance = Mock()
        mock_instance.search_similar = Mock(
            return_value=[
                {"capsule_id": "capsule-1", "similarity": 0.92},
                {"capsule_id": "capsule-2", "similarity": 0.85}
            ]
        )
        mock.return_value = mock_instance
        yield mock_instance
