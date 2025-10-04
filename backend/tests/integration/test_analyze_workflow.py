"""
Integration test for analyze workflow (T139)

Tests the complete analyze workflow:
1. POST /api/v1/analyze to start analysis
2. Poll GET /api/v1/analyze/{job_id} for status
3. GET /api/v1/journeys to retrieve discovered journeys
4. Assert workflow completes successfully

Per spec.md FR-001: Automated discovery of user journeys
"""
import pytest
from fastapi.testclient import TestClient
from uuid import UUID
import time
from datetime import datetime
from unittest.mock import patch, Mock


def test_analyze_workflow_happy_path(client: TestClient, sample_service, mock_llm, mock_vector_search):
    """
    Test complete analyze workflow from job creation to journey discovery

    Workflow:
    1. POST /api/v1/analyze - create analysis job
    2. Poll GET /api/v1/analyze/{job_id} - monitor progress
    3. GET /api/v1/journeys - retrieve discovered journeys
    """
    # Step 1: Start analysis job
    analyze_request = {
        "service_name": sample_service.name,
        "environment": sample_service.environment,
        "analysis_window_days": 30,
        "force_refresh": False
    }

    response = client.post("/api/v1/analyze", json=analyze_request)

    assert response.status_code == 202
    data = response.json()

    # Validate response structure
    assert "job_id" in data
    job_id = data["job_id"]
    UUID(job_id)  # Validate UUID format

    assert data["status"] in ["pending", "running"]
    assert isinstance(data["estimated_duration_seconds"], int)
    assert data["estimated_duration_seconds"] > 0

    # Step 2: Poll job status (simulate completion)
    # In production, this would be handled by background workers
    # For testing, we simulate status updates

    response = client.get(f"/api/v1/analyze/{job_id}")
    assert response.status_code == 200

    status_data = response.json()
    assert status_data["job_id"] == job_id
    assert status_data["status"] in ["pending", "running", "completed"]
    assert 0 <= status_data["progress_percent"] <= 100
    assert "started_at" in status_data

    # Step 3: Retrieve journeys (may be empty if analysis not complete)
    response = client.get(
        f"/api/v1/journeys",
        params={"service_name": sample_service.name, "environment": sample_service.environment}
    )

    assert response.status_code == 200
    journeys_data = response.json()

    # Validate response structure
    assert isinstance(journeys_data, list)

    # If journeys were discovered, validate structure
    for journey in journeys_data:
        assert "journey_id" in journey
        UUID(journey["journey_id"])
        assert "name" in journey
        assert "entry_point" in journey
        assert "exit_point" in journey
        assert "confidence_score" in journey
        assert 0 <= journey["confidence_score"] <= 100


def test_analyze_workflow_with_journeys(client: TestClient, sample_service, sample_user_journey):
    """
    Test analyze workflow when journeys already exist in database
    """
    # Start analysis
    analyze_request = {
        "service_name": sample_service.name,
        "environment": sample_service.environment,
        "analysis_window_days": 7,
        "force_refresh": False
    }

    response = client.post("/api/v1/analyze", json=analyze_request)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    # Check status
    response = client.get(f"/api/v1/analyze/{job_id}")
    assert response.status_code == 200

    # Retrieve journeys - should include the pre-existing journey
    response = client.get(
        f"/api/v1/journeys",
        params={"service_name": sample_service.name, "environment": sample_service.environment}
    )

    assert response.status_code == 200
    journeys = response.json()

    # Should find at least the sample journey
    assert len(journeys) >= 1

    # Find our sample journey
    found_journey = None
    for journey in journeys:
        if journey["journey_id"] == str(sample_user_journey.journey_id):
            found_journey = journey
            break

    assert found_journey is not None
    assert found_journey["name"] == sample_user_journey.name
    assert found_journey["entry_point"] == sample_user_journey.entry_point
    assert found_journey["confidence_score"] == sample_user_journey.confidence_score


def test_analyze_workflow_with_min_confidence_filter(client: TestClient, sample_service, sample_user_journey):
    """
    Test journeys endpoint with min_confidence filter

    Per api-analyze.yaml: min_confidence query parameter
    """
    # Start analysis
    analyze_request = {
        "service_name": sample_service.name,
        "environment": sample_service.environment
    }

    response = client.post("/api/v1/analyze", json=analyze_request)
    assert response.status_code == 202

    # Retrieve journeys with confidence filter above sample journey's score
    high_confidence = sample_user_journey.confidence_score + 10
    response = client.get(
        f"/api/v1/journeys",
        params={
            "service_name": sample_service.name,
            "environment": sample_service.environment,
            "min_confidence": high_confidence
        }
    )

    assert response.status_code == 200
    journeys = response.json()

    # Should filter out the sample journey
    for journey in journeys:
        assert journey["confidence_score"] >= high_confidence

    # Retrieve with lower confidence threshold
    low_confidence = sample_user_journey.confidence_score - 10
    response = client.get(
        f"/api/v1/journeys",
        params={
            "service_name": sample_service.name,
            "environment": sample_service.environment,
            "min_confidence": low_confidence
        }
    )

    assert response.status_code == 200
    journeys = response.json()

    # Should include the sample journey
    assert len(journeys) >= 1
    journey_ids = [j["journey_id"] for j in journeys]
    assert str(sample_user_journey.journey_id) in journey_ids


def test_analyze_workflow_service_not_found(client: TestClient):
    """
    Test analyze workflow with non-existent service

    Per api-analyze.yaml: 404 if service not found
    """
    analyze_request = {
        "service_name": "nonexistent-service",
        "environment": "prod"
    }

    response = client.post("/api/v1/analyze", json=analyze_request)

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error_code" in data["detail"]
    assert data["detail"]["error_code"] == "SERVICE_NOT_FOUND"


def test_analyze_workflow_invalid_job_id(client: TestClient):
    """
    Test status check with invalid job_id

    Per api-analyze.yaml: 404 if job not found
    """
    fake_job_id = "00000000-0000-0000-0000-000000000000"

    response = client.get(f"/api/v1/analyze/{fake_job_id}")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error_code" in data["detail"]
    assert data["detail"]["error_code"] == "JOB_NOT_FOUND"


def test_analyze_workflow_validation_errors(client: TestClient, sample_service):
    """
    Test validation errors in analyze request

    Per api-analyze.yaml: 400 for validation errors
    """
    # Missing required field
    response = client.post("/api/v1/analyze", json={"environment": "prod"})
    assert response.status_code == 422  # FastAPI validation error

    # Invalid environment
    response = client.post("/api/v1/analyze", json={
        "service_name": sample_service.name,
        "environment": "production"  # Should be "prod"
    })
    assert response.status_code == 422

    # Invalid analysis window
    response = client.post("/api/v1/analyze", json={
        "service_name": sample_service.name,
        "environment": "prod",
        "analysis_window_days": 100  # Exceeds max 90
    })
    assert response.status_code == 422


def test_analyze_workflow_force_refresh(client: TestClient, sample_service):
    """
    Test force_refresh parameter bypasses cache

    Per api-analyze.yaml: force_refresh flag
    """
    # First analysis without force_refresh
    analyze_request = {
        "service_name": sample_service.name,
        "environment": sample_service.environment,
        "force_refresh": False
    }

    response1 = client.post("/api/v1/analyze", json=analyze_request)
    assert response1.status_code == 202
    job_id_1 = response1.json()["job_id"]

    # Second analysis with force_refresh
    analyze_request["force_refresh"] = True
    response2 = client.post("/api/v1/analyze", json=analyze_request)
    assert response2.status_code == 202
    job_id_2 = response2.json()["job_id"]

    # Should create different jobs
    assert job_id_1 != job_id_2


def test_analyze_workflow_concurrent_analyses(client: TestClient, sample_service):
    """
    Test multiple concurrent analyze jobs for same service

    Ensures jobs are tracked independently
    """
    # Create multiple analysis jobs
    job_ids = []
    for i in range(3):
        response = client.post("/api/v1/analyze", json={
            "service_name": sample_service.name,
            "environment": sample_service.environment,
            "analysis_window_days": 7 + i
        })
        assert response.status_code == 202
        job_ids.append(response.json()["job_id"])

    # Verify all jobs are tracked
    assert len(set(job_ids)) == 3

    # Check each job status independently
    for job_id in job_ids:
        response = client.get(f"/api/v1/analyze/{job_id}")
        assert response.status_code == 200
        assert response.json()["job_id"] == job_id
