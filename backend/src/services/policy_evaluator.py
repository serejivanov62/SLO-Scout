"""
Policy evaluator service for governance rule enforcement.

Per research.md FR-034: Multi-dimensional blast radius thresholds
- Default: max(10% of services, 5 services, $100 cost impact)
- Supports enforcement modes: block, warn, audit
- Returns structured PolicyViolation responses per api-artifacts.yaml
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Any
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..models.policy import Policy, EnforcementMode, PolicyScope
from .blast_radius import BlastRadiusCalculator, BlastRadiusMetrics

logger = logging.getLogger(__name__)


@dataclass
class PolicyEvaluationResult:
    """
    Result of policy evaluation.

    Per api-artifacts.yaml PolicyViolation schema
    """
    is_allowed: bool
    policy_name: str
    enforcement_mode: EnforcementMode
    violated_invariants: Dict[str, Any]
    suggested_actions: List[str]
    blast_radius_metrics: Optional[BlastRadiusMetrics] = None

    def to_violation_response(self) -> Dict[str, Any]:
        """
        Convert to PolicyViolation API response format.

        Returns:
            Dictionary matching api-artifacts.yaml PolicyViolation schema
        """
        # Build error message
        violation_details = []
        for invariant, value in self.violated_invariants.items():
            violation_details.append(f"{invariant}: {value}")

        message = f"Policy '{self.policy_name}' violation: " + ", ".join(violation_details)

        return {
            "error_code": f"POLICY_{self.policy_name.upper().replace('-', '_')}_VIOLATED",
            "message": message,
            "policy_name": self.policy_name,
            "violated_invariants": self.violated_invariants,
            "suggested_actions": self.suggested_actions
        }


class PolicyEvaluator:
    """
    Evaluate artifact deployment requests against governance policies.

    Implements multi-dimensional policy checking:
    1. Load applicable policies from DB
    2. Calculate blast radius metrics
    3. Evaluate invariants against thresholds
    4. Return structured violation details
    """

    def __init__(self, db_session: Session):
        """
        Initialize policy evaluator.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        self.blast_radius_calc = BlastRadiusCalculator(db_session)

    async def evaluate_artifact_deployment(
        self,
        artifact_id: UUID,
        action: str,
        service_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None
    ) -> PolicyEvaluationResult:
        """
        Evaluate if artifact deployment is allowed by policies.

        Args:
            artifact_id: UUID of artifact to deploy
            action: Action being performed (e.g., "deploy", "approve")
            service_id: Optional service scope
            organization_id: Optional organization scope

        Returns:
            PolicyEvaluationResult with evaluation details
        """
        # Load applicable policies
        policies = self._load_applicable_policies(
            action=action,
            service_id=service_id,
            organization_id=organization_id
        )

        if not policies:
            logger.warning("No policies found for action '%s', allowing by default", action)
            return PolicyEvaluationResult(
                is_allowed=True,
                policy_name="default",
                enforcement_mode=EnforcementMode.AUDIT,
                violated_invariants={},
                suggested_actions=[]
            )

        # Calculate blast radius
        blast_radius = await self.blast_radius_calc.calculate_from_artifact(
            artifact_id=artifact_id,
            organization_id=organization_id
        )

        # Evaluate each policy
        for policy in policies:
            result = self._evaluate_policy(
                policy=policy,
                blast_radius=blast_radius,
                action=action
            )

            # If any policy blocks, return violation
            if not result.is_allowed and policy.enforcement_mode == EnforcementMode.BLOCK:
                logger.warning(
                    f"Policy '{policy.name}' BLOCKED artifact {artifact_id} deployment: "
                    f"{result.violated_invariants}"
                )
                result.blast_radius_metrics = blast_radius
                return result

            # Log warnings for warn mode
            if not result.is_allowed and policy.enforcement_mode == EnforcementMode.WARN:
                logger.warning(
                    f"Policy '{policy.name}' WARNING for artifact {artifact_id}: "
                    f"{result.violated_invariants}"
                )

            # Log audit events
            if policy.audit_required:
                self._log_audit_event(
                    policy=policy,
                    artifact_id=artifact_id,
                    result=result,
                    blast_radius=blast_radius
                )

        # All policies passed or only warnings/audits
        logger.info(f"Artifact {artifact_id} passed all BLOCK policies")
        return PolicyEvaluationResult(
            is_allowed=True,
            policy_name="all_policies",
            enforcement_mode=EnforcementMode.AUDIT,
            violated_invariants={},
            suggested_actions=[],
            blast_radius_metrics=blast_radius
        )

    def _load_applicable_policies(
        self,
        action: str,
        service_id: Optional[UUID] = None,
        organization_id: Optional[UUID] = None
    ) -> List[Policy]:
        """
        Load policies applicable to the current context.

        Policy scope hierarchy:
        1. Global policies (apply to all)
        2. Organization-scoped policies
        3. Service-scoped policies

        Args:
            action: Action being performed
            service_id: Optional service scope
            organization_id: Optional organization scope

        Returns:
            List of applicable Policy objects ordered by scope specificity
        """
        # Build query for applicable policies
        query = select(Policy).where(
            Policy.allowed_actions.contains([action])
        )

        # Include global, org, and service-scoped policies
        scope_filters = [Policy.scope == PolicyScope.GLOBAL]

        if organization_id:
            scope_filters.append(
                (Policy.scope == PolicyScope.ORGANIZATION) &
                (Policy.scope_id == organization_id)
            )

        if service_id:
            scope_filters.append(
                (Policy.scope == PolicyScope.SERVICE) &
                (Policy.scope_id == service_id)
            )

        from sqlalchemy import or_
        query = query.where(or_(*scope_filters))

        # Order by scope specificity: service > org > global
        policies = self.db.execute(query).scalars().all()

        # Sort by scope (most specific first)
        scope_priority = {
            PolicyScope.SERVICE: 0,
            PolicyScope.ORGANIZATION: 1,
            PolicyScope.GLOBAL: 2
        }
        return sorted(policies, key=lambda p: scope_priority[p.scope])

    def _evaluate_policy(
        self,
        policy: Policy,
        blast_radius: BlastRadiusMetrics,
        action: str
    ) -> PolicyEvaluationResult:
        """
        Evaluate a single policy against blast radius metrics.

        Per research.md FR-034 decision:
        - Default threshold: max(10% of services, 5 services, $100 cost impact)
        - Multi-dimensional evaluation (services %, count, cost)

        Args:
            policy: Policy to evaluate
            blast_radius: Calculated blast radius metrics
            action: Action being performed

        Returns:
            PolicyEvaluationResult
        """
        invariants = policy.invariants or {}
        violated_invariants = {}
        suggested_actions = []

        # Check max services affected (count)
        max_services = invariants.get("max_services_affected")
        if max_services is not None:
            if blast_radius.affected_services_count > max_services:
                violated_invariants["max_services_affected"] = (
                    f"Affects {blast_radius.affected_services_count} services, "
                    f"exceeds limit of {max_services}"
                )
                suggested_actions.append(
                    f"Reduce scope to fewer services (currently {blast_radius.affected_services_count})"
                )

        # Check max services affected (percentage)
        max_services_pct = invariants.get("max_services_percentage")
        if max_services_pct is not None:
            if blast_radius.affected_services_percentage > max_services_pct:
                violated_invariants["max_services_percentage"] = (
                    f"Affects {blast_radius.affected_services_percentage}% of services, "
                    f"exceeds limit of {max_services_pct}%"
                )
                suggested_actions.append(
                    f"Reduce service scope (currently {blast_radius.affected_services_percentage:.1f}%)"
                )

        # Check max cost impact
        max_cost = invariants.get("max_cost_impact_usd")
        if max_cost is not None:
            max_cost_decimal = Decimal(str(max_cost))
            if blast_radius.estimated_cost_impact_usd > max_cost_decimal:
                violated_invariants["max_cost_impact_usd"] = (
                    f"Cost impact ${blast_radius.estimated_cost_impact_usd}, "
                    f"exceeds limit of ${max_cost_decimal}"
                )
                suggested_actions.append(
                    f"Reduce cost impact (currently ${blast_radius.estimated_cost_impact_usd})"
                )

        # Check max traffic percentage
        max_traffic_pct = invariants.get("max_traffic_percentage")
        if max_traffic_pct is not None:
            if blast_radius.affected_traffic_percentage > max_traffic_pct:
                violated_invariants["max_traffic_percentage"] = (
                    f"Affects {blast_radius.affected_traffic_percentage}% of traffic, "
                    f"exceeds limit of {max_traffic_pct}%"
                )
                suggested_actions.append(
                    f"Reduce traffic impact (currently {blast_radius.affected_traffic_percentage:.1f}%)"
                )

        # Check max endpoints
        max_endpoints = invariants.get("max_endpoints_affected")
        if max_endpoints is not None:
            if blast_radius.affected_endpoints_count > max_endpoints:
                violated_invariants["max_endpoints_affected"] = (
                    f"Affects {blast_radius.affected_endpoints_count} endpoints, "
                    f"exceeds limit of {max_endpoints}"
                )
                suggested_actions.append(
                    f"Reduce endpoint scope (currently {blast_radius.affected_endpoints_count})"
                )

        # Add default suggestion if violations exist
        if violated_invariants and not suggested_actions:
            suggested_actions.append("Request policy override from administrator")

        is_allowed = len(violated_invariants) == 0

        return PolicyEvaluationResult(
            is_allowed=is_allowed,
            policy_name=policy.name,
            enforcement_mode=policy.enforcement_mode,
            violated_invariants=violated_invariants,
            suggested_actions=suggested_actions
        )

    async def evaluate_batch_deployment(
        self,
        artifact_ids: List[UUID],
        action: str,
        organization_id: Optional[UUID] = None
    ) -> PolicyEvaluationResult:
        """
        Evaluate batch artifact deployment against policies.

        Args:
            artifact_ids: List of artifact UUIDs
            action: Action being performed
            organization_id: Optional organization scope

        Returns:
            PolicyEvaluationResult for combined deployment
        """
        # Load applicable policies
        policies = self._load_applicable_policies(
            action=action,
            organization_id=organization_id
        )

        if not policies:
            return PolicyEvaluationResult(
                is_allowed=True,
                policy_name="default",
                enforcement_mode=EnforcementMode.AUDIT,
                violated_invariants={},
                suggested_actions=[]
            )

        # Calculate combined blast radius
        blast_radius = await self.blast_radius_calc.calculate_batch_impact(
            artifact_ids=artifact_ids,
            organization_id=organization_id
        )

        # Evaluate policies
        for policy in policies:
            result = self._evaluate_policy(
                policy=policy,
                blast_radius=blast_radius,
                action=action
            )

            if not result.is_allowed and policy.enforcement_mode == EnforcementMode.BLOCK:
                logger.warning(
                    f"Policy '{policy.name}' BLOCKED batch deployment: {result.violated_invariants}"
                )
                result.blast_radius_metrics = blast_radius
                return result

        return PolicyEvaluationResult(
            is_allowed=True,
            policy_name="all_policies",
            enforcement_mode=EnforcementMode.AUDIT,
            violated_invariants={},
            suggested_actions=[],
            blast_radius_metrics=blast_radius
        )

    def _log_audit_event(
        self,
        policy: Policy,
        artifact_id: UUID,
        result: PolicyEvaluationResult,
        blast_radius: BlastRadiusMetrics
    ) -> None:
        """
        Log audit event for policy evaluation.

        Args:
            policy: Policy that was evaluated
            artifact_id: Artifact being evaluated
            result: Evaluation result
            blast_radius: Calculated blast radius
        """
        audit_data = {
            "policy_name": policy.name,
            "policy_id": str(policy.policy_id),
            "artifact_id": str(artifact_id),
            "is_allowed": result.is_allowed,
            "enforcement_mode": policy.enforcement_mode.value,
            "violated_invariants": result.violated_invariants,
            "blast_radius": {
                "services_count": blast_radius.affected_services_count,
                "services_percentage": blast_radius.affected_services_percentage,
                "endpoints_count": blast_radius.affected_endpoints_count,
                "traffic_percentage": blast_radius.affected_traffic_percentage,
                "cost_impact_usd": str(blast_radius.estimated_cost_impact_usd)
            }
        }

        logger.info(f"AUDIT: Policy evaluation", extra={"audit_data": audit_data})

    async def get_default_policy(self) -> Policy:
        """
        Get or create default blast radius policy.

        Per research.md FR-034: max(10% of services, 5 services, $100 cost)

        Returns:
            Default Policy object
        """
        # Check if default policy exists
        default_policy = self.db.query(Policy).filter(
            Policy.name == "default-blast-radius",
            Policy.scope == PolicyScope.GLOBAL
        ).first()

        if default_policy:
            return default_policy

        # Create default policy
        default_policy = Policy(
            name="default-blast-radius",
            scope=PolicyScope.GLOBAL,
            scope_id=None,
            invariants={
                "max_services_affected": 5,
                "max_services_percentage": 10.0,
                "max_cost_impact_usd": 100.0
            },
            allowed_actions=["artifact_deploy", "approve", "deploy"],
            enforcement_mode=EnforcementMode.BLOCK,
            audit_required=True,
            created_by="system"
        )

        self.db.add(default_policy)
        self.db.commit()

        logger.info("Created default blast radius policy")
        return default_policy
