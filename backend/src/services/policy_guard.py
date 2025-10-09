"""
Policy Guard - Deployment safety enforcement with blast radius calculation.

Enforces deployment policies with fail-open logic for safety guardrails.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import UUID
from decimal import Decimal
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.models.policy import Policy
from src.models.artifact import Artifact
from src.services.blast_radius import BlastRadiusCalculator, BlastRadiusMetrics

logger = logging.getLogger(__name__)


class PolicyNotFoundError(Exception):
    """Raised when a policy is not found."""
    pass


class PolicyViolationError(Exception):
    """Raised when a deployment violates a policy."""
    pass


@dataclass
class PolicyEvaluationResult:
    """
    Result of policy evaluation.

    Attributes:
        allowed: Whether deployment is allowed
        policy_id: UUID of the evaluated policy
        policy_name: Name of the policy
        blast_radius: Calculated blast radius metrics
        violations: List of policy violations
        warnings: List of policy warnings
        evaluated_at: Timestamp of evaluation
        fail_open: Whether result was fail-open due to error
    """
    allowed: bool
    policy_id: Optional[UUID]
    policy_name: Optional[str]
    blast_radius: BlastRadiusMetrics
    violations: List[str]
    warnings: List[str]
    evaluated_at: datetime
    fail_open: bool = False

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "allowed": self.allowed,
            "policy_id": str(self.policy_id) if self.policy_id else None,
            "policy_name": self.policy_name,
            "blast_radius": {
                "affected_services_count": self.blast_radius.affected_services_count,
                "affected_services_percentage": self.blast_radius.affected_services_percentage,
                "total_services_count": self.blast_radius.total_services_count,
                "affected_endpoints_count": self.blast_radius.affected_endpoints_count,
                "affected_traffic_percentage": self.blast_radius.affected_traffic_percentage,
                "estimated_cost_impact_usd": float(self.blast_radius.estimated_cost_impact_usd),
                "affected_service_ids": [str(sid) for sid in self.blast_radius.affected_service_ids]
            },
            "violations": self.violations,
            "warnings": self.warnings,
            "evaluated_at": self.evaluated_at.isoformat(),
            "fail_open": self.fail_open
        }


class PolicyGuard:
    """
    Policy Guard for enforcing deployment safety rules.

    Implements fail-open logic: if policy evaluation fails due to errors,
    the deployment is allowed (fail-open) with warnings logged.
    """

    def __init__(
        self,
        db_session: Session,
        blast_radius_calculator: Optional[BlastRadiusCalculator] = None
    ):
        """
        Initialize policy guard.

        Args:
            db_session: SQLAlchemy database session
            blast_radius_calculator: Optional BlastRadiusCalculator instance
        """
        self.db = db_session
        self.blast_radius_calc = blast_radius_calculator or BlastRadiusCalculator(db_session)

    async def evaluate(
        self,
        artifact_id: UUID,
        policy_name: Optional[str] = None,
        organization_id: Optional[UUID] = None
    ) -> PolicyEvaluationResult:
        """
        Evaluate if artifact deployment is allowed by policy.

        Implements fail-open: on evaluation errors, allows deployment with warnings.

        Args:
            artifact_id: UUID of artifact to evaluate
            policy_name: Optional specific policy to evaluate (default: active default policy)
            organization_id: Optional organization scope for blast radius calculation

        Returns:
            PolicyEvaluationResult with evaluation outcome

        Raises:
            ArtifactNotFoundError: If artifact not found (fail-close for invalid input)
        """
        try:
            # Verify artifact exists (fail-close on invalid input)
            artifact = self.db.query(Artifact).filter(
                Artifact.artifact_id == artifact_id
            ).first()
            if not artifact:
                raise ValueError(f"Artifact {artifact_id} not found")

            # Get policy (fail-open if policy retrieval fails)
            try:
                policy = await self._get_policy(policy_name)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve policy '{policy_name}': {str(e)}. "
                    "Failing open - allowing deployment.",
                    exc_info=True
                )
                # Fail-open with minimal blast radius
                blast_radius = self._create_minimal_blast_radius()
                return PolicyEvaluationResult(
                    allowed=True,
                    policy_id=None,
                    policy_name=policy_name,
                    blast_radius=blast_radius,
                    violations=[],
                    warnings=[f"Policy retrieval failed: {str(e)}. Failing open."],
                    evaluated_at=datetime.utcnow(),
                    fail_open=True
                )

            # Calculate blast radius (fail-open if calculation fails)
            try:
                blast_radius = await self.calculate_blast_radius(
                    artifact_id,
                    organization_id
                )
            except Exception as e:
                logger.error(
                    f"Failed to calculate blast radius for artifact {artifact_id}: {str(e)}. "
                    "Failing open - allowing deployment.",
                    exc_info=True
                )
                blast_radius = self._create_minimal_blast_radius()
                return PolicyEvaluationResult(
                    allowed=True,
                    policy_id=policy.policy_id if policy else None,
                    policy_name=policy.name if policy else policy_name,
                    blast_radius=blast_radius,
                    violations=[],
                    warnings=[f"Blast radius calculation failed: {str(e)}. Failing open."],
                    evaluated_at=datetime.utcnow(),
                    fail_open=True
                )

            # Evaluate policy rules
            violations = []
            warnings = []

            # Check if policy is enabled
            if not policy.enabled:
                warnings.append(f"Policy '{policy.name}' is disabled")

            # Check blast radius threshold
            blast_radius_decimal = Decimal(str(blast_radius.affected_services_percentage)) / 100
            if blast_radius_decimal > policy.blast_radius_threshold:
                violations.append(
                    f"Blast radius {blast_radius.affected_services_percentage}% "
                    f"exceeds threshold {float(policy.blast_radius_threshold) * 100}%"
                )

            # Determine if deployment is allowed
            allowed = len(violations) == 0

            result = PolicyEvaluationResult(
                allowed=allowed,
                policy_id=policy.policy_id,
                policy_name=policy.name,
                blast_radius=blast_radius,
                violations=violations,
                warnings=warnings,
                evaluated_at=datetime.utcnow(),
                fail_open=False
            )

            if allowed:
                logger.info(
                    f"Policy evaluation PASSED for artifact {artifact_id} "
                    f"(policy={policy.name})"
                )
            else:
                logger.warning(
                    f"Policy evaluation FAILED for artifact {artifact_id} "
                    f"(policy={policy.name}, violations={len(violations)})"
                )

            return result

        except ValueError:
            # Re-raise ValueError for invalid inputs (fail-close)
            raise
        except Exception as e:
            # Unexpected error - fail-open
            logger.error(
                f"Unexpected error during policy evaluation for artifact {artifact_id}: {str(e)}. "
                "Failing open - allowing deployment.",
                exc_info=True
            )
            blast_radius = self._create_minimal_blast_radius()
            return PolicyEvaluationResult(
                allowed=True,
                policy_id=None,
                policy_name=policy_name,
                blast_radius=blast_radius,
                violations=[],
                warnings=[f"Policy evaluation failed: {str(e)}. Failing open."],
                evaluated_at=datetime.utcnow(),
                fail_open=True
            )

    async def evaluate_batch(
        self,
        artifact_ids: List[UUID],
        policy_name: Optional[str] = None,
        organization_id: Optional[UUID] = None
    ) -> PolicyEvaluationResult:
        """
        Evaluate batch deployment of multiple artifacts.

        Args:
            artifact_ids: List of artifact UUIDs to evaluate
            policy_name: Optional specific policy to evaluate
            organization_id: Optional organization scope

        Returns:
            PolicyEvaluationResult for the batch deployment
        """
        try:
            if not artifact_ids:
                raise ValueError("No artifact IDs provided")

            # Get policy (fail-open on error)
            try:
                policy = await self._get_policy(policy_name)
            except Exception as e:
                logger.error(
                    f"Failed to retrieve policy '{policy_name}': {str(e)}. "
                    "Failing open - allowing deployment.",
                    exc_info=True
                )
                blast_radius = self._create_minimal_blast_radius()
                return PolicyEvaluationResult(
                    allowed=True,
                    policy_id=None,
                    policy_name=policy_name,
                    blast_radius=blast_radius,
                    violations=[],
                    warnings=[f"Policy retrieval failed: {str(e)}. Failing open."],
                    evaluated_at=datetime.utcnow(),
                    fail_open=True
                )

            # Calculate combined blast radius (fail-open on error)
            try:
                blast_radius = await self.blast_radius_calc.calculate_batch_impact(
                    artifact_ids,
                    organization_id
                )
            except Exception as e:
                logger.error(
                    f"Failed to calculate batch blast radius: {str(e)}. "
                    "Failing open - allowing deployment.",
                    exc_info=True
                )
                blast_radius = self._create_minimal_blast_radius()
                return PolicyEvaluationResult(
                    allowed=True,
                    policy_id=policy.policy_id if policy else None,
                    policy_name=policy.name if policy else policy_name,
                    blast_radius=blast_radius,
                    violations=[],
                    warnings=[f"Blast radius calculation failed: {str(e)}. Failing open."],
                    evaluated_at=datetime.utcnow(),
                    fail_open=True
                )

            # Evaluate policy
            violations = []
            warnings = []

            if not policy.enabled:
                warnings.append(f"Policy '{policy.name}' is disabled")

            blast_radius_decimal = Decimal(str(blast_radius.affected_services_percentage)) / 100
            if blast_radius_decimal > policy.blast_radius_threshold:
                violations.append(
                    f"Batch blast radius {blast_radius.affected_services_percentage}% "
                    f"exceeds threshold {float(policy.blast_radius_threshold) * 100}%"
                )

            allowed = len(violations) == 0

            logger.info(
                f"Batch policy evaluation for {len(artifact_ids)} artifacts: "
                f"{'PASSED' if allowed else 'FAILED'}"
            )

            return PolicyEvaluationResult(
                allowed=allowed,
                policy_id=policy.policy_id,
                policy_name=policy.name,
                blast_radius=blast_radius,
                violations=violations,
                warnings=warnings,
                evaluated_at=datetime.utcnow(),
                fail_open=False
            )

        except ValueError:
            # Re-raise ValueError for invalid inputs (fail-close)
            raise
        except Exception as e:
            # Unexpected error - fail-open
            logger.error(
                f"Unexpected error during batch policy evaluation: {str(e)}. "
                "Failing open - allowing deployment.",
                exc_info=True
            )
            blast_radius = self._create_minimal_blast_radius()
            return PolicyEvaluationResult(
                allowed=True,
                policy_id=None,
                policy_name=policy_name,
                blast_radius=blast_radius,
                violations=[],
                warnings=[f"Batch policy evaluation failed: {str(e)}. Failing open."],
                evaluated_at=datetime.utcnow(),
                fail_open=True
            )

    async def calculate_blast_radius(
        self,
        artifact_id: UUID,
        organization_id: Optional[UUID] = None
    ) -> BlastRadiusMetrics:
        """
        Calculate blast radius for an artifact.

        Args:
            artifact_id: UUID of the artifact
            organization_id: Optional organization scope

        Returns:
            BlastRadiusMetrics

        Raises:
            Exception: If calculation fails (caller should handle with fail-open)
        """
        return await self.blast_radius_calc.calculate_from_artifact(
            artifact_id,
            organization_id
        )

    async def _get_policy(self, policy_name: Optional[str] = None) -> Policy:
        """
        Get policy by name or default active policy.

        Args:
            policy_name: Optional policy name

        Returns:
            Policy instance

        Raises:
            PolicyNotFoundError: If policy not found
        """
        query = self.db.query(Policy)

        if policy_name:
            policy = query.filter(Policy.name == policy_name).first()
            if not policy:
                raise PolicyNotFoundError(f"Policy '{policy_name}' not found")
        else:
            # Get first enabled policy (default)
            policy = query.filter(Policy.enabled == True).first()
            if not policy:
                raise PolicyNotFoundError("No enabled policy found")

        logger.debug(f"Retrieved policy: {policy.name} ({policy.policy_id})")
        return policy

    def _create_minimal_blast_radius(self) -> BlastRadiusMetrics:
        """
        Create minimal blast radius for fail-open scenarios.

        Returns:
            BlastRadiusMetrics with minimal impact values
        """
        return BlastRadiusMetrics(
            affected_services_count=1,
            affected_services_percentage=0.0,
            total_services_count=1,
            affected_endpoints_count=1,
            affected_traffic_percentage=0.0,
            estimated_cost_impact_usd=Decimal("0.00"),
            affected_service_ids=set()
        )

    async def create_policy(
        self,
        name: str,
        blast_radius_threshold: Decimal,
        description: Optional[str] = None,
        enabled: bool = True
    ) -> Policy:
        """
        Create a new policy.

        Args:
            name: Policy name (must be unique)
            blast_radius_threshold: Maximum blast radius allowed (0.00-1.00)
            description: Optional policy description
            enabled: Whether policy is active

        Returns:
            Created Policy instance

        Raises:
            ValueError: If validation fails
        """
        if not name or not name.strip():
            raise ValueError("Policy name cannot be empty")

        if blast_radius_threshold < 0 or blast_radius_threshold > 1:
            raise ValueError(
                f"Blast radius threshold must be between 0 and 1, got {blast_radius_threshold}"
            )

        policy = Policy(
            name=name.strip(),
            description=description.strip() if description else None,
            blast_radius_threshold=blast_radius_threshold,
            enabled=enabled
        )

        try:
            self.db.add(policy)
            self.db.flush()
            logger.info(
                f"Created policy: {policy.name} "
                f"(threshold={blast_radius_threshold}, enabled={enabled})"
            )
            return policy
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to create policy: {str(e)}")
            raise

    async def get_policy(self, policy_id: UUID) -> Policy:
        """
        Get a policy by ID.

        Args:
            policy_id: UUID of the policy

        Returns:
            Policy instance

        Raises:
            PolicyNotFoundError: If policy not found
        """
        policy = self.db.query(Policy).filter(Policy.policy_id == policy_id).first()

        if not policy:
            raise PolicyNotFoundError(f"Policy with ID {policy_id} not found")

        logger.debug(f"Retrieved policy: {policy.name} ({policy.policy_id})")
        return policy

    async def list_policies(
        self,
        enabled: Optional[bool] = None,
        limit: int = 100
    ) -> List[Policy]:
        """
        List policies with optional filters.

        Args:
            enabled: Filter by enabled status
            limit: Maximum number of results

        Returns:
            List of Policy instances
        """
        query = self.db.query(Policy).order_by(Policy.created_at.desc())

        if enabled is not None:
            query = query.filter(Policy.enabled == enabled)

        policies = query.limit(limit).all()

        logger.debug(f"Listed {len(policies)} policies (enabled={enabled})")
        return policies

    async def update_policy(
        self,
        policy_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        blast_radius_threshold: Optional[Decimal] = None,
        enabled: Optional[bool] = None
    ) -> Policy:
        """
        Update a policy.

        Args:
            policy_id: UUID of the policy to update
            name: New name (optional)
            description: New description (optional)
            blast_radius_threshold: New threshold (optional)
            enabled: New enabled status (optional)

        Returns:
            Updated Policy instance

        Raises:
            PolicyNotFoundError: If policy not found
            ValueError: If validation fails
        """
        policy = await self.get_policy(policy_id)

        if name is not None:
            if not name.strip():
                raise ValueError("Policy name cannot be empty")
            policy.name = name.strip()

        if description is not None:
            policy.description = description.strip() if description else None

        if blast_radius_threshold is not None:
            if blast_radius_threshold < 0 or blast_radius_threshold > 1:
                raise ValueError(
                    f"Blast radius threshold must be between 0 and 1, got {blast_radius_threshold}"
                )
            policy.blast_radius_threshold = blast_radius_threshold

        if enabled is not None:
            policy.enabled = enabled

        policy.updated_at = datetime.utcnow()
        self.db.flush()

        logger.info(f"Updated policy: {policy.name} ({policy.policy_id})")
        return policy

    async def delete_policy(self, policy_id: UUID) -> None:
        """
        Delete a policy.

        Args:
            policy_id: UUID of the policy to delete

        Raises:
            PolicyNotFoundError: If policy not found
        """
        policy = await self.get_policy(policy_id)

        policy_name = policy.name
        self.db.delete(policy)
        self.db.flush()

        logger.info(f"Deleted policy: {policy_name} ({policy_id})")
