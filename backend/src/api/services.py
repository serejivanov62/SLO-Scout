"""
Services API router - Service registration and management endpoints
Implements services-api.yaml contract
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..models.service import Service, EnvironmentEnum, ServiceStatusEnum
from .deps import get_db

# Create router
router = APIRouter(prefix="/api/v1/services", tags=["Services"])


# Pydantic schemas per contract
class ServiceCreate(BaseModel):
    """Service creation request schema"""
    name: str = Field(..., min_length=1, max_length=255)
    environment: str = Field(..., pattern="^(prod|staging|dev)$")
    owner_team: str = Field(..., min_length=1, max_length=255)
    telemetry_endpoints: Dict[str, str] = Field(...)
    label_mappings: Dict[str, Dict[str, str]] = Field(...)


class ServiceUpdate(BaseModel):
    """Service update request schema"""
    owner_team: Optional[str] = Field(None, min_length=1, max_length=255)
    telemetry_endpoints: Optional[Dict[str, str]] = None
    label_mappings: Optional[Dict[str, Dict[str, str]]] = None
    status: Optional[str] = Field(None, pattern="^(active|inactive|archived)$")


class ServiceResponse(BaseModel):
    """Service response schema"""
    id: str
    name: str
    environment: str
    owner_team: str
    telemetry_endpoints: Dict[str, str]
    label_mappings: Dict[str, Dict[str, str]]
    created_at: str
    updated_at: str
    status: str

    @classmethod
    def from_orm(cls, service: Service):
        """Convert SQLAlchemy model to Pydantic schema"""
        return cls(
            id=str(service.id),
            name=service.name,
            environment=service.environment.value,
            owner_team=service.owner_team,
            telemetry_endpoints=service.telemetry_endpoints,
            label_mappings=service.label_mappings,
            created_at=service.created_at.isoformat(),
            updated_at=service.updated_at.isoformat(),
            status=service.status.value
        )


class ServiceListResponse(BaseModel):
    """Service list response schema"""
    services: list[ServiceResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None


# Route handlers
@router.get("", response_model=ServiceListResponse, status_code=status.HTTP_200_OK)
async def list_services(
    environment: Optional[str] = Query(None, pattern="^(prod|staging|dev)$"),
    service_status: Optional[str] = Query(None, alias="status", pattern="^(active|inactive|archived)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
) -> ServiceListResponse:
    """List all services with optional filtering"""
    query = db.query(Service)

    # Apply filters
    if environment:
        query = query.filter(Service.environment == EnvironmentEnum(environment))

    if service_status:
        query = query.filter(Service.status == ServiceStatusEnum(service_status))

    # Get total count before pagination
    total = query.count()

    # Apply pagination
    services = query.offset(offset).limit(limit).all()

    return ServiceListResponse(
        services=[ServiceResponse.from_orm(s) for s in services],
        total=total,
        limit=limit,
        offset=offset
    )


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    service_data: ServiceCreate,
    db: Session = Depends(get_db)
) -> ServiceResponse:
    """Create a new service"""
    # Check for duplicate name+environment
    existing = db.query(Service).filter(
        Service.name == service_data.name,
        Service.environment == EnvironmentEnum(service_data.environment)
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "DUPLICATE_SERVICE",
                "message": f"Service with name '{service_data.name}' already exists in environment '{service_data.environment}'",
                "details": {"service_id": str(existing.id)}
            }
        )

    # Create new service
    new_service = Service(
        name=service_data.name,
        environment=EnvironmentEnum(service_data.environment),
        owner_team=service_data.owner_team,
        telemetry_endpoints=service_data.telemetry_endpoints,
        label_mappings=service_data.label_mappings
    )

    db.add(new_service)
    db.commit()
    db.refresh(new_service)

    return ServiceResponse.from_orm(new_service)


@router.get("/{service_id}", response_model=ServiceResponse, status_code=status.HTTP_200_OK)
async def get_service(
    service_id: UUID,
    db: Session = Depends(get_db)
) -> ServiceResponse:
    """Get service by ID"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Service with ID '{service_id}' not found",
                "details": {}
            }
        )

    return ServiceResponse.from_orm(service)


@router.patch("/{service_id}", response_model=ServiceResponse, status_code=status.HTTP_200_OK)
async def update_service(
    service_id: UUID,
    update_data: ServiceUpdate,
    db: Session = Depends(get_db)
) -> ServiceResponse:
    """Update service configuration"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Service with ID '{service_id}' not found",
                "details": {}
            }
        )

    # Apply updates
    if update_data.owner_team is not None:
        service.owner_team = update_data.owner_team

    if update_data.telemetry_endpoints is not None:
        service.telemetry_endpoints = update_data.telemetry_endpoints

    if update_data.label_mappings is not None:
        service.label_mappings = update_data.label_mappings

    if update_data.status is not None:
        service.status = ServiceStatusEnum(update_data.status)

    # Update timestamp
    service.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(service)

    return ServiceResponse.from_orm(service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: UUID,
    hard_delete: bool = Query(False),
    db: Session = Depends(get_db)
) -> None:
    """Delete or archive a service"""
    service = db.query(Service).filter(Service.id == service_id).first()

    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "SERVICE_NOT_FOUND",
                "message": f"Service with ID '{service_id}' not found",
                "details": {}
            }
        )

    if hard_delete:
        # Permanently delete (cascades to related data)
        db.delete(service)
    else:
        # Archive only
        service.status = ServiceStatusEnum.ARCHIVED
        service.updated_at = datetime.now(timezone.utc)

    db.commit()
