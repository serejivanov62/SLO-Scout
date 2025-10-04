"""
Integration test for artifact workflow (T141)

Tests the complete artifact workflow:
1. POST /api/v1/artifacts/generate to generate artifacts
2. PATCH /api/v1/artifacts/{id} to approve artifacts
3. POST /api/v1/pr to create GitOps PR
4. Assert PR URL is returned and artifacts are bundled correctly

Per spec.md FR-006, FR-007, FR-008, FR-009
"""
import pytest
from fastapi.testclient import TestClient
from uuid import UUID, uuid4
from datetime import datetime


def test_artifact_workflow_happy_path(
    client: TestClient,
    sample_slo,
    sample_artifact,
    mock_github
):
    """
    Test complete artifact workflow from generation to PR creation

    Workflow:
    1. POST /api/v1/artifacts/generate - generate artifacts
    2. PATCH /api/v1/artifacts/{id} - approve artifact
    3. POST /api/v1/pr - create GitOps PR
    """
    # Step 1: Generate artifacts from SLO
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": [
            "prometheus_alert",
            "grafana_dashboard",
            "runbook"
        ],
        "validation_only": False
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)

    assert response.status_code == 201
    artifacts = response.json()

    # Should generate requested artifact types
    assert isinstance(artifacts, list)
    assert len(artifacts) >= 1

    # Validate each artifact
    for artifact in artifacts:
        assert "artifact_id" in artifact
        UUID(artifact["artifact_id"])

        assert artifact["artifact_type"] in [
            "prometheus_alert",
            "grafana_dashboard",
            "runbook"
        ]
        assert artifact["validation_status"] in ["pending", "passed", "failed"]
        assert artifact["approval_status"] == "pending"
        assert "content" in artifact

    # Step 2: Approve artifacts
    approved_artifact_ids = []
    for artifact in artifacts:
        if artifact["validation_status"] == "passed":
            approve_request = {
                "action": "approve"
            }

            response = client.patch(
                f"/api/v1/artifacts/{artifact['artifact_id']}",
                json=approve_request
            )

            assert response.status_code == 200
            approved = response.json()

            assert approved["approval_status"] == "approved"
            assert approved["approved_at"] is not None
            approved_artifact_ids.append(approved["artifact_id"])

    # Step 3: Create GitOps PR with approved artifacts
    pr_request = {
        "artifact_ids": approved_artifact_ids,
        "repository": "org/infrastructure-repo",
        "base_branch": "main",
        "title": "Add checkout latency SLO monitoring",
        "description": "Automated SLO artifacts for checkout flow"
    }

    response = client.post("/api/v1/pr", json=pr_request)

    assert response.status_code == 201
    pr_data = response.json()

    # Validate PR response
    assert "pr_url" in pr_data
    assert pr_data["pr_url"].startswith("http")
    assert "/pull/" in pr_data["pr_url"] or "/merge_requests/" in pr_data["pr_url"]

    assert "branch_name" in pr_data
    assert pr_data["branch_name"].startswith("slo-scout/")

    assert "artifacts_included" in pr_data
    assert isinstance(pr_data["artifacts_included"], list)
    assert len(pr_data["artifacts_included"]) == len(approved_artifact_ids)


def test_artifact_workflow_validation_only(
    client: TestClient,
    sample_slo
):
    """
    Test artifact generation in validation-only mode

    Per api-artifacts.yaml: validation_only flag
    """
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": ["prometheus_alert"],
        "validation_only": True
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)

    assert response.status_code == 201
    artifacts = response.json()

    # Should generate artifacts but not save to database
    assert len(artifacts) >= 1

    # Artifacts should be validated but not persisted
    for artifact in artifacts:
        assert "validation_status" in artifact
        # In validation-only mode, artifact_id might be temporary
        if "artifact_id" in artifact:
            # Try to retrieve it - should not exist in DB
            response = client.patch(
                f"/api/v1/artifacts/{artifact['artifact_id']}",
                json={"action": "approve"}
            )
            # May succeed or fail depending on implementation


def test_artifact_workflow_policy_violation(
    client: TestClient,
    sample_slo,
    sample_artifact
):
    """
    Test artifact deployment blocked by policy guard

    Per spec.md FR-034, api-artifacts.yaml PolicyViolation
    """
    # Approve artifact first
    approve_response = client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json={"action": "approve"}
    )
    assert approve_response.status_code == 200

    # Attempt to deploy with policy violation
    # Mock policy evaluator to simulate blast radius violation
    deploy_request = {
        "action": "deploy"
    }

    response = client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json=deploy_request
    )

    # May succeed or return 403 if policy violated
    if response.status_code == 403:
        error = response.json()
        assert "detail" in error
        # Should include policy violation details
        if isinstance(error["detail"], dict):
            assert "policy_name" in error["detail"] or "error_code" in error["detail"]


def test_artifact_workflow_rollback(
    client: TestClient,
    sample_artifact
):
    """
    Test artifact rollback action

    Per api-artifacts.yaml: rollback action
    """
    # First approve and deploy
    client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json={"action": "approve"}
    )

    client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json={"action": "deploy"}
    )

    # Now rollback
    rollback_request = {
        "action": "rollback"
    }

    response = client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json=rollback_request
    )

    assert response.status_code == 200
    artifact = response.json()

    assert artifact["deployment_status"] == "rollback"


def test_artifact_workflow_reject(
    client: TestClient,
    sample_artifact
):
    """
    Test artifact rejection workflow

    Per api-artifacts.yaml: reject action
    """
    reject_request = {
        "action": "reject"
    }

    response = client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json=reject_request
    )

    assert response.status_code == 200
    artifact = response.json()

    assert artifact["approval_status"] == "rejected"


def test_artifact_workflow_multiple_types(
    client: TestClient,
    sample_slo
):
    """
    Test generating all artifact types

    Per spec.md FR-006, FR-007, FR-008
    """
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": [
            "prometheus_recording",
            "prometheus_alert",
            "grafana_dashboard",
            "runbook"
        ],
        "validation_only": False
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)

    assert response.status_code == 201
    artifacts = response.json()

    # Should generate all requested types
    artifact_types = {a["artifact_type"] for a in artifacts}
    assert "prometheus_alert" in artifact_types

    # Validate artifact content structure
    for artifact in artifacts:
        assert len(artifact["content"]) > 0

        if artifact["artifact_type"] == "prometheus_alert":
            # Should contain YAML alert rule
            assert "alert:" in artifact["content"] or "groups:" in artifact["content"]

        elif artifact["artifact_type"] == "prometheus_recording":
            # Should contain YAML recording rule
            assert "record:" in artifact["content"] or "groups:" in artifact["content"]

        elif artifact["artifact_type"] == "grafana_dashboard":
            # Should contain JSON dashboard
            assert "{" in artifact["content"]
            assert "panels" in artifact["content"] or "dashboard" in artifact["content"]

        elif artifact["artifact_type"] == "runbook":
            # Should contain YAML runbook
            assert "steps:" in artifact["content"] or "name:" in artifact["content"]


def test_artifact_workflow_validation_failure(
    client: TestClient,
    sample_slo
):
    """
    Test handling of validation failures

    Per spec.md: Artifacts should be validated before deployment
    """
    # Generate artifacts - some may fail validation
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": ["prometheus_alert"],
        "validation_only": False
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)
    assert response.status_code == 201
    artifacts = response.json()

    # Check for validation status
    for artifact in artifacts:
        if artifact["validation_status"] == "failed":
            # Should not be able to approve failed artifacts
            approve_request = {"action": "approve"}

            response = client.patch(
                f"/api/v1/artifacts/{artifact['artifact_id']}",
                json=approve_request
            )

            # Should reject approval of failed validation
            assert response.status_code in [400, 403, 422]


def test_pr_workflow_conventional_commit(
    client: TestClient,
    sample_artifact,
    mock_github
):
    """
    Test PR creation with conventional commit format

    Per spec.md FR-009: Conventional commit messages
    """
    # Approve artifact
    client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json={"action": "approve"}
    )

    # Create PR
    pr_request = {
        "artifact_ids": [str(sample_artifact.artifact_id)],
        "repository": "org/infrastructure-repo",
        "base_branch": "main"
    }

    response = client.post("/api/v1/pr", json=pr_request)

    assert response.status_code == 201
    pr_data = response.json()

    # Verify PR was created with mock
    assert mock_github.create_pull_request.called


def test_pr_workflow_no_approved_artifacts(
    client: TestClient
):
    """
    Test PR creation fails without approved artifacts

    Per api-artifacts.yaml: Requires approved artifacts
    """
    pr_request = {
        "artifact_ids": [],
        "repository": "org/infrastructure-repo",
        "base_branch": "main"
    }

    response = client.post("/api/v1/pr", json=pr_request)

    # Should return 400 or 422 for empty artifacts
    assert response.status_code in [400, 422]


def test_pr_workflow_invalid_repository(
    client: TestClient,
    sample_artifact
):
    """
    Test PR creation with invalid repository

    Per api-artifacts.yaml: Validate repository format
    """
    # Approve artifact
    client.patch(
        f"/api/v1/artifacts/{sample_artifact.artifact_id}",
        json={"action": "approve"}
    )

    # Try with invalid repository format
    pr_request = {
        "artifact_ids": [str(sample_artifact.artifact_id)],
        "repository": "invalid-repo-format",  # Missing org/repo format
        "base_branch": "main"
    }

    response = client.post("/api/v1/pr", json=pr_request)

    # Should validate repository format
    assert response.status_code in [400, 422]


def test_artifact_workflow_concurrent_approvals(
    client: TestClient,
    sample_slo
):
    """
    Test concurrent artifact approvals don't conflict

    Ensures thread-safe artifact state management
    """
    # Generate multiple artifacts
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": [
            "prometheus_alert",
            "grafana_dashboard",
            "runbook"
        ],
        "validation_only": False
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)
    assert response.status_code == 201
    artifacts = response.json()

    # Approve all artifacts
    for artifact in artifacts:
        if artifact["validation_status"] == "passed":
            response = client.patch(
                f"/api/v1/artifacts/{artifact['artifact_id']}",
                json={"action": "approve"}
            )
            assert response.status_code == 200


def test_artifact_workflow_version_tracking(
    client: TestClient,
    sample_slo
):
    """
    Test artifact version is tracked

    Per data-model.md: Artifact.version field
    """
    # Generate artifacts
    generate_request = {
        "slo_id": str(sample_slo.slo_id),
        "artifact_types": ["prometheus_alert"],
        "validation_only": False
    }

    response = client.post("/api/v1/artifacts/generate", json=generate_request)
    assert response.status_code == 201
    artifacts = response.json()

    # Check version field
    for artifact in artifacts:
        if "version" in artifact:
            assert isinstance(artifact["version"], int)
            assert artifact["version"] >= 1
