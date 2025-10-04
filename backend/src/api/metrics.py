"""
Metrics API Endpoint (T142 Integration)

Provides Prometheus metrics endpoint for SLO-Scout self-observability.
Per spec.md FR-024: Expose metrics at /metrics endpoint.
"""
from fastapi import APIRouter, Response
from ..observability.metrics import get_metrics

router = APIRouter(prefix="/metrics", tags=["observability"])


@router.get("", response_class=Response)
async def metrics_endpoint() -> Response:
    """
    Prometheus metrics endpoint.

    Exposes all SLO-Scout self-observability metrics in Prometheus format.

    Per FR-024: Exports metrics including:
    - ingest_lag_seconds
    - embedding_queue_length
    - vector_query_latency
    - llm_calls_per_min
    - daily_llm_spend_usd

    Returns:
        Response: Prometheus-formatted metrics with appropriate content type
    """
    metrics = get_metrics()
    return Response(
        content=metrics.export(),
        media_type=metrics.get_content_type()
    )


@router.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint for metrics subsystem.

    Returns:
        dict: Health status
    """
    return {
        "status": "healthy",
        "component": "metrics",
        "metrics_enabled": True
    }
