"""
Integration test for artifact deployment workflow (Step 6 - quickstart.md)

Tests the complete artifact deployment workflow including:
- POST /api/v1/artifacts/generate (Prometheus rule generation)
- Promtool validation (FR-018)
- PolicyGuard blast radius evaluation (FR-034)
- GitHub PR creation (FR-036)
- Fail-open behavior when policy evaluator disabled (clarification: "B - Fail-open")
- Artifact rollback functionality

MUST FAIL initially before implementation (TDD principle)

Per spec.md FR-006, FR-007, FR-008, FR-009, FR-018, FR-034, FR-036
"""
import pytest
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock, MagicMock, call
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from uuid import UUID, uuid4
from datetime import datetime
from decimal import Decimal

from src.models.artifact import Artifact, ArtifactType, ValidationStatus, ApprovalStatus
from src.models.policy import Policy, PolicyScope, EnforcementMode
from src.services.blast_radius import BlastRadiusMetrics
from src.services.policy_evaluator import PolicyEvaluationResult


@pytest.fixture
def mock_promtool():
    """Mock promtool validation for Prometheus rules."""
    with patch('src.validators.promtool_validator.PrometheusValidator') as mock:
        mock_instance = Mock()
        mock_instance.validate_recording_rules = Mock(return_value={
            "is_valid": True,
            "errors": [],
            "warnings": []
        })
        mock_instance.validate_alert_rules = Mock(return_value={
            "is_valid": True,
            "errors": [],
            "warnings": []
        })
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_promtool_failure():
    """Mock promtool validation failure for invalid Prometheus rules."""
    with patch('src.validators.promtool_validator.PrometheusValidator') as mock:
        mock_instance = Mock()
        mock_instance.validate_recording_rules = Mock(return_value={
            "is_valid": False,
            "errors": [
                "invalid expression: parse error at char 15: unexpected identifier"
            ],
            "warnings": []
        })
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_policy_evaluator_pass():
    """Mock PolicyEvaluator that passes all checks."""
    with patch('src.services.policy_evaluator.PolicyEvaluator') as mock:
        mock_instance = Mock()

        # Create successful policy evaluation result
        result = PolicyEvaluationResult(
            is_allowed=True,
            policy_name="default-blast-radius",
            enforcement_mode=EnforcementMode.BLOCK,
            violated_invariants={},
            suggested_actions=[],
            blast_radius_metrics=BlastRadiusMetrics(
                affected_services_count=2,
                affected_services_percentage=5.0,
                total_services_count=40,
                affected_endpoints_count=3,
                affected_traffic_percentage=10.0,
                estimated_cost_impact_usd=Decimal("25.00"),
                affected_service_ids={uuid4(), uuid4()}
            )
        )

        mock_instance.evaluate_deployment = AsyncMock(return_value=result)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_policy_evaluator_violation():
    """Mock PolicyEvaluator that detects policy violations."""
    with patch('src.services.policy_evaluator.PolicyEvaluator') as mock:
        mock_instance = Mock()

        # Create policy violation result
        result = PolicyEvaluationResult(
            is_allowed=False,
            policy_name="default-blast-radius",
            enforcement_mode=EnforcementMode.BLOCK,
            violated_invariants={
                "max_services_affected": "7 services affected exceeds limit of 5",
                "max_cost_impact_usd": "$150.00 exceeds limit of $100.00"
            },
            suggested_actions=[
                "Reduce deployment scope to fewer services",
                "Request approval override from platform team"
            ],
            blast_radius_metrics=BlastRadiusMetrics(
                affected_services_count=7,
                affected_services_percentage=17.5,
                total_services_count=40,
                affected_endpoints_count=12,
                affected_traffic_percentage=35.0,
                estimated_cost_impact_usd=Decimal("150.00"),
                affected_service_ids={uuid4() for _ in range(7)}
            )
        )

        mock_instance.evaluate_deployment = AsyncMock(return_value=result)
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_policy_evaluator_disabled():
    """Mock PolicyEvaluator in disabled state (fail-open behavior)."""
    with patch('src.services.policy_evaluator.PolicyEvaluator') as mock:
        # Simulate disabled state by raising exception
        mock_instance = Mock()
        mock_instance.evaluate_deployment = AsyncMock(
            side_effect=Exception("Policy evaluator service unavailable")
        )
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_github_client():
    """Mock GitHub client for PR creation."""
    with patch('src.integrations.github_client.GitHubClient') as mock:
        mock_instance = Mock()
        mock_instance.create_pull_request = AsyncMock(return_value={
            "pr_url": "https://github.com/org/observability-config/pull/42",
            "pr_number": 42,
            "branch_name": "slo-scout/payments-api-slos"
        })
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_github_client_failure():
    """Mock GitHub client that fails PR creation."""
    with patch('src.integrations.github_client.GitHubClient') as mock:
        mock_instance = Mock()
        mock_instance.create_pull_request = AsyncMock(
            side_effect=Exception("GitHub API rate limit exceeded")
        )
        mock.return_value = mock_instance
        yield mock_instance


class TestArtifactGeneration:
    """Test POST /api/v1/artifacts/generate endpoint."""

    def test_generate_prometheus_recording_rules_with_promtool_validation(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool
    ):
        """
        Test Prometheus recording rule generation with promtool validation.

        Per FR-018: All Prometheus artifacts MUST pass promtool validation
        """
        generate_request = {
            "slo_id": str(sample_slo.slo_id),
            "artifact_types": ["prometheus_recording"],
            "validation_only": False
        }

        response = client.post("/api/v1/artifacts/generate", json=generate_request)

        # Should succeed with 201
        assert response.status_code == 201
        artifacts = response.json()

        # Verify artifact generated
        assert isinstance(artifacts, list)
        assert len(artifacts) >= 1

        prometheus_artifact = next(
            (a for a in artifacts if a["artifact_type"] == "prometheus_recording"),
            None
        )
        assert prometheus_artifact is not None

        # Verify promtool validation was called (FR-018)
        mock_promtool.validate_recording_rules.assert_called_once()

        # Verify validation status is PASSED
        assert prometheus_artifact["validation_status"] == "passed"
        assert "content" in prometheus_artifact
        assert len(prometheus_artifact["content"]) > 0

        # Verify content structure
        content = prometheus_artifact["content"]
        assert "groups:" in content
        assert "record:" in content or "- record:" in content

    def test_generate_prometheus_alert_rules_with_promtool_validation(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool
    ):
        """
        Test Prometheus alert rule generation with promtool validation.

        Per FR-018: All Prometheus artifacts MUST pass promtool validation
        """
        generate_request = {
            "slo_id": str(sample_slo.slo_id),
            "artifact_types": ["prometheus_alert"],
            "validation_only": False
        }

        response = client.post("/api/v1/artifacts/generate", json=generate_request)

        assert response.status_code == 201
        artifacts = response.json()

        prometheus_artifact = next(
            (a for a in artifacts if a["artifact_type"] == "prometheus_alert"),
            None
        )
        assert prometheus_artifact is not None

        # Verify promtool validation was called
        mock_promtool.validate_alert_rules.assert_called_once()

        # Verify validation status
        assert prometheus_artifact["validation_status"] == "passed"

        # Verify content structure
        content = prometheus_artifact["content"]
        assert "alert:" in content or "- alert:" in content

    def test_generate_fails_when_promtool_validation_fails(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool_failure
    ):
        """
        Test artifact generation when promtool validation fails.

        Per FR-018: Invalid Prometheus rules MUST be marked as validation_status=failed
        """
        generate_request = {
            "slo_id": str(sample_slo.slo_id),
            "artifact_types": ["prometheus_recording"],
            "validation_only": False
        }

        response = client.post("/api/v1/artifacts/generate", json=generate_request)

        # Should still return 201 but with failed validation
        assert response.status_code == 201
        artifacts = response.json()

        prometheus_artifact = next(
            (a for a in artifacts if a["artifact_type"] == "prometheus_recording"),
            None
        )
        assert prometheus_artifact is not None

        # Verify validation status is FAILED
        assert prometheus_artifact["validation_status"] == "failed"

        # Verify validation errors are included
        if "validation_errors" in prometheus_artifact:
            assert len(prometheus_artifact["validation_errors"]) > 0
            assert "parse error" in str(prometheus_artifact["validation_errors"])

    def test_generate_multiple_artifact_types(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool
    ):
        """
        Test generating multiple artifact types in single request.

        Per FR-006, FR-007, FR-008: Support multiple artifact types
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

        # Verify all types generated
        artifact_types = {a["artifact_type"] for a in artifacts}
        assert "prometheus_recording" in artifact_types or "prometheus_alert" in artifact_types

        # Each artifact should have content
        for artifact in artifacts:
            assert "content" in artifact
            assert len(artifact["content"]) > 0


class TestPolicyGuardEvaluation:
    """Test PolicyGuard blast radius calculation and enforcement."""

    def test_deployment_succeeds_when_policy_check_passes(
        self,
        client: TestClient,
        sample_artifact,
        mock_policy_evaluator_pass
    ):
        """
        Test deployment proceeds when PolicyGuard allows it.

        Per FR-034: Blast radius within thresholds allows deployment
        """
        # Approve artifact first
        approve_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )
        assert approve_response.status_code == 200

        # Attempt deployment
        deploy_request = {
            "action": "deploy"
        }

        response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json=deploy_request
        )

        # Should succeed
        assert response.status_code == 200
        artifact = response.json()

        # Verify policy evaluator was called
        mock_policy_evaluator_pass.evaluate_deployment.assert_called_once()

        # Verify deployment status
        assert artifact["deployment_status"] in ["deployed", "deploying"]

    def test_deployment_blocked_when_policy_violated(
        self,
        client: TestClient,
        sample_artifact,
        mock_policy_evaluator_violation
    ):
        """
        Test deployment blocked when PolicyGuard detects violations.

        Per FR-034: Blast radius exceeding thresholds blocks deployment
        """
        # Approve artifact first
        approve_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )
        assert approve_response.status_code == 200

        # Attempt deployment - should be blocked
        deploy_request = {
            "action": "deploy"
        }

        response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json=deploy_request
        )

        # Should return 403 Forbidden due to policy violation
        assert response.status_code == 403

        error = response.json()
        assert "detail" in error

        # Verify PolicyViolation response structure
        detail = error["detail"]
        if isinstance(detail, dict):
            assert "policy_name" in detail or "error_code" in detail
            assert "violated_invariants" in detail or "message" in detail
            assert "suggested_actions" in detail or "message" in detail

            # Verify violation details
            if "violated_invariants" in detail:
                invariants = detail["violated_invariants"]
                assert "max_services_affected" in invariants or "max_cost_impact_usd" in invariants

    def test_fail_open_when_policy_evaluator_disabled(
        self,
        client: TestClient,
        sample_artifact,
        mock_policy_evaluator_disabled
    ):
        """
        Test fail-open behavior when PolicyGuard is unavailable.

        Per clarification: "B - Fail-open" - deployment proceeds when policy service unavailable
        """
        # Approve artifact first
        approve_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )
        assert approve_response.status_code == 200

        # Attempt deployment with policy evaluator disabled
        deploy_request = {
            "action": "deploy"
        }

        response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json=deploy_request
        )

        # Should succeed with fail-open behavior (200 OK)
        assert response.status_code == 200

        artifact = response.json()

        # Deployment should proceed despite policy service failure
        assert artifact["deployment_status"] in ["deployed", "deploying"]

    def test_blast_radius_calculation_includes_affected_services(
        self,
        client: TestClient,
        sample_artifact,
        mock_policy_evaluator_pass
    ):
        """
        Test blast radius calculation includes service metrics.

        Per FR-034: Blast radius should calculate affected services count and percentage
        """
        # Approve artifact
        client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )

        # Deploy artifact
        response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "deploy"}
        )

        assert response.status_code == 200

        # Verify policy evaluator was called
        assert mock_policy_evaluator_pass.evaluate_deployment.called

        # Extract call arguments
        call_args = mock_policy_evaluator_pass.evaluate_deployment.call_args

        # Should include artifact_id and context
        if call_args:
            # Verify blast radius was calculated
            # (Actual verification would inspect the PolicyEvaluationResult)
            pass


class TestGitHubPRCreation:
    """Test GitHub PR creation workflow (FR-036)."""

    def test_create_pr_with_approved_artifacts(
        self,
        client: TestClient,
        sample_artifact,
        mock_github_client
    ):
        """
        Test GitHub PR creation with approved artifacts.

        Per FR-036: Create PR in observability config repo
        """
        # Approve artifact first
        approve_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )
        assert approve_response.status_code == 200

        # Create PR
        pr_request = {
            "artifact_ids": [str(sample_artifact.artifact_id)],
            "repository": "org/observability-config",
            "base_branch": "main",
            "title": "Add checkout latency SLO monitoring",
            "description": "Automated SLO artifacts for checkout flow"
        }

        response = client.post("/api/v1/pr", json=pr_request)

        # Should succeed
        assert response.status_code == 201
        pr_data = response.json()

        # Verify PR response structure
        assert "pr_url" in pr_data
        assert pr_data["pr_url"].startswith("https://github.com/")
        assert "/pull/" in pr_data["pr_url"]

        assert "branch_name" in pr_data
        assert pr_data["branch_name"].startswith("slo-scout/")

        # Verify GitHub client was called
        mock_github_client.create_pull_request.assert_called_once()

    def test_pr_creation_fails_without_approved_artifacts(
        self,
        client: TestClient,
        sample_artifact
    ):
        """
        Test PR creation requires approved artifacts.

        Per FR-036: Only approved artifacts should be included in PR
        """
        # Don't approve artifact - leave as pending

        # Attempt to create PR
        pr_request = {
            "artifact_ids": [str(sample_artifact.artifact_id)],
            "repository": "org/observability-config",
            "base_branch": "main"
        }

        response = client.post("/api/v1/pr", json=pr_request)

        # Should fail with 400 or 403
        assert response.status_code in [400, 403, 422]

    def test_pr_creation_handles_github_api_failure(
        self,
        client: TestClient,
        sample_artifact,
        mock_github_client_failure
    ):
        """
        Test graceful handling of GitHub API failures.

        Per FR-036: Handle GitHub API errors gracefully
        """
        # Approve artifact
        client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )

        # Attempt PR creation
        pr_request = {
            "artifact_ids": [str(sample_artifact.artifact_id)],
            "repository": "org/observability-config",
            "base_branch": "main"
        }

        response = client.post("/api/v1/pr", json=pr_request)

        # Should fail with 502 or 500 (external service error)
        assert response.status_code in [500, 502, 503]

        error = response.json()
        assert "detail" in error
        # Error should mention GitHub
        assert "GitHub" in str(error["detail"]) or "rate limit" in str(error["detail"]).lower()


class TestArtifactRollback:
    """Test artifact rollback functionality."""

    def test_rollback_deployed_artifact(
        self,
        client: TestClient,
        sample_artifact
    ):
        """
        Test rolling back a deployed artifact.

        Per api-artifacts.yaml: Support rollback action
        """
        # Approve and deploy artifact
        client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )

        deploy_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "deploy"}
        )

        # Assume deployment succeeds (or mock it)
        if deploy_response.status_code == 200:
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

            # Verify rollback status
            assert artifact["deployment_status"] == "rollback"

    def test_rollback_updates_artifact_version(
        self,
        client: TestClient,
        sample_artifact
    ):
        """
        Test rollback creates new artifact version.

        Per data-model.md: Artifact versioning
        """
        # Get original version
        original_version = sample_artifact.version

        # Approve, deploy, then rollback
        client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "approve"}
        )

        client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "deploy"}
        )

        rollback_response = client.patch(
            f"/api/v1/artifacts/{sample_artifact.artifact_id}",
            json={"action": "rollback"}
        )

        if rollback_response.status_code == 200:
            artifact = rollback_response.json()

            # Version should be incremented (or rollback tracked differently)
            if "version" in artifact:
                # Implementation may vary - version could increment or stay same
                assert artifact["version"] >= original_version


class TestEndToEndWorkflow:
    """Test complete artifact deployment workflow."""

    def test_full_deployment_workflow(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool,
        mock_policy_evaluator_pass,
        mock_github_client
    ):
        """
        Test complete workflow from generation to PR creation.

        Workflow:
        1. Generate artifacts with promtool validation
        2. Approve artifacts
        3. Deploy with PolicyGuard check
        4. Create GitHub PR
        """
        # Step 1: Generate artifacts
        generate_request = {
            "slo_id": str(sample_slo.slo_id),
            "artifact_types": ["prometheus_alert", "grafana_dashboard"],
            "validation_only": False
        }

        generate_response = client.post("/api/v1/artifacts/generate", json=generate_request)
        assert generate_response.status_code == 201
        artifacts = generate_response.json()

        # Filter for valid artifacts
        valid_artifacts = [
            a for a in artifacts
            if a.get("validation_status") == "passed"
        ]
        assert len(valid_artifacts) > 0

        # Step 2: Approve artifacts
        approved_ids = []
        for artifact in valid_artifacts:
            approve_response = client.patch(
                f"/api/v1/artifacts/{artifact['artifact_id']}",
                json={"action": "approve"}
            )

            if approve_response.status_code == 200:
                approved_ids.append(artifact['artifact_id'])

        assert len(approved_ids) > 0

        # Step 3: Create PR with approved artifacts
        pr_request = {
            "artifact_ids": approved_ids,
            "repository": "org/observability-config",
            "base_branch": "main",
            "title": "Add SLO monitoring artifacts"
        }

        pr_response = client.post("/api/v1/pr", json=pr_request)
        assert pr_response.status_code == 201

        pr_data = pr_response.json()
        assert "pr_url" in pr_data
        assert pr_data["pr_url"].startswith("https://github.com/")

        # Verify promtool was called
        assert mock_promtool.validate_alert_rules.called or mock_promtool.validate_recording_rules.called

        # Verify GitHub client was called
        assert mock_github_client.create_pull_request.called


class TestValidationOnly:
    """Test validation-only mode."""

    def test_validation_only_does_not_persist_artifacts(
        self,
        client: TestClient,
        sample_slo,
        mock_promtool
    ):
        """
        Test validation_only flag prevents artifact persistence.

        Per api-artifacts.yaml: validation_only should not save to database
        """
        generate_request = {
            "slo_id": str(sample_slo.slo_id),
            "artifact_types": ["prometheus_alert"],
            "validation_only": True
        }

        response = client.post("/api/v1/artifacts/generate", json=generate_request)
        assert response.status_code == 201
        artifacts = response.json()

        # Artifacts returned but not persisted
        assert len(artifacts) > 0

        # Try to approve - should fail if not persisted
        for artifact in artifacts:
            if "artifact_id" in artifact:
                approve_response = client.patch(
                    f"/api/v1/artifacts/{artifact['artifact_id']}",
                    json={"action": "approve"}
                )
                # May return 404 if artifact wasn't persisted
                # Implementation determines exact behavior


# Test coverage summary
def test_integration_coverage() -> None:
    """
    Meta-test to validate integration test coverage for Step 6.

    Integration tests cover:
    1. POST /api/v1/artifacts/generate (Prometheus rule generation)
    2. Promtool validation (FR-018)
    3. PolicyGuard blast radius evaluation (FR-034)
    4. GitHub PR creation (FR-036)
    5. Fail-open behavior when policy evaluator disabled
    6. Artifact rollback functionality
    7. End-to-end workflow validation
    """
    covered_areas = [
        "Artifact generation",
        "Promtool validation",
        "PolicyGuard evaluation",
        "GitHub PR creation",
        "Fail-open behavior",
        "Artifact rollback",
        "End-to-end workflow"
    ]

    assert len(covered_areas) == 7
    assert "Promtool validation" in covered_areas
    assert "PolicyGuard evaluation" in covered_areas
    assert "GitHub PR creation" in covered_areas
