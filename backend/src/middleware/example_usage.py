"""
Example usage of Policy Guard middleware and helpers.

Shows how to integrate policy enforcement into FastAPI application.
"""
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from uuid import UUID
from typing import List

from .policy_guard import (
    PolicyGuardMiddleware,
    PolicyGuardException,
    check_artifact_policy,
    check_batch_policy
)
from ..models.policy import EnforcementMode


# Example 1: Add middleware to FastAPI app
# =========================================

def get_db() -> Session:
    """Database session dependency."""
    # In real app, this would create and yield a session
    pass


app = FastAPI()

# Add Policy Guard middleware
app.add_middleware(PolicyGuardMiddleware, get_db=get_db)


# Example 2: Explicit policy check in route handler
# =================================================

@app.patch("/api/v1/artifacts/{artifact_id}")
async def update_artifact(
    artifact_id: UUID,
    action: str,
    db: Session = Depends(get_db)
):
    """
    Update artifact with explicit policy check.

    The middleware will also check, but this shows explicit usage.
    """
    # Option A: Check policy and handle violation manually
    try:
        result = await check_artifact_policy(
            artifact_id=artifact_id,
            action=action,
            db=db
        )

        # Log result
        if not result.is_allowed:
            if result.enforcement_mode == EnforcementMode.WARN:
                # Log warning but proceed
                print(f"WARNING: {result.violated_invariants}")
            elif result.enforcement_mode == EnforcementMode.BLOCK:
                # This will raise PolicyGuardException
                pass

    except PolicyGuardException as e:
        # Return structured error response
        raise HTTPException(status_code=403, detail=e.result.to_violation_response())

    # Proceed with artifact update
    return {"status": "updated", "artifact_id": str(artifact_id)}


# Example 3: Batch policy check for PR creation
# =============================================

@app.post("/api/v1/pr")
async def create_pr(
    artifact_ids: List[UUID],
    repository: str,
    db: Session = Depends(get_db)
):
    """
    Create PR with batch policy check.
    """
    # Check policy for all artifacts together
    try:
        result = await check_batch_policy(
            artifact_ids=artifact_ids,
            action="deploy",
            db=db
        )

        print(f"Batch deployment approved: {len(artifact_ids)} artifacts")

    except PolicyGuardException as e:
        # Return violation details
        raise HTTPException(
            status_code=403,
            detail=e.result.to_violation_response()
        )

    # Create PR
    return {
        "pr_url": f"https://github.com/{repository}/pull/123",
        "artifacts_included": artifact_ids
    }


# Example 4: Custom policy evaluation logic
# =========================================

from ..services.policy_evaluator import PolicyEvaluator

@app.get("/api/v1/artifacts/{artifact_id}/policy-check")
async def check_artifact_policies(
    artifact_id: UUID,
    action: str,
    db: Session = Depends(get_db)
):
    """
    Get policy evaluation details without enforcing.

    Useful for UI to show what would happen before user acts.
    """
    evaluator = PolicyEvaluator(db)

    result = await evaluator.evaluate_artifact_deployment(
        artifact_id=artifact_id,
        action=action
    )

    return {
        "is_allowed": result.is_allowed,
        "enforcement_mode": result.enforcement_mode.value,
        "policy_name": result.policy_name,
        "violated_invariants": result.violated_invariants,
        "suggested_actions": result.suggested_actions,
        "blast_radius": {
            "services": result.blast_radius_metrics.affected_services_count,
            "percentage": result.blast_radius_metrics.affected_services_percentage,
            "cost_usd": str(result.blast_radius_metrics.estimated_cost_impact_usd)
        } if result.blast_radius_metrics else None
    }


# Example 5: Get default policy
# =============================

from ..services.policy_evaluator import PolicyEvaluator

@app.get("/api/v1/policies/default")
async def get_default_policy(db: Session = Depends(get_db)):
    """Get or create the default blast radius policy."""
    evaluator = PolicyEvaluator(db)
    policy = await evaluator.get_default_policy()

    return {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "scope": policy.scope.value,
        "invariants": policy.invariants,
        "enforcement_mode": policy.enforcement_mode.value,
        "allowed_actions": policy.allowed_actions
    }


# Example 6: Calculate blast radius without policy
# ===============================================

from ..services.blast_radius import BlastRadiusCalculator

@app.get("/api/v1/artifacts/{artifact_id}/blast-radius")
async def get_blast_radius(
    artifact_id: UUID,
    db: Session = Depends(get_db)
):
    """
    Calculate blast radius for artifact without policy enforcement.

    Useful for showing impact before deployment.
    """
    calculator = BlastRadiusCalculator(db)

    metrics = await calculator.calculate_from_artifact(artifact_id)

    return {
        "affected_services_count": metrics.affected_services_count,
        "affected_services_percentage": metrics.affected_services_percentage,
        "total_services_count": metrics.total_services_count,
        "affected_endpoints_count": metrics.affected_endpoints_count,
        "affected_traffic_percentage": metrics.affected_traffic_percentage,
        "estimated_cost_impact_usd": str(metrics.estimated_cost_impact_usd),
        "affected_service_ids": [str(sid) for sid in metrics.affected_service_ids]
    }


# Example 7: Organization-scoped policy check
# ==========================================

from fastapi import Header

@app.patch("/api/v1/artifacts/{artifact_id}/deploy")
async def deploy_artifact(
    artifact_id: UUID,
    x_organization_id: UUID = Header(...),
    db: Session = Depends(get_db)
):
    """
    Deploy artifact with organization-scoped policy.

    The middleware will extract org_id from headers.
    """
    # Explicit check with org scope
    result = await check_artifact_policy(
        artifact_id=artifact_id,
        action="deploy",
        db=db,
        organization_id=x_organization_id
    )

    if not result.is_allowed and result.enforcement_mode == EnforcementMode.BLOCK:
        raise PolicyGuardException(result)

    # Deploy artifact
    return {"status": "deployed", "artifact_id": str(artifact_id)}


# Example 8: Policy creation endpoint
# ===================================

from ..models.policy import Policy, PolicyScope
from pydantic import BaseModel

class PolicyCreateRequest(BaseModel):
    name: str
    scope: str
    invariants: dict
    enforcement_mode: str
    allowed_actions: List[str]


@app.post("/api/v1/policies")
async def create_policy(
    request: PolicyCreateRequest,
    db: Session = Depends(get_db)
):
    """Create a new governance policy."""
    policy = Policy(
        name=request.name,
        scope=PolicyScope(request.scope),
        scope_id=None,  # Set based on scope type
        invariants=request.invariants,
        allowed_actions=request.allowed_actions,
        enforcement_mode=EnforcementMode(request.enforcement_mode),
        audit_required=True,
        created_by="api_user"
    )

    db.add(policy)
    db.commit()
    db.refresh(policy)

    return {
        "policy_id": str(policy.policy_id),
        "name": policy.name,
        "created_at": policy.created_at.isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
