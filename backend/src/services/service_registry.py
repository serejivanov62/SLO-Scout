"""
Service Registry - CRUD operations for Service entities.

Provides repository pattern for managing services with telemetry connection details.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.service import Service, EnvironmentEnum, ServiceStatusEnum

logger = logging.getLogger(__name__)


class ServiceNotFoundError(Exception):
    """Raised when a service is not found."""
    pass


class ServiceAlreadyExistsError(Exception):
    """Raised when a service with the same name and environment already exists."""
    pass


class ServiceRegistry:
    """
    Service Registry for CRUD operations on Service entities.

    Implements repository pattern with dependency injection for database session.
    """

    def __init__(self, db_session: Session):
        """
        Initialize service registry.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    async def create(
        self,
        name: str,
        environment: EnvironmentEnum,
        owner_team: str,
        telemetry_endpoints: dict,
        label_mappings: dict,
        status: ServiceStatusEnum = ServiceStatusEnum.ACTIVE
    ) -> Service:
        """
        Create a new service.

        Args:
            name: Service name
            environment: Service environment (prod/staging/dev)
            owner_team: Team responsible for the service
            telemetry_endpoints: Telemetry system endpoints mapping
            label_mappings: Label mappings for each telemetry system
            status: Service status (default: ACTIVE)

        Returns:
            Created Service instance

        Raises:
            ServiceAlreadyExistsError: If service with name+environment already exists
            ValueError: If validation fails
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("Service name cannot be empty")

        if not owner_team or not owner_team.strip():
            raise ValueError("Owner team cannot be empty")

        if not telemetry_endpoints:
            raise ValueError("Telemetry endpoints cannot be empty")

        if not label_mappings:
            raise ValueError("Label mappings cannot be empty")

        # Create service instance
        service = Service(
            name=name.strip(),
            environment=environment,
            owner_team=owner_team.strip(),
            telemetry_endpoints=telemetry_endpoints,
            label_mappings=label_mappings,
            status=status
        )

        try:
            self.db.add(service)
            self.db.flush()
            logger.info(
                f"Created service: {service.name} ({service.environment}) "
                f"with ID {service.id}"
            )
            return service
        except IntegrityError as e:
            self.db.rollback()
            if "uq_services_name_environment" in str(e):
                raise ServiceAlreadyExistsError(
                    f"Service '{name}' in environment '{environment}' already exists"
                )
            raise

    async def list(
        self,
        environment: Optional[EnvironmentEnum] = None,
        status: Optional[ServiceStatusEnum] = None,
        owner_team: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Service]:
        """
        List services with optional filters.

        Args:
            environment: Filter by environment
            status: Filter by status
            owner_team: Filter by owner team
            limit: Maximum number of results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of Service instances
        """
        query = select(Service).order_by(Service.created_at.desc())

        if environment:
            query = query.where(Service.environment == environment)

        if status:
            query = query.where(Service.status == status)

        if owner_team:
            query = query.where(Service.owner_team == owner_team)

        query = query.limit(limit).offset(offset)

        result = self.db.execute(query)
        services = list(result.scalars().all())

        logger.debug(
            f"Listed {len(services)} services "
            f"(env={environment}, status={status}, team={owner_team})"
        )

        return services

    async def get(self, service_id: UUID) -> Service:
        """
        Get a service by ID.

        Args:
            service_id: UUID of the service

        Returns:
            Service instance

        Raises:
            ServiceNotFoundError: If service not found
        """
        service = self.db.query(Service).filter(Service.id == service_id).first()

        if not service:
            raise ServiceNotFoundError(f"Service with ID {service_id} not found")

        logger.debug(f"Retrieved service: {service.name} ({service.id})")
        return service

    async def get_by_name(
        self,
        name: str,
        environment: EnvironmentEnum
    ) -> Optional[Service]:
        """
        Get a service by name and environment.

        Args:
            name: Service name
            environment: Service environment

        Returns:
            Service instance or None if not found
        """
        service = self.db.query(Service).filter(
            Service.name == name,
            Service.environment == environment
        ).first()

        if service:
            logger.debug(f"Retrieved service by name: {name} ({environment})")
        else:
            logger.debug(f"Service not found: {name} ({environment})")

        return service

    async def update(
        self,
        service_id: UUID,
        owner_team: Optional[str] = None,
        telemetry_endpoints: Optional[dict] = None,
        label_mappings: Optional[dict] = None,
        status: Optional[ServiceStatusEnum] = None
    ) -> Service:
        """
        Update a service.

        Args:
            service_id: UUID of the service to update
            owner_team: New owner team (optional)
            telemetry_endpoints: New telemetry endpoints (optional)
            label_mappings: New label mappings (optional)
            status: New status (optional)

        Returns:
            Updated Service instance

        Raises:
            ServiceNotFoundError: If service not found
            ValueError: If validation fails
        """
        service = await self.get(service_id)

        if owner_team is not None:
            if not owner_team.strip():
                raise ValueError("Owner team cannot be empty")
            service.owner_team = owner_team.strip()

        if telemetry_endpoints is not None:
            if not telemetry_endpoints:
                raise ValueError("Telemetry endpoints cannot be empty")
            service.telemetry_endpoints = telemetry_endpoints

        if label_mappings is not None:
            if not label_mappings:
                raise ValueError("Label mappings cannot be empty")
            service.label_mappings = label_mappings

        if status is not None:
            service.status = status

        service.updated_at = datetime.utcnow()
        self.db.flush()

        logger.info(f"Updated service: {service.name} ({service.id})")
        return service

    async def delete(self, service_id: UUID) -> None:
        """
        Delete a service (soft delete by setting status to ARCHIVED).

        Args:
            service_id: UUID of the service to delete

        Raises:
            ServiceNotFoundError: If service not found
        """
        service = await self.get(service_id)

        service.status = ServiceStatusEnum.ARCHIVED
        service.updated_at = datetime.utcnow()
        self.db.flush()

        logger.info(f"Archived service: {service.name} ({service.id})")

    async def hard_delete(self, service_id: UUID) -> None:
        """
        Permanently delete a service from the database.

        Warning: This will cascade delete all related entities
        (telemetry events, capsules, user journeys, etc.)

        Args:
            service_id: UUID of the service to delete

        Raises:
            ServiceNotFoundError: If service not found
        """
        service = await self.get(service_id)

        service_name = service.name
        self.db.delete(service)
        self.db.flush()

        logger.warning(
            f"Hard deleted service: {service_name} ({service_id}) "
            "and all related entities"
        )

    async def count(
        self,
        environment: Optional[EnvironmentEnum] = None,
        status: Optional[ServiceStatusEnum] = None
    ) -> int:
        """
        Count services with optional filters.

        Args:
            environment: Filter by environment
            status: Filter by status

        Returns:
            Count of services
        """
        query = select(Service)

        if environment:
            query = query.where(Service.environment == environment)

        if status:
            query = query.where(Service.status == status)

        count = self.db.query(Service).filter(
            *query.whereclause if hasattr(query, 'whereclause') else []
        ).count()

        logger.debug(f"Counted {count} services (env={environment}, status={status})")
        return count
