"""
Integration test for SLI/SLO workflow (T140)

Tests the complete SLI/SLO workflow:
1. GET /api/v1/sli to retrieve SLI recommendations
2. PATCH /api/v1/sli/{id} to approve SLI
3. POST /api/v1/slo to create SLO from approved SLI
4. POST /api/v1/slo/{id}/simulate to run backtest simulation
5. Assert simulation results are correct

Per spec.md FR-002, FR-003, FR-010
"""
import pytest
from fastapi.testclient import TestClient
from uuid import UUID, uuid4
from datetime import datetime


def test_sli_slo_workflow_happy_path(
    client: TestClient,
    sample_service,
    sample_user_journey,
    sample_sli,
    mock_prometheus
):
    """
    Test complete SLI/SLO workflow from retrieval to simulation

    Workflow:
    1. GET /api/v1/sli - retrieve SLI recommendations
    2. PATCH /api/v1/sli/{id} - approve SLI
    3. POST /api/v1/slo - create SLO
    4. POST /api/v1/slo/{id}/simulate - run backtest
    """
    # Step 1: Retrieve SLI recommendations
    response = client.get(
        "/api/v1/sli",
        params={"journey_id": str(sample_user_journey.journey_id)}
    )

    assert response.status_code == 200
    slis = response.json()

    # Should find at least the sample SLI
    assert isinstance(slis, list)
    assert len(slis) >= 1

    # Find our sample SLI
    sli = None
    for s in slis:
        if s["sli_id"] == str(sample_sli.sli_id):
            sli = s
            break

    assert sli is not None
    assert sli["name"] == sample_sli.name
    assert sli["metric_type"] == sample_sli.metric_type
    assert sli["confidence_score"] == sample_sli.confidence_score

    # Step 2: Approve SLI
    sli_id = sli["sli_id"]
    approve_request = {
        "approved_by": "test-user@example.com",
        "approved": True
    }

    response = client.patch(f"/api/v1/sli/{sli_id}", json=approve_request)

    assert response.status_code == 200
    approved_sli = response.json()

    assert approved_sli["approved_by"] == "test-user@example.com"
    assert approved_sli["approved_at"] is not None

    # Step 3: Create SLO from approved SLI
    slo_request = {
        "sli_id": sli_id,
        "threshold_value": 200.0,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical",
        "variant": "conservative"
    }

    response = client.post("/api/v1/slo", json=slo_request)

    assert response.status_code == 201
    slo = response.json()

    assert "slo_id" in slo
    slo_id = slo["slo_id"]
    UUID(slo_id)

    assert slo["sli_id"] == sli_id
    assert slo["threshold_value"] == 200.0
    assert slo["comparison_operator"] == "lt"
    assert slo["target_percentage"] == 99.9

    # Step 4: Simulate SLO to estimate breaches
    simulate_request = {
        "backtest_window_days": 30,
        "lookback_start": "2024-01-01T00:00:00Z"
    }

    response = client.post(f"/api/v1/slo/{slo_id}/simulate", json=simulate_request)

    assert response.status_code == 200
    simulation = response.json()

    # Validate simulation results
    assert "simulated_breaches" in simulation
    assert isinstance(simulation["simulated_breaches"], int)
    assert simulation["simulated_breaches"] >= 0

    assert "breach_timestamps" in simulation
    assert isinstance(simulation["breach_timestamps"], list)
    assert len(simulation["breach_timestamps"]) == simulation["simulated_breaches"]

    # Validate simulation metadata
    assert "evaluation_period_days" in simulation
    assert "total_evaluations" in simulation
    assert "breach_rate_percent" in simulation


def test_sli_workflow_with_evidence(
    client: TestClient,
    sample_user_journey,
    sample_sli
):
    """
    Test SLI retrieval with evidence pointers

    Per api-sli.yaml: include_evidence parameter
    """
    # Retrieve SLIs without evidence
    response = client.get(
        "/api/v1/sli",
        params={
            "journey_id": str(sample_user_journey.journey_id),
            "include_evidence": False
        }
    )

    assert response.status_code == 200
    slis = response.json()
    assert len(slis) >= 1

    # Evidence should not be included
    for sli in slis:
        assert "evidence_pointers" not in sli or sli["evidence_pointers"] is None

    # Retrieve SLIs with evidence
    response = client.get(
        "/api/v1/sli",
        params={
            "journey_id": str(sample_user_journey.journey_id),
            "include_evidence": True
        }
    )

    assert response.status_code == 200
    slis = response.json()

    # Find SLI with evidence
    sli_with_evidence = None
    for sli in slis:
        if sli["sli_id"] == str(sample_sli.sli_id):
            sli_with_evidence = sli
            break

    assert sli_with_evidence is not None
    assert "evidence_pointers" in sli_with_evidence
    assert sli_with_evidence["evidence_pointers"] is not None


def test_sli_workflow_metric_override(
    client: TestClient,
    sample_sli
):
    """
    Test SLI approval with metric definition override

    Per api-sli.yaml: metric_definition_override optional field
    """
    # Approve SLI with metric override
    override_promql = 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{endpoint="/checkout"}[5m]))'

    approve_request = {
        "approved_by": "sre-lead@example.com",
        "approved": True,
        "metric_definition_override": override_promql
    }

    response = client.patch(
        f"/api/v1/sli/{sample_sli.sli_id}",
        json=approve_request
    )

    assert response.status_code == 200
    approved_sli = response.json()

    assert approved_sli["approved_by"] == "sre-lead@example.com"
    assert approved_sli["metric_definition"] == override_promql


def test_sli_workflow_invalid_promql(client: TestClient, sample_sli):
    """
    Test SLI approval with invalid PromQL override

    Per api-sli.yaml: should validate PromQL syntax
    """
    # Attempt to approve with invalid PromQL
    approve_request = {
        "approved_by": "test-user@example.com",
        "approved": True,
        "metric_definition_override": "invalid{promql syntax"
    }

    response = client.patch(
        f"/api/v1/sli/{sample_sli.sli_id}",
        json=approve_request
    )

    # Should return 400 for invalid PromQL
    assert response.status_code == 400
    error = response.json()
    assert "detail" in error
    assert "promql" in error["detail"]["message"].lower() or "syntax" in error["detail"]["message"].lower()


def test_slo_workflow_validation(client: TestClient, sample_sli):
    """
    Test SLO creation validation

    Per api-sli.yaml: validate threshold, comparison_operator, target_percentage
    """
    # First approve the SLI
    client.patch(
        f"/api/v1/sli/{sample_sli.sli_id}",
        json={"approved_by": "test-user@example.com", "approved": True}
    )

    # Test invalid threshold (negative)
    response = client.post("/api/v1/slo", json={
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": -100,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical"
    })
    assert response.status_code == 422  # Validation error

    # Test invalid comparison operator
    response = client.post("/api/v1/slo", json={
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 200,
        "comparison_operator": "invalid",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical"
    })
    assert response.status_code == 422

    # Test invalid target percentage (>100)
    response = client.post("/api/v1/slo", json={
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 200,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 101.0,
        "severity": "critical"
    })
    assert response.status_code == 422


def test_slo_workflow_unapproved_sli(client: TestClient, sample_sli):
    """
    Test SLO creation from unapproved SLI

    Per spec.md: Should allow creating SLO even if SLI not approved
    (approval is optional workflow)
    """
    # Attempt to create SLO without approving SLI first
    slo_request = {
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 200.0,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical"
    }

    response = client.post("/api/v1/slo", json=slo_request)

    # Should succeed (approval is optional)
    assert response.status_code == 201


def test_slo_workflow_multiple_variants(
    client: TestClient,
    sample_sli
):
    """
    Test creating multiple SLO variants from same SLI

    Per spec.md FR-004: Support multiple SLO variants (conservative/balanced/aggressive)
    """
    # Approve SLI
    client.patch(
        f"/api/v1/sli/{sample_sli.sli_id}",
        json={"approved_by": "test-user@example.com", "approved": True}
    )

    # Create conservative variant
    conservative_slo = {
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 200.0,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical",
        "variant": "conservative"
    }

    response = client.post("/api/v1/slo", json=conservative_slo)
    assert response.status_code == 201
    conservative = response.json()

    # Create balanced variant
    balanced_slo = {
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 250.0,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.0,
        "severity": "major",
        "variant": "balanced"
    }

    response = client.post("/api/v1/slo", json=balanced_slo)
    assert response.status_code == 201
    balanced = response.json()

    # Verify both SLOs created
    assert conservative["slo_id"] != balanced["slo_id"]
    assert conservative["variant"] == "conservative"
    assert balanced["variant"] == "balanced"


def test_slo_simulate_window_validation(
    client: TestClient,
    sample_slo
):
    """
    Test SLO simulation window validation

    Per api-sli.yaml: backtest_window_days should be reasonable range
    """
    # Test valid simulation
    response = client.post(
        f"/api/v1/slo/{sample_slo.slo_id}/simulate",
        json={"backtest_window_days": 30}
    )
    assert response.status_code == 200

    # Test invalid window (too large)
    response = client.post(
        f"/api/v1/slo/{sample_slo.slo_id}/simulate",
        json={"backtest_window_days": 365}
    )
    assert response.status_code == 422  # Validation error


def test_slo_simulate_nonexistent_slo(client: TestClient):
    """
    Test simulation with non-existent SLO

    Per api-sli.yaml: 404 if SLO not found
    """
    fake_slo_id = str(uuid4())

    response = client.post(
        f"/api/v1/slo/{fake_slo_id}/simulate",
        json={"backtest_window_days": 30}
    )

    assert response.status_code == 404
    error = response.json()
    assert "detail" in error


def test_slo_error_budget_calculation(
    client: TestClient,
    sample_sli,
    mock_prometheus
):
    """
    Test error budget is calculated correctly

    Per spec.md FR-005: Error budget tracking
    """
    # Create SLO
    slo_request = {
        "sli_id": str(sample_sli.sli_id),
        "threshold_value": 200.0,
        "comparison_operator": "lt",
        "time_window": "30d",
        "target_percentage": 99.9,
        "severity": "critical"
    }

    response = client.post("/api/v1/slo", json=slo_request)
    assert response.status_code == 201
    slo = response.json()

    # Error budget should be initialized
    assert "error_budget_remaining" in slo
    assert isinstance(slo["error_budget_remaining"], (int, float))

    # Simulate to see error budget impact
    response = client.post(
        f"/api/v1/slo/{slo['slo_id']}/simulate",
        json={"backtest_window_days": 30}
    )

    assert response.status_code == 200
    simulation = response.json()

    # Should include error budget information
    if "error_budget_consumed_percent" in simulation:
        assert 0 <= simulation["error_budget_consumed_percent"] <= 100
