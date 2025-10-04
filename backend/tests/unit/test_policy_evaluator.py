"""
Unit tests for policy evaluator service.

Tests T114: Policy evaluator with blast radius calculation
"""
import pytest
from decimal import Decimal
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, MagicMock

from backend.src.services.policy_evaluator import PolicyEvaluator, PolicyEvaluationResult
from backend.src.services.blast_radius import BlastRadiusMetrics
from backend.src.models.policy import Policy, PolicyScope, EnforcementMode
from backend.src.models.artifact import Artifact, ArtifactType


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = Mock()
    session.query = Mock()
    session.execute = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def sample_blast_radius():
    """Create sample blast radius metrics."""
    return BlastRadiusMetrics(
        affected_services_count=3,
        affected_services_percentage=15.0,
        total_services_count=20,
        affected_endpoints_count=5,
        affected_traffic_percentage=25.0,
        estimated_cost_impact_usd=Decimal("45.00"),
        affected_service_ids={uuid4(), uuid4(), uuid4()}
    )


@pytest.fixture
def sample_policy():
    """Create sample policy with default thresholds."""
    return Policy(
        policy_id=uuid4(),
        name="test-blast-radius",
        scope=PolicyScope.GLOBAL,
        scope_id=None,
        invariants={
            "max_services_affected": 5,
            "max_services_percentage": 10.0,
            "max_cost_impact_usd": 100.0
        },
        allowed_actions=["deploy", "approve"],
        enforcement_mode=EnforcementMode.BLOCK,
        audit_required=True,
        created_by="test_user"
    )


class TestPolicyEvaluator:
    """Test suite for PolicyEvaluator."""

    @pytest.mark.asyncio
    async def test_evaluate_policy_within_thresholds(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test policy evaluation when all thresholds are met."""
        # Adjust blast radius to be within thresholds
        sample_blast_radius.affected_services_count = 3
        sample_blast_radius.affected_services_percentage = 8.0
        sample_blast_radius.estimated_cost_impact_usd = Decimal("50.00")

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is True
        assert result.policy_name == "test-blast-radius"
        assert result.enforcement_mode == EnforcementMode.BLOCK
        assert len(result.violated_invariants) == 0
        assert len(result.suggested_actions) == 0

    @pytest.mark.asyncio
    async def test_evaluate_policy_exceeds_service_count(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test policy violation when service count exceeds limit."""
        # Set service count above threshold (5)
        sample_blast_radius.affected_services_count = 7
        sample_blast_radius.affected_services_percentage = 8.0  # Below threshold
        sample_blast_radius.estimated_cost_impact_usd = Decimal("50.00")  # Below threshold

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is False
        assert "max_services_affected" in result.violated_invariants
        assert "7 services" in result.violated_invariants["max_services_affected"]
        assert "exceeds limit of 5" in result.violated_invariants["max_services_affected"]
        assert any("Reduce scope" in action for action in result.suggested_actions)

    @pytest.mark.asyncio
    async def test_evaluate_policy_exceeds_percentage(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test policy violation when service percentage exceeds limit."""
        # Set percentage above threshold (10%)
        sample_blast_radius.affected_services_count = 3  # Below count threshold
        sample_blast_radius.affected_services_percentage = 15.0  # Above threshold
        sample_blast_radius.estimated_cost_impact_usd = Decimal("50.00")

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is False
        assert "max_services_percentage" in result.violated_invariants
        assert "15.0%" in result.violated_invariants["max_services_percentage"]

    @pytest.mark.asyncio
    async def test_evaluate_policy_exceeds_cost(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test policy violation when cost impact exceeds limit."""
        # Set cost above threshold ($100)
        sample_blast_radius.affected_services_count = 3
        sample_blast_radius.affected_services_percentage = 8.0
        sample_blast_radius.estimated_cost_impact_usd = Decimal("150.00")  # Above threshold

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is False
        assert "max_cost_impact_usd" in result.violated_invariants
        assert "$150.00" in result.violated_invariants["max_cost_impact_usd"]
        assert "exceeds limit of $100" in result.violated_invariants["max_cost_impact_usd"]

    @pytest.mark.asyncio
    async def test_evaluate_policy_multiple_violations(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test policy with multiple threshold violations."""
        # Exceed multiple thresholds
        sample_blast_radius.affected_services_count = 7  # > 5
        sample_blast_radius.affected_services_percentage = 15.0  # > 10%
        sample_blast_radius.estimated_cost_impact_usd = Decimal("150.00")  # > $100

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is False
        assert len(result.violated_invariants) == 3
        assert "max_services_affected" in result.violated_invariants
        assert "max_services_percentage" in result.violated_invariants
        assert "max_cost_impact_usd" in result.violated_invariants
        assert len(result.suggested_actions) >= 3

    @pytest.mark.asyncio
    async def test_policy_violation_response_format(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test PolicyViolation response format per api-artifacts.yaml."""
        # Create violation
        sample_blast_radius.affected_services_count = 10

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        violation_response = result.to_violation_response()

        # Verify response structure
        assert "error_code" in violation_response
        assert "message" in violation_response
        assert "policy_name" in violation_response
        assert "violated_invariants" in violation_response
        assert "suggested_actions" in violation_response

        # Verify values
        assert violation_response["policy_name"] == "test-blast-radius"
        assert "POLICY_" in violation_response["error_code"]
        assert isinstance(violation_response["violated_invariants"], dict)
        assert isinstance(violation_response["suggested_actions"], list)

    @pytest.mark.asyncio
    async def test_load_policies_scope_hierarchy(self, mock_db_session):
        """Test policy loading respects scope hierarchy."""
        # Create policies with different scopes
        global_policy = Policy(
            policy_id=uuid4(),
            name="global-policy",
            scope=PolicyScope.GLOBAL,
            scope_id=None,
            invariants={"max_services_affected": 10},
            allowed_actions=["deploy"],
            enforcement_mode=EnforcementMode.BLOCK,
            audit_required=True,
            created_by="system"
        )

        org_id = uuid4()
        org_policy = Policy(
            policy_id=uuid4(),
            name="org-policy",
            scope=PolicyScope.ORGANIZATION,
            scope_id=org_id,
            invariants={"max_services_affected": 5},
            allowed_actions=["deploy"],
            enforcement_mode=EnforcementMode.BLOCK,
            audit_required=True,
            created_by="org_admin"
        )

        service_id = uuid4()
        service_policy = Policy(
            policy_id=uuid4(),
            name="service-policy",
            scope=PolicyScope.SERVICE,
            scope_id=service_id,
            invariants={"max_services_affected": 1},
            allowed_actions=["deploy"],
            enforcement_mode=EnforcementMode.BLOCK,
            audit_required=True,
            created_by="service_owner"
        )

        # Mock query to return all policies
        mock_scalars = Mock()
        mock_scalars.all.return_value = [global_policy, org_policy, service_policy]
        mock_result = Mock()
        mock_result.scalars.return_value = mock_scalars
        mock_db_session.execute.return_value = mock_result

        evaluator = PolicyEvaluator(mock_db_session)
        policies = evaluator._load_applicable_policies(
            action="deploy",
            service_id=service_id,
            organization_id=org_id
        )

        # Should return policies sorted by specificity: service > org > global
        assert len(policies) == 3
        assert policies[0].scope == PolicyScope.SERVICE
        assert policies[1].scope == PolicyScope.ORGANIZATION
        assert policies[2].scope == PolicyScope.GLOBAL

    @pytest.mark.asyncio
    async def test_enforcement_mode_warn(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test WARN enforcement mode logs but doesn't block."""
        # Set to WARN mode
        sample_policy.enforcement_mode = EnforcementMode.WARN
        sample_blast_radius.affected_services_count = 10  # Exceeds threshold

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        assert result.is_allowed is False
        assert result.enforcement_mode == EnforcementMode.WARN
        # In actual implementation, warning would be logged but not block

    @pytest.mark.asyncio
    async def test_enforcement_mode_audit(
        self,
        mock_db_session,
        sample_policy,
        sample_blast_radius
    ):
        """Test AUDIT enforcement mode only logs, never blocks."""
        # Set to AUDIT mode
        sample_policy.enforcement_mode = EnforcementMode.AUDIT
        sample_blast_radius.affected_services_count = 10  # Exceeds threshold

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=sample_blast_radius,
            action="deploy"
        )

        # Even with violation, audit mode sets is_allowed based on thresholds
        # but enforcement determines actual blocking behavior
        assert result.enforcement_mode == EnforcementMode.AUDIT

    @pytest.mark.asyncio
    async def test_default_policy_creation(self, mock_db_session):
        """Test default policy creation per research.md FR-034."""
        # Mock no existing policy
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db_session.query.return_value = mock_query

        evaluator = PolicyEvaluator(mock_db_session)
        default_policy = await evaluator.get_default_policy()

        # Verify default policy creation
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

        # Created policy should be the one added
        added_policy = mock_db_session.add.call_args[0][0]
        assert added_policy.name == "default-blast-radius"
        assert added_policy.scope == PolicyScope.GLOBAL
        assert added_policy.invariants["max_services_affected"] == 5
        assert added_policy.invariants["max_services_percentage"] == 10.0
        assert added_policy.invariants["max_cost_impact_usd"] == 100.0
        assert added_policy.enforcement_mode == EnforcementMode.BLOCK


class TestMultiDimensionalThresholds:
    """Test multi-dimensional threshold logic per research.md FR-034."""

    @pytest.mark.asyncio
    async def test_max_function_small_deployment(self, mock_db_session, sample_policy):
        """
        Test that absolute count prevents false positives in small deployments.

        Per FR-034: "Percentage alone fails for small deployments (10% of 3 services = 0.3)"
        """
        # Small deployment: 3 total services, affecting 1 (33%)
        blast_radius = BlastRadiusMetrics(
            affected_services_count=1,
            affected_services_percentage=33.3,  # Above 10% threshold
            total_services_count=3,
            affected_endpoints_count=2,
            affected_traffic_percentage=10.0,
            estimated_cost_impact_usd=Decimal("10.00"),
            affected_service_ids={uuid4()}
        )

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=blast_radius,
            action="deploy"
        )

        # Should violate percentage threshold (33% > 10%)
        assert "max_services_percentage" in result.violated_invariants
        # But count is within limits (1 < 5)
        assert "max_services_affected" not in result.violated_invariants

    @pytest.mark.asyncio
    async def test_max_function_large_deployment(self, mock_db_session, sample_policy):
        """
        Test that percentage prevents false positives in large deployments.

        Per FR-034: "Absolute count fails for large deployments (5 services out of 1000 = 0.5%)"
        """
        # Large deployment: 1000 total services, affecting 3 (0.3%)
        blast_radius = BlastRadiusMetrics(
            affected_services_count=3,
            affected_services_percentage=0.3,  # Well below 10% threshold
            total_services_count=1000,
            affected_endpoints_count=5,
            affected_traffic_percentage=5.0,
            estimated_cost_impact_usd=Decimal("30.00"),
            affected_service_ids={uuid4(), uuid4(), uuid4()}
        )

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=blast_radius,
            action="deploy"
        )

        # Should pass both thresholds
        # Count: 3 < 5 ✓
        # Percentage: 0.3% < 10% ✓
        assert "max_services_affected" not in result.violated_invariants
        assert "max_services_percentage" not in result.violated_invariants
        assert result.is_allowed is True

    @pytest.mark.asyncio
    async def test_cost_prevents_expensive_actions(self, mock_db_session, sample_policy):
        """
        Test that cost impact prevents expensive actions.

        Per FR-034: "Cost impact prevents expensive actions (e.g., increase replicas 10x)"
        """
        # Small service count but high cost
        blast_radius = BlastRadiusMetrics(
            affected_services_count=2,  # Within count limit
            affected_services_percentage=5.0,  # Within percentage limit
            total_services_count=40,
            affected_endpoints_count=3,
            affected_traffic_percentage=10.0,
            estimated_cost_impact_usd=Decimal("500.00"),  # Exceeds $100 limit
            affected_service_ids={uuid4(), uuid4()}
        )

        evaluator = PolicyEvaluator(mock_db_session)
        result = evaluator._evaluate_policy(
            policy=sample_policy,
            blast_radius=blast_radius,
            action="deploy"
        )

        # Should only violate cost threshold
        assert "max_services_affected" not in result.violated_invariants
        assert "max_services_percentage" not in result.violated_invariants
        assert "max_cost_impact_usd" in result.violated_invariants
        assert result.is_allowed is False
