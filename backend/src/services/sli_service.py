"""
SLI Service - Service Level Indicator management with approval workflow.

Provides CRUD operations and approval workflow for SLI entities.
"""
from datetime import datetime
from typing import List, Optional
from uuid import UUID
from decimal import Decimal
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.sli import SLI
from src.models.user_journey import UserJourney

logger = logging.getLogger(__name__)


class SLINotFoundError(Exception):
    """Raised when an SLI is not found."""
    pass


class SLIAlreadyApprovedException(Exception):
    """Raised when attempting to approve an already approved SLI."""
    pass


class InvalidConfidenceScoreError(Exception):
    """Raised when confidence score is out of valid range."""
    pass


class SLIService:
    """
    SLI Service for managing Service Level Indicators with approval workflow.

    Implements repository pattern with approval workflow for human validation
    of AI-recommended SLIs.
    """

    def __init__(self, db_session: Session):
        """
        Initialize SLI service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    async def create(
        self,
        journey_id: UUID,
        name: str,
        promql_query: str,
        confidence_score: Decimal,
        description: Optional[str] = None
    ) -> SLI:
        """
        Create a new SLI.

        Args:
            journey_id: UUID of the associated user journey
            name: SLI name
            promql_query: PromQL query for the SLI
            confidence_score: AI confidence score (0.0-1.0)
            description: Optional SLI description

        Returns:
            Created SLI instance

        Raises:
            ValueError: If validation fails
            InvalidConfidenceScoreError: If confidence score is out of range
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("SLI name cannot be empty")

        if not promql_query or not promql_query.strip():
            raise ValueError("PromQL query cannot be empty")

        if confidence_score < 0 or confidence_score > 1:
            raise InvalidConfidenceScoreError(
                f"Confidence score must be between 0 and 1, got {confidence_score}"
            )

        # Verify journey exists
        journey = self.db.query(UserJourney).filter(
            UserJourney.journey_id == journey_id
        ).first()
        if not journey:
            raise ValueError(f"Journey {journey_id} not found")

        # Create SLI instance
        sli = SLI(
            journey_id=journey_id,
            name=name.strip(),
            description=description.strip() if description else None,
            promql_query=promql_query.strip(),
            confidence_score=confidence_score,
            approved=False
        )

        try:
            self.db.add(sli)
            self.db.flush()
            logger.info(
                f"Created SLI: {sli.name} (ID: {sli.sli_id}, "
                f"confidence: {confidence_score:.3f})"
            )
            return sli
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create SLI: {str(e)}")
            raise

    async def get(self, sli_id: UUID) -> SLI:
        """
        Get an SLI by ID.

        Args:
            sli_id: UUID of the SLI

        Returns:
            SLI instance

        Raises:
            SLINotFoundError: If SLI not found
        """
        sli = self.db.query(SLI).filter(SLI.sli_id == sli_id).first()

        if not sli:
            raise SLINotFoundError(f"SLI with ID {sli_id} not found")

        logger.debug(f"Retrieved SLI: {sli.name} ({sli.sli_id})")
        return sli

    async def list(
        self,
        journey_id: Optional[UUID] = None,
        approved: Optional[bool] = None,
        min_confidence: Optional[Decimal] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SLI]:
        """
        List SLIs with optional filters.

        Args:
            journey_id: Filter by journey ID
            approved: Filter by approval status
            min_confidence: Minimum confidence score threshold
            limit: Maximum number of results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of SLI instances
        """
        query = select(SLI).order_by(SLI.created_at.desc())

        if journey_id:
            query = query.where(SLI.journey_id == journey_id)

        if approved is not None:
            query = query.where(SLI.approved == approved)

        if min_confidence is not None:
            query = query.where(SLI.confidence_score >= min_confidence)

        query = query.limit(limit).offset(offset)

        result = self.db.execute(query)
        slis = list(result.scalars().all())

        logger.debug(
            f"Listed {len(slis)} SLIs "
            f"(journey={journey_id}, approved={approved}, "
            f"min_confidence={min_confidence})"
        )

        return slis

    async def approve(
        self,
        sli_id: UUID,
        approved_by: str
    ) -> SLI:
        """
        Approve an SLI.

        Sets approved=True, approved_by, and approved_at timestamp.

        Args:
            sli_id: UUID of the SLI to approve
            approved_by: Username/email of the approver

        Returns:
            Approved SLI instance

        Raises:
            SLINotFoundError: If SLI not found
            SLIAlreadyApprovedException: If SLI is already approved
            ValueError: If approved_by is empty
        """
        if not approved_by or not approved_by.strip():
            raise ValueError("Approver username/email cannot be empty")

        sli = await self.get(sli_id)

        if sli.approved:
            raise SLIAlreadyApprovedException(
                f"SLI {sli_id} is already approved by {sli.approved_by} "
                f"at {sli.approved_at}"
            )

        # Set approval fields
        sli.approved = True
        sli.approved_by = approved_by.strip()
        sli.approved_at = datetime.utcnow()

        self.db.flush()

        logger.info(
            f"Approved SLI: {sli.name} ({sli.sli_id}) by {approved_by}"
        )

        return sli

    async def unapprove(self, sli_id: UUID) -> SLI:
        """
        Revoke approval of an SLI.

        Sets approved=False and clears approved_by and approved_at.

        Args:
            sli_id: UUID of the SLI to unapprove

        Returns:
            Unapproved SLI instance

        Raises:
            SLINotFoundError: If SLI not found
        """
        sli = await self.get(sli_id)

        if not sli.approved:
            logger.warning(f"SLI {sli_id} is not approved, no action taken")
            return sli

        # Clear approval fields
        sli.approved = False
        sli.approved_by = None
        sli.approved_at = None

        self.db.flush()

        logger.info(f"Revoked approval for SLI: {sli.name} ({sli.sli_id})")

        return sli

    async def update(
        self,
        sli_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        promql_query: Optional[str] = None,
        confidence_score: Optional[Decimal] = None
    ) -> SLI:
        """
        Update an SLI.

        Note: Updating an approved SLI will revoke its approval status.

        Args:
            sli_id: UUID of the SLI to update
            name: New name (optional)
            description: New description (optional)
            promql_query: New PromQL query (optional)
            confidence_score: New confidence score (optional)

        Returns:
            Updated SLI instance

        Raises:
            SLINotFoundError: If SLI not found
            ValueError: If validation fails
            InvalidConfidenceScoreError: If confidence score is out of range
        """
        sli = await self.get(sli_id)

        updated = False

        if name is not None:
            if not name.strip():
                raise ValueError("SLI name cannot be empty")
            sli.name = name.strip()
            updated = True

        if description is not None:
            sli.description = description.strip() if description else None
            updated = True

        if promql_query is not None:
            if not promql_query.strip():
                raise ValueError("PromQL query cannot be empty")
            sli.promql_query = promql_query.strip()
            updated = True

        if confidence_score is not None:
            if confidence_score < 0 or confidence_score > 1:
                raise InvalidConfidenceScoreError(
                    f"Confidence score must be between 0 and 1, got {confidence_score}"
                )
            sli.confidence_score = confidence_score
            updated = True

        # Revoke approval if SLI was modified
        if updated and sli.approved:
            logger.warning(
                f"SLI {sli_id} was modified, revoking approval from {sli.approved_by}"
            )
            sli.approved = False
            sli.approved_by = None
            sli.approved_at = None

        if updated:
            self.db.flush()
            logger.info(f"Updated SLI: {sli.name} ({sli.sli_id})")

        return sli

    async def delete(self, sli_id: UUID) -> None:
        """
        Delete an SLI.

        This will cascade delete all related SLOs.

        Args:
            sli_id: UUID of the SLI to delete

        Raises:
            SLINotFoundError: If SLI not found
        """
        sli = await self.get(sli_id)

        sli_name = sli.name
        self.db.delete(sli)
        self.db.flush()

        logger.info(f"Deleted SLI: {sli_name} ({sli_id})")

    async def count_by_journey(
        self,
        journey_id: UUID,
        approved: Optional[bool] = None
    ) -> int:
        """
        Count SLIs for a journey.

        Args:
            journey_id: UUID of the journey
            approved: Filter by approval status

        Returns:
            Count of SLIs
        """
        query = self.db.query(SLI).filter(SLI.journey_id == journey_id)

        if approved is not None:
            query = query.filter(SLI.approved == approved)

        count = query.count()

        logger.debug(
            f"Counted {count} SLIs for journey {journey_id} "
            f"(approved={approved})"
        )

        return count

    async def get_pending_approvals(
        self,
        min_confidence: Optional[Decimal] = None,
        limit: int = 100
    ) -> List[SLI]:
        """
        Get SLIs pending approval.

        Args:
            min_confidence: Minimum confidence score threshold
            limit: Maximum number of results

        Returns:
            List of unapproved SLI instances ordered by confidence score
        """
        query = select(SLI).where(
            SLI.approved == False
        ).order_by(SLI.confidence_score.desc(), SLI.created_at.desc())

        if min_confidence is not None:
            query = query.where(SLI.confidence_score >= min_confidence)

        query = query.limit(limit)

        result = self.db.execute(query)
        slis = list(result.scalars().all())

        logger.debug(
            f"Retrieved {len(slis)} pending SLIs "
            f"(min_confidence={min_confidence})"
        )

        return slis
