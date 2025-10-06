from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
from .schemas import Service, ServiceCreate

router = APIRouter(prefix="/api/v1/services", tags=["services"])

# Mock data for development
MOCK_SERVICES = [
    {
        "id": "svc-001",
        "name": "payments-api",
        "environment": "production",
        "owner_team": "Platform Team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090",
            "traces": "http://jaeger:16686"
        },
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "status": "active"
    },
    {
        "id": "svc-002",
        "name": "auth-service",
        "environment": "production",
        "owner_team": "Security Team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090"
        },
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "status": "active"
    },
    {
        "id": "svc-003",
        "name": "user-profile",
        "environment": "staging",
        "owner_team": "Users Team",
        "telemetry_endpoints": {},
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
        "status": "active"
    }
]


@router.get("", response_model=List[dict])
async def list_services():
    """List all services"""
    return MOCK_SERVICES


@router.get("/{service_id}", response_model=dict)
async def get_service(service_id: str):
    """Get service by ID"""
    for service in MOCK_SERVICES:
        if service["id"] == service_id:
            return service
    raise HTTPException(status_code=404, detail="Service not found")


@router.post("", response_model=dict, status_code=201)
async def create_service(service: dict):
    """Create a new service"""
    new_service = {
        "id": f"svc-{len(MOCK_SERVICES) + 1:03d}",
        **service,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    MOCK_SERVICES.append(new_service)
    return new_service


@router.delete("/{service_id}", status_code=204)
async def delete_service(service_id: str):
    """Delete a service"""
    global MOCK_SERVICES
    MOCK_SERVICES = [s for s in MOCK_SERVICES if s["id"] != service_id]
    return None
