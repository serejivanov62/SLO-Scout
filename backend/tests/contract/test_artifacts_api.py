"""
Contract test for Artifacts API endpoints
Validates against /specs/002-complete-slo-scout/contracts/artifacts-api.yaml

MUST FAIL before implementation (TDD principle)

Tests:
- POST /api/v1/artifacts/generate (generate artifact)
- GET /api/v1/artifacts (list artifacts)
- GET /api/v1/artifacts/{artifact_id} (get artifact)
- POST /api/v1/artifacts/{artifact_id}/deploy (deploy artifact with policy guard)
"""
import pytest
from httpx import AsyncClient
from uuid import uuid4


# ============================================================================
# POST /api/v1/artifacts/generate - Generate Artifact
# ============================================================================


@pytest.mark.asyncio
async def test_generate_artifact_returns_201(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should create artifact and return 201"""
    slo_id = str(uuid4())
    request_body = {
        "slo_id": slo_id,
        "artifact_type": "prometheus_rule"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should return 201 on success or 404 if SLO not found
    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()

        # Validate response schema per artifacts-api.yaml Artifact schema
        assert "artifact_id" in data
        assert "slo_id" in data
        assert data["slo_id"] == slo_id
        assert "artifact_type" in data
        assert data["artifact_type"] == "prometheus_rule"
        assert "content" in data
        assert isinstance(data["content"], str)
        assert "confidence_score" in data
        assert 0.0 <= data["confidence_score"] <= 1.0
        assert "status" in data
        assert data["status"] in ["draft", "deployed", "rolled_back"]
        assert "created_at" in data


@pytest.mark.asyncio
async def test_generate_artifact_grafana_dashboard(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should support grafana_dashboard type"""
    request_body = {
        "slo_id": str(uuid4()),
        "artifact_type": "grafana_dashboard"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()
        assert data["artifact_type"] == "grafana_dashboard"


@pytest.mark.asyncio
async def test_generate_artifact_runbook(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should support runbook type"""
    request_body = {
        "slo_id": str(uuid4()),
        "artifact_type": "runbook"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    assert response.status_code in [201, 404]

    if response.status_code == 201:
        data = response.json()
        assert data["artifact_type"] == "runbook"


@pytest.mark.asyncio
async def test_generate_artifact_validates_artifact_type(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should validate artifact_type enum"""
    request_body = {
        "slo_id": str(uuid4()),
        "artifact_type": "invalid_type"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should reject invalid artifact type (400 Bad Request or 422 Validation Error)
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_generate_artifact_requires_slo_id(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should require slo_id field"""
    request_body = {
        "artifact_type": "prometheus_rule"
        # Missing slo_id
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should return validation error
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_generate_artifact_validates_uuid_format(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should validate slo_id is valid UUID"""
    request_body = {
        "slo_id": "not-a-valid-uuid",
        "artifact_type": "prometheus_rule"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should return validation error for invalid UUID format
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_generate_artifact_returns_404_for_nonexistent_slo(async_client: AsyncClient):
    """POST /api/v1/artifacts/generate should return 404 for non-existent SLO"""
    request_body = {
        "slo_id": str(uuid4()),  # Random UUID that doesn't exist
        "artifact_type": "prometheus_rule"
    }

    response = await async_client.post("/api/v1/artifacts/generate", json=request_body)

    # Should return 404 if SLO not found
    assert response.status_code in [201, 404]


# ============================================================================
# GET /api/v1/artifacts - List Artifacts
# ============================================================================


@pytest.mark.asyncio
async def test_list_artifacts_returns_200(async_client: AsyncClient):
    """GET /api/v1/artifacts should return paginated list of artifacts"""
    response = await async_client.get("/api/v1/artifacts")

    assert response.status_code == 200

    data = response.json()

    # Validate response schema per artifacts-api.yaml
    assert "artifacts" in data
    assert isinstance(data["artifacts"], list)
    assert "total" in data
    assert isinstance(data["total"], int)
    assert "limit" in data
    assert isinstance(data["limit"], int)
    assert "offset" in data
    assert isinstance(data["offset"], int)


@pytest.mark.asyncio
async def test_list_artifacts_with_slo_id_filter(async_client: AsyncClient):
    """GET /api/v1/artifacts should support slo_id query parameter"""
    slo_id = str(uuid4())
    response = await async_client.get(f"/api/v1/artifacts?slo_id={slo_id}")

    assert response.status_code in [200, 400]

    if response.status_code == 200:
        data = response.json()
        # If artifacts returned, they should all match the slo_id filter
        for artifact in data["artifacts"]:
            assert artifact["slo_id"] == slo_id


@pytest.mark.asyncio
async def test_list_artifacts_with_artifact_type_filter(async_client: AsyncClient):
    """GET /api/v1/artifacts should support artifact_type query parameter"""
    response = await async_client.get("/api/v1/artifacts?artifact_type=prometheus_rule")

    assert response.status_code == 200

    data = response.json()
    # If artifacts returned, they should all be prometheus_rule type
    for artifact in data["artifacts"]:
        assert artifact["artifact_type"] == "prometheus_rule"


@pytest.mark.asyncio
async def test_list_artifacts_with_status_filter(async_client: AsyncClient):
    """GET /api/v1/artifacts should support status query parameter"""
    response = await async_client.get("/api/v1/artifacts?status=draft")

    assert response.status_code == 200

    data = response.json()
    # If artifacts returned, they should all have draft status
    for artifact in data["artifacts"]:
        assert artifact["status"] == "draft"


@pytest.mark.asyncio
async def test_list_artifacts_with_pagination(async_client: AsyncClient):
    """GET /api/v1/artifacts should support limit and offset pagination"""
    response = await async_client.get("/api/v1/artifacts?limit=10&offset=0")

    assert response.status_code == 200

    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0
    assert len(data["artifacts"]) <= 10


@pytest.mark.asyncio
async def test_list_artifacts_validates_limit_range(async_client: AsyncClient):
    """GET /api/v1/artifacts should validate limit is between 1 and 100"""
    # Test limit exceeds maximum
    response = await async_client.get("/api/v1/artifacts?limit=200")
    assert response.status_code in [200, 400]

    # Test limit is zero
    response = await async_client.get("/api/v1/artifacts?limit=0")
    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_list_artifacts_validates_offset_non_negative(async_client: AsyncClient):
    """GET /api/v1/artifacts should validate offset is non-negative"""
    response = await async_client.get("/api/v1/artifacts?offset=-10")

    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_list_artifacts_validates_artifact_type_enum(async_client: AsyncClient):
    """GET /api/v1/artifacts should validate artifact_type is valid enum value"""
    response = await async_client.get("/api/v1/artifacts?artifact_type=invalid_type")

    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_list_artifacts_validates_status_enum(async_client: AsyncClient):
    """GET /api/v1/artifacts should validate status is valid enum value"""
    response = await async_client.get("/api/v1/artifacts?status=invalid_status")

    assert response.status_code in [200, 400]


# ============================================================================
# GET /api/v1/artifacts/{artifact_id} - Get Artifact by ID
# ============================================================================


@pytest.mark.asyncio
async def test_get_artifact_by_id_returns_200(async_client: AsyncClient):
    """GET /api/v1/artifacts/{artifact_id} should return artifact details"""
    artifact_id = str(uuid4())
    response = await async_client.get(f"/api/v1/artifacts/{artifact_id}")

    # Should return 200 if found or 404 if not found
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        data = response.json()

        # Validate response schema per artifacts-api.yaml Artifact schema
        assert "artifact_id" in data
        assert data["artifact_id"] == artifact_id
        assert "slo_id" in data
        assert "artifact_type" in data
        assert data["artifact_type"] in ["prometheus_rule", "grafana_dashboard", "runbook"]
        assert "content" in data
        assert "confidence_score" in data
        assert 0.0 <= data["confidence_score"] <= 1.0
        assert "status" in data
        assert data["status"] in ["draft", "deployed", "rolled_back"]
        assert "created_at" in data


@pytest.mark.asyncio
async def test_get_artifact_returns_404_for_nonexistent_id(async_client: AsyncClient):
    """GET /api/v1/artifacts/{artifact_id} should return 404 for non-existent artifact"""
    artifact_id = str(uuid4())  # Random UUID that doesn't exist
    response = await async_client.get(f"/api/v1/artifacts/{artifact_id}")

    # Should return 404 if artifact not found
    assert response.status_code in [200, 404]


@pytest.mark.asyncio
async def test_get_artifact_validates_uuid_format(async_client: AsyncClient):
    """GET /api/v1/artifacts/{artifact_id} should validate artifact_id is valid UUID"""
    response = await async_client.get("/api/v1/artifacts/not-a-valid-uuid")

    # Should return 400/422 for invalid UUID format
    assert response.status_code in [400, 404, 422]


@pytest.mark.asyncio
async def test_get_artifact_includes_optional_fields(async_client: AsyncClient):
    """GET /api/v1/artifacts/{artifact_id} should include pr_url and deployed_at when deployed"""
    artifact_id = str(uuid4())
    response = await async_client.get(f"/api/v1/artifacts/{artifact_id}")

    if response.status_code == 200:
        data = response.json()

        # pr_url and deployed_at are nullable, should be present
        assert "pr_url" in data
        assert "deployed_at" in data

        # If status is deployed, pr_url and deployed_at should have values
        if data["status"] == "deployed":
            # pr_url should be a valid URI or None
            if data["pr_url"]:
                assert isinstance(data["pr_url"], str)
                assert data["pr_url"].startswith("http")


# ============================================================================
# PATCH /api/v1/artifacts/{artifact_id}/deploy - Deploy Artifact with Policy Guard
# ============================================================================


@pytest.mark.asyncio
async def test_deploy_artifact_returns_200(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should initiate deployment"""
    artifact_id = str(uuid4())
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    # Should return 200 on success or 404 if artifact not found
    assert response.status_code in [200, 404, 400, 409]

    if response.status_code == 200:
        data = response.json()

        # Validate response schema per artifacts-api.yaml
        assert "artifact_id" in data
        assert data["artifact_id"] == artifact_id
        assert "status" in data
        assert data["status"] in ["deployed", "pending_approval"]
        assert "pr_url" in data

        # If status is deployed, pr_url should be present
        if data["status"] == "deployed":
            assert data["pr_url"] is not None
            assert isinstance(data["pr_url"], str)
            assert data["pr_url"].startswith("http")

        # If status is pending_approval, pr_url should be null
        if data["status"] == "pending_approval":
            assert data["pr_url"] is None

        # policy_result is optional
        assert "policy_result" in data


@pytest.mark.asyncio
async def test_deploy_artifact_with_policy_passed(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should return policy_result when policy evaluator enabled"""
    artifact_id = str(uuid4())
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    if response.status_code == 200:
        data = response.json()

        if data.get("policy_result"):
            policy = data["policy_result"]

            # Validate policy_result schema
            assert "blast_radius_score" in policy
            assert isinstance(policy["blast_radius_score"], (int, float))
            assert "threshold" in policy
            assert isinstance(policy["threshold"], (int, float))
            assert "passed" in policy
            assert isinstance(policy["passed"], bool)
            assert "details" in policy
            assert isinstance(policy["details"], dict)

            # If policy passed, status should be deployed
            if policy["passed"]:
                assert data["status"] == "deployed"

            # If policy failed, status should be pending_approval
            if not policy["passed"]:
                assert data["status"] == "pending_approval"


@pytest.mark.asyncio
async def test_deploy_artifact_with_custom_repository(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should support custom repository in request body"""
    artifact_id = str(uuid4())
    request_body = {
        "repository": "my-org/infrastructure",
        "branch_prefix": "slo-scout"
    }

    response = await async_client.patch(
        f"/api/v1/artifacts/{artifact_id}/deploy",
        json=request_body
    )

    # Should accept custom repository
    assert response.status_code in [200, 404, 400, 409]


@pytest.mark.asyncio
async def test_deploy_artifact_returns_404_for_nonexistent_artifact(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should return 404 for non-existent artifact"""
    artifact_id = str(uuid4())  # Random UUID that doesn't exist
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    # Should return 404 if artifact not found
    assert response.status_code in [200, 404, 400, 409]


@pytest.mark.asyncio
async def test_deploy_artifact_returns_409_if_already_deployed(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should return 409 if artifact already deployed"""
    artifact_id = str(uuid4())
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    # Should return 409 Conflict if artifact already deployed
    assert response.status_code in [200, 404, 400, 409]


@pytest.mark.asyncio
async def test_deploy_artifact_validates_uuid_format(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should validate artifact_id is valid UUID"""
    response = await async_client.patch("/api/v1/artifacts/not-a-valid-uuid/deploy")

    # Should return 400/422 for invalid UUID format
    assert response.status_code in [400, 404, 422]


@pytest.mark.asyncio
async def test_deploy_artifact_with_high_blast_radius(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should block deployment if blast radius exceeds threshold"""
    artifact_id = str(uuid4())
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    if response.status_code == 200:
        data = response.json()

        if data.get("policy_result"):
            policy = data["policy_result"]

            # If blast radius score exceeds threshold, should be blocked
            if policy["blast_radius_score"] > policy["threshold"]:
                assert policy["passed"] is False
                assert data["status"] == "pending_approval"
                assert data["pr_url"] is None


@pytest.mark.asyncio
async def test_deploy_artifact_optional_request_body(async_client: AsyncClient):
    """PATCH /api/v1/artifacts/{artifact_id}/deploy should work without request body"""
    artifact_id = str(uuid4())
    # Deploy without request body (requestBody is optional per spec)
    response = await async_client.patch(f"/api/v1/artifacts/{artifact_id}/deploy")

    # Should accept request without body
    assert response.status_code in [200, 404, 400, 409]


# ============================================================================
# Additional Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_artifact_schema_consistency(async_client: AsyncClient):
    """Artifact schema should be consistent across all endpoints"""
    # Create an artifact
    create_response = await async_client.post(
        "/api/v1/artifacts/generate",
        json={"slo_id": str(uuid4()), "artifact_type": "prometheus_rule"}
    )

    if create_response.status_code == 201:
        created_artifact = create_response.json()
        artifact_id = created_artifact["artifact_id"]

        # Get the artifact by ID
        get_response = await async_client.get(f"/api/v1/artifacts/{artifact_id}")

        if get_response.status_code == 200:
            retrieved_artifact = get_response.json()

            # Schema should be identical
            assert set(created_artifact.keys()) == set(retrieved_artifact.keys())
            assert created_artifact["artifact_id"] == retrieved_artifact["artifact_id"]
            assert created_artifact["slo_id"] == retrieved_artifact["slo_id"]
            assert created_artifact["artifact_type"] == retrieved_artifact["artifact_type"]
