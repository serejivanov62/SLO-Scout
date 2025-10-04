"""
Policy Guard middleware for artifact deployment governance.

Per api-artifacts.yaml:
- Intercept artifact deployment requests
- Call policy_evaluator to check invariants
- Return 403 PolicyViolation if blocked
- Support enforcement modes: block, warn, audit
"""
from typing import Callable, Optional
from uuid import UUID
import logging

from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.orm import Session

from ..services.policy_evaluator import PolicyEvaluator, PolicyEvaluationResult
from ..models.policy import EnforcementMode

logger = logging.getLogger(__name__)


class PolicyGuardMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to enforce governance policies on artifact operations.

    Intercepts requests to artifact endpoints and evaluates against policies.
    Returns HTTP 403 with structured PolicyViolation response if blocked.
    """

    # Paths that require policy evaluation
    PROTECTED_PATHS = [
        "/api/v1/artifacts/{artifact_id}",  # PATCH for approve/deploy
        "/api/v1/pr",                        # POST for PR creation
    ]

    # Actions that require policy evaluation
    PROTECTED_ACTIONS = ["approve", "deploy", "rollback"]

    def __init__(self, app, get_db: Callable[[], Session]):
        """
        Initialize policy guard middleware.

        Args:
            app: FastAPI application
            get_db: Function to get database session
        """
        super().__init__(app)
        self.get_db = get_db

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Intercept requests and enforce policies if applicable.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response (403 if policy violated, otherwise normal response)
        """
        # Check if this path requires policy evaluation
        if not self._is_protected_path(request.url.path):
            return await call_next(request)

        # Only evaluate on specific HTTP methods
        if request.method not in ["PATCH", "POST"]:
            return await call_next(request)

        try:
            # Extract context from request
            evaluation_context = await self._extract_evaluation_context(request)

            if not evaluation_context:
                # No policy evaluation needed (e.g., wrong action)
                return await call_next(request)

            # Evaluate policy
            db = next(self.get_db())
            try:
                evaluator = PolicyEvaluator(db)
                result = await evaluator.evaluate_artifact_deployment(
                    artifact_id=evaluation_context["artifact_id"],
                    action=evaluation_context["action"],
                    service_id=evaluation_context.get("service_id"),
                    organization_id=evaluation_context.get("organization_id")
                )

                # Check enforcement mode
                if not result.is_allowed:
                    if result.enforcement_mode == EnforcementMode.BLOCK:
                        # Return 403 PolicyViolation response
                        logger.warning(
                            f"Policy Guard BLOCKED request to {request.url.path}: "
                            f"{result.violated_invariants}"
                        )
                        return JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content=result.to_violation_response()
                        )
                    elif result.enforcement_mode == EnforcementMode.WARN:
                        # Log warning but allow request
                        logger.warning(
                            f"Policy Guard WARNING for {request.url.path}: "
                            f"{result.violated_invariants}"
                        )
                        # Add warning header to response
                        request.state.policy_warning = result.to_violation_response()

                # Policy passed or audit mode - proceed
                logger.info(
                    f"Policy Guard ALLOWED request to {request.url.path} "
                    f"(mode: {result.enforcement_mode.value})"
                )

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Policy Guard error: {e}", exc_info=True)
            # Fail open - allow request if policy evaluation fails
            # This prevents policy system from becoming a single point of failure
            logger.warning(f"Policy Guard failed, allowing request: {e}")

        # Proceed with request
        response = await call_next(request)

        # Add warning header if present
        if hasattr(request.state, "policy_warning"):
            response.headers["X-Policy-Warning"] = str(request.state.policy_warning)

        return response

    def _is_protected_path(self, path: str) -> bool:
        """
        Check if path requires policy evaluation.

        Args:
            path: Request path

        Returns:
            True if path is protected
        """
        # Simple path matching (could use path templates for better matching)
        for protected in self.PROTECTED_PATHS:
            # Match exact or with path parameters
            if path.startswith("/api/v1/artifacts/") or path == "/api/v1/pr":
                return True
        return False

    async def _extract_evaluation_context(self, request: Request) -> Optional[dict]:
        """
        Extract policy evaluation context from request.

        Args:
            request: HTTP request

        Returns:
            Dictionary with evaluation context or None if not applicable
        """
        # Handle PATCH /api/v1/artifacts/{artifact_id}
        if request.method == "PATCH" and "/api/v1/artifacts/" in request.url.path:
            # Extract artifact_id from path
            path_parts = request.url.path.split("/")
            artifact_id_str = path_parts[-1]

            try:
                artifact_id = UUID(artifact_id_str)
            except ValueError:
                logger.warning(f"Invalid artifact_id in path: {artifact_id_str}")
                return None

            # Parse request body to get action
            try:
                body = await request.json()
                action = body.get("action")

                if action not in self.PROTECTED_ACTIONS:
                    # Action doesn't require policy evaluation
                    return None

                return {
                    "artifact_id": artifact_id,
                    "action": action,
                    "organization_id": self._extract_org_id(request),
                    "service_id": None  # Could extract from artifact if needed
                }

            except Exception as e:
                logger.error(f"Failed to parse request body: {e}")
                return None

        # Handle POST /api/v1/pr
        elif request.method == "POST" and request.url.path == "/api/v1/pr":
            try:
                body = await request.json()
                artifact_ids = body.get("artifact_ids", [])

                if not artifact_ids:
                    return None

                # For now, evaluate first artifact (could batch evaluate)
                return {
                    "artifact_id": UUID(artifact_ids[0]),
                    "action": "deploy",
                    "organization_id": self._extract_org_id(request),
                    "service_id": None
                }

            except Exception as e:
                logger.error(f"Failed to parse PR request: {e}")
                return None

        return None

    def _extract_org_id(self, request: Request) -> Optional[UUID]:
        """
        Extract organization ID from request context.

        Args:
            request: HTTP request

        Returns:
            Organization UUID or None
        """
        # Check request state (set by auth middleware)
        if hasattr(request.state, "organization_id"):
            return request.state.organization_id

        # Check headers
        org_header = request.headers.get("X-Organization-ID")
        if org_header:
            try:
                return UUID(org_header)
            except ValueError:
                logger.warning(f"Invalid organization ID in header: {org_header}")

        # Check query parameters
        org_param = request.query_params.get("organization_id")
        if org_param:
            try:
                return UUID(org_param)
            except ValueError:
                logger.warning(f"Invalid organization ID in query: {org_param}")

        return None


class PolicyGuardException(HTTPException):
    """
    Custom exception for policy violations.

    Provides structured error response per api-artifacts.yaml PolicyViolation
    """

    def __init__(
        self,
        result: PolicyEvaluationResult,
        status_code: int = status.HTTP_403_FORBIDDEN
    ):
        """
        Initialize policy guard exception.

        Args:
            result: Policy evaluation result
            status_code: HTTP status code (default 403)
        """
        super().__init__(
            status_code=status_code,
            detail=result.to_violation_response()
        )
        self.result = result


async def check_artifact_policy(
    artifact_id: UUID,
    action: str,
    db: Session,
    organization_id: Optional[UUID] = None,
    service_id: Optional[UUID] = None
) -> PolicyEvaluationResult:
    """
    Helper function to check artifact policy in route handlers.

    Can be used directly in endpoints for explicit policy checks.

    Args:
        artifact_id: Artifact UUID
        action: Action being performed
        db: Database session
        organization_id: Optional organization scope
        service_id: Optional service scope

    Returns:
        PolicyEvaluationResult

    Raises:
        PolicyGuardException: If policy is violated and enforcement is BLOCK

    Example:
        ```python
        @app.patch("/api/v1/artifacts/{artifact_id}")
        async def update_artifact(
            artifact_id: UUID,
            action: str,
            db: Session = Depends(get_db)
        ):
            # Check policy
            result = await check_artifact_policy(
                artifact_id=artifact_id,
                action=action,
                db=db
            )

            if not result.is_allowed and result.enforcement_mode == EnforcementMode.BLOCK:
                raise PolicyGuardException(result)

            # Proceed with update
            ...
        ```
    """
    evaluator = PolicyEvaluator(db)

    result = await evaluator.evaluate_artifact_deployment(
        artifact_id=artifact_id,
        action=action,
        service_id=service_id,
        organization_id=organization_id
    )

    if not result.is_allowed and result.enforcement_mode == EnforcementMode.BLOCK:
        raise PolicyGuardException(result)

    return result


async def check_batch_policy(
    artifact_ids: list[UUID],
    action: str,
    db: Session,
    organization_id: Optional[UUID] = None
) -> PolicyEvaluationResult:
    """
    Helper function to check batch artifact policy in route handlers.

    Args:
        artifact_ids: List of artifact UUIDs
        action: Action being performed
        db: Database session
        organization_id: Optional organization scope

    Returns:
        PolicyEvaluationResult

    Raises:
        PolicyGuardException: If policy is violated and enforcement is BLOCK
    """
    evaluator = PolicyEvaluator(db)

    result = await evaluator.evaluate_batch_deployment(
        artifact_ids=artifact_ids,
        action=action,
        organization_id=organization_id
    )

    if not result.is_allowed and result.enforcement_mode == EnforcementMode.BLOCK:
        raise PolicyGuardException(result)

    return result
