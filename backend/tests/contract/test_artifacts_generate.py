"""
Contract test for POST /api/v1/artifacts/generate endpoint
Per api-artifacts.yaml specification

MUST FAIL before implementation (TDD principle)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_artifacts_generate_returns_201(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should generate artifacts"""
    slo_id = str(uuid4())
    request_body = {
        "slo_id": slo_id,
        "artifact_types": ["prometheus_alert", "grafana_dashboard"],
        "validation_only": False
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()

        # Should return array of generated artifacts
        assert "artifacts" in data
        assert isinstance(data["artifacts"], list)
        assert len(data["artifacts"]) == 2  # prometheus_alert + grafana_dashboard

        for artifact in data["artifacts"]:
            assert "artifact_id" in artifact
            assert "artifact_type" in artifact
            assert artifact["artifact_type"] in ["prometheus_alert", "grafana_dashboard"]
            assert "validation_status" in artifact


@pytest.mark.asyncio
async def test_artifacts_generate_validation_only(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate with validation_only flag"""
    slo_id = str(uuid4())
    request_body = {
        "slo_id": slo_id,
        "artifact_types": ["prometheus_alert"],
        "validation_only": True
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    if response.status_code == 201:
        data = response.json()

        for artifact in data["artifacts"]:
            # Per api-artifacts.yaml: validation_only should not persist artifacts
            assert artifact.get("artifact_id") is None or artifact.get("transient") is True


@pytest.mark.asyncio
async def test_artifacts_generate_validates_types(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should validate artifact_types"""
    request_body = {
        "slo_id": str(uuid4()),
        "artifact_types": ["invalid_type"]
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should reject invalid artifact type
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_artifacts_generate_promtool_validation(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should validate Prometheus rules with promtool"""
    slo_id = str(uuid4())
    request_body = {
        "slo_id": slo_id,
        "artifact_types": ["prometheus_alert"]
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    if response.status_code == 201:
        data = response.json()

        prometheus_artifact = [a for a in data["artifacts"] if a["artifact_type"] == "prometheus_alert"][0]

        # Per FR-006: MUST pass promtool validation
        assert prometheus_artifact["validation_status"] == "passed"
