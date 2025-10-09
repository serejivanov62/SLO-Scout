"""
SLO Service - Service Level Objective management with error budget calculation.

Provides CRUD operations and error budget calculation for SLO entities.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from decimal import Decimal
import logging

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.models.slo import SLO, ThresholdVariantEnum
from src.models.sli import SLI

logger = logging.getLogger(__name__)


class SLONotFoundError(Exception):
    """Raised when an SLO is not found."""
    pass


class InvalidTargetPercentageError(Exception):
    """Raised when target percentage is out of valid range."""
    pass


class ErrorBudget:
    """Error budget calculation result."""

    def __init__(
        self,
        target_percentage: Decimal,
        time_window: str,
        allowed_error_rate: Decimal,
        allowed_downtime_seconds: int,
        threshold_variant: ThresholdVariantEnum
    ):
        self.target_percentage = target_percentage
        self.time_window = time_window
        self.allowed_error_rate = allowed_error_rate
        self.allowed_downtime_seconds = allowed_downtime_seconds
        self.threshold_variant = threshold_variant

    def to_dict(self) -> Dict[str, any]:
        """Convert error budget to dictionary."""
        return {
            "target_percentage": float(self.target_percentage),
            "time_window": self.time_window,
            "allowed_error_rate": float(self.allowed_error_rate),
            "allowed_downtime_seconds": self.allowed_downtime_seconds,
            "allowed_downtime_minutes": self.allowed_downtime_seconds / 60,
            "allowed_downtime_hours": self.allowed_downtime_seconds / 3600,
            "threshold_variant": self.threshold_variant.value
        }


class SLOService:
    """
    SLO Service for managing Service Level Objectives.

    Provides CRUD operations and error budget calculations based on
    target percentages and time windows.
    """

    # Time window to seconds mapping
    TIME_WINDOW_SECONDS = {
        "1h": 3600,
        "24h": 86400,
        "7d": 604800,
        "30d": 2592000,
        "90d": 7776000
    }

    def __init__(self, db_session: Session):
        """
        Initialize SLO service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    async def create(
        self,
        sli_id: UUID,
        name: str,
        target_percentage: Decimal,
        time_window: str,
        threshold_variant: ThresholdVariantEnum = ThresholdVariantEnum.BALANCED
    ) -> SLO:
        """
        Create a new SLO.

        Args:
            sli_id: UUID of the associated SLI
            name: SLO name
            target_percentage: Target percentage (0.00-100.00)
            time_window: Time window (e.g., "30d", "7d", "24h")
            threshold_variant: Alert threshold variant

        Returns:
            Created SLO instance

        Raises:
            ValueError: If validation fails
            InvalidTargetPercentageError: If target percentage is out of range
        """
        # Validate inputs
        if not name or not name.strip():
            raise ValueError("SLO name cannot be empty")

        if target_percentage < 0 or target_percentage > 100:
            raise InvalidTargetPercentageError(
                f"Target percentage must be between 0 and 100, got {target_percentage}"
            )

        if time_window not in self.TIME_WINDOW_SECONDS:
            raise ValueError(
                f"Invalid time window: {time_window}. "
                f"Must be one of: {', '.join(self.TIME_WINDOW_SECONDS.keys())}"
            )

        # Verify SLI exists and is approved
        sli = self.db.query(SLI).filter(SLI.sli_id == sli_id).first()
        if not sli:
            raise ValueError(f"SLI {sli_id} not found")

        if not sli.approved:
            logger.warning(
                f"Creating SLO for unapproved SLI {sli_id}. "
                "This SLO will only be useful after SLI approval."
            )

        # Create SLO instance
        slo = SLO(
            sli_id=sli_id,
            name=name.strip(),
            target_percentage=target_percentage,
            time_window=time_window,
            threshold_variant=threshold_variant
        )

        try:
            self.db.add(slo)
            self.db.flush()
            logger.info(
                f"Created SLO: {slo.name} (ID: {slo.slo_id}, "
                f"target: {target_percentage}%, window: {time_window})"
            )
            return slo
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create SLO: {str(e)}")
            raise

    async def get(self, slo_id: UUID) -> SLO:
        """
        Get an SLO by ID.

        Args:
            slo_id: UUID of the SLO

        Returns:
            SLO instance

        Raises:
            SLONotFoundError: If SLO not found
        """
        slo = self.db.query(SLO).filter(SLO.slo_id == slo_id).first()

        if not slo:
            raise SLONotFoundError(f"SLO with ID {slo_id} not found")

        logger.debug(f"Retrieved SLO: {slo.name} ({slo.slo_id})")
        return slo

    async def list(
        self,
        sli_id: Optional[UUID] = None,
        threshold_variant: Optional[ThresholdVariantEnum] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SLO]:
        """
        List SLOs with optional filters.

        Args:
            sli_id: Filter by SLI ID
            threshold_variant: Filter by threshold variant
            limit: Maximum number of results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of SLO instances
        """
        query = select(SLO).order_by(SLO.created_at.desc())

        if sli_id:
            query = query.where(SLO.sli_id == sli_id)

        if threshold_variant:
            query = query.where(SLO.threshold_variant == threshold_variant)

        query = query.limit(limit).offset(offset)

        result = self.db.execute(query)
        slos = list(result.scalars().all())

        logger.debug(
            f"Listed {len(slos)} SLOs "
            f"(sli={sli_id}, variant={threshold_variant})"
        )

        return slos

    async def update(
        self,
        slo_id: UUID,
        name: Optional[str] = None,
        target_percentage: Optional[Decimal] = None,
        time_window: Optional[str] = None,
        threshold_variant: Optional[ThresholdVariantEnum] = None
    ) -> SLO:
        """
        Update an SLO.

        Args:
            slo_id: UUID of the SLO to update
            name: New name (optional)
            target_percentage: New target percentage (optional)
            time_window: New time window (optional)
            threshold_variant: New threshold variant (optional)

        Returns:
            Updated SLO instance

        Raises:
            SLONotFoundError: If SLO not found
            ValueError: If validation fails
            InvalidTargetPercentageError: If target percentage is out of range
        """
        slo = await self.get(slo_id)

        if name is not None:
            if not name.strip():
                raise ValueError("SLO name cannot be empty")
            slo.name = name.strip()

        if target_percentage is not None:
            if target_percentage < 0 or target_percentage > 100:
                raise InvalidTargetPercentageError(
                    f"Target percentage must be between 0 and 100, got {target_percentage}"
                )
            slo.target_percentage = target_percentage

        if time_window is not None:
            if time_window not in self.TIME_WINDOW_SECONDS:
                raise ValueError(
                    f"Invalid time window: {time_window}. "
                    f"Must be one of: {', '.join(self.TIME_WINDOW_SECONDS.keys())}"
                )
            slo.time_window = time_window

        if threshold_variant is not None:
            slo.threshold_variant = threshold_variant

        self.db.flush()
        logger.info(f"Updated SLO: {slo.name} ({slo.slo_id})")

        return slo

    async def delete(self, slo_id: UUID) -> None:
        """
        Delete an SLO.

        This will cascade delete all related artifacts.

        Args:
            slo_id: UUID of the SLO to delete

        Raises:
            SLONotFoundError: If SLO not found
        """
        slo = await self.get(slo_id)

        slo_name = slo.name
        self.db.delete(slo)
        self.db.flush()

        logger.info(f"Deleted SLO: {slo_name} ({slo_id})")

    async def calculate_error_budget(self, slo_id: UUID) -> ErrorBudget:
        """
        Calculate error budget for an SLO.

        The error budget is the allowed error rate and downtime based on
        the target percentage and time window.

        Formula:
        - Allowed error rate = 100% - target_percentage
        - Allowed downtime = time_window_seconds * (allowed_error_rate / 100)

        Args:
            slo_id: UUID of the SLO

        Returns:
            ErrorBudget instance with calculated values

        Raises:
            SLONotFoundError: If SLO not found
        """
        slo = await self.get(slo_id)

        # Calculate allowed error rate
        allowed_error_rate = Decimal("100") - slo.target_percentage

        # Get time window in seconds
        time_window_seconds = self.TIME_WINDOW_SECONDS.get(slo.time_window)
        if not time_window_seconds:
            raise ValueError(f"Unknown time window: {slo.time_window}")

        # Calculate allowed downtime in seconds
        allowed_downtime_seconds = int(
            time_window_seconds * float(allowed_error_rate) / 100
        )

        error_budget = ErrorBudget(
            target_percentage=slo.target_percentage,
            time_window=slo.time_window,
            allowed_error_rate=allowed_error_rate,
            allowed_downtime_seconds=allowed_downtime_seconds,
            threshold_variant=slo.threshold_variant
        )

        logger.debug(
            f"Calculated error budget for SLO {slo_id}: "
            f"{allowed_error_rate}% error rate, "
            f"{allowed_downtime_seconds}s downtime"
        )

        return error_budget

    async def get_burn_rate_thresholds(
        self,
        slo_id: UUID
    ) -> Dict[str, Decimal]:
        """
        Get burn rate thresholds based on threshold variant.

        Burn rate is how fast the error budget is being consumed.
        Based on Google SRE Workbook multiwindow alerting strategy.

        Args:
            slo_id: UUID of the SLO

        Returns:
            Dictionary with burn rate thresholds for different time windows

        Raises:
            SLONotFoundError: If SLO not found
        """
        slo = await self.get(slo_id)

        # Define burn rate thresholds per variant
        # Based on Google SRE Workbook Chapter 5
        thresholds = {
            ThresholdVariantEnum.CONSERVATIVE: {
                "1h": Decimal("20.0"),   # 20x burn rate for 1-hour window
                "6h": Decimal("6.0"),    # 6x burn rate for 6-hour window
                "24h": Decimal("3.0"),   # 3x burn rate for 24-hour window
            },
            ThresholdVariantEnum.BALANCED: {
                "1h": Decimal("14.4"),   # 14.4x burn rate for 1-hour window
                "6h": Decimal("6.0"),    # 6x burn rate for 6-hour window
                "24h": Decimal("3.0"),   # 3x burn rate for 24-hour window
            },
            ThresholdVariantEnum.AGGRESSIVE: {
                "1h": Decimal("10.0"),   # 10x burn rate for 1-hour window
                "6h": Decimal("4.0"),    # 4x burn rate for 6-hour window
                "24h": Decimal("2.0"),   # 2x burn rate for 24-hour window
            }
        }

        variant_thresholds = thresholds[slo.threshold_variant]

        logger.debug(
            f"Retrieved burn rate thresholds for SLO {slo_id} "
            f"(variant={slo.threshold_variant.value})"
        )

        return variant_thresholds

    async def count_by_sli(self, sli_id: UUID) -> int:
        """
        Count SLOs for an SLI.

        Args:
            sli_id: UUID of the SLI

        Returns:
            Count of SLOs
        """
        count = self.db.query(SLO).filter(SLO.sli_id == sli_id).count()

        logger.debug(f"Counted {count} SLOs for SLI {sli_id}")
        return count

    async def get_recommended_variants(
        self,
        sli_id: UUID
    ) -> List[Tuple[ThresholdVariantEnum, str]]:
        """
        Get recommended threshold variants for an SLI.

        Provides guidance on which threshold variant to use based on
        the SLI's characteristics.

        Args:
            sli_id: UUID of the SLI

        Returns:
            List of (variant, recommendation) tuples

        Raises:
            ValueError: If SLI not found
        """
        sli = self.db.query(SLI).filter(SLI.sli_id == sli_id).first()
        if not sli:
            raise ValueError(f"SLI {sli_id} not found")

        recommendations = [
            (
                ThresholdVariantEnum.CONSERVATIVE,
                "Use for critical services where false positives are expensive. "
                "Slower alerting, fewer pages."
            ),
            (
                ThresholdVariantEnum.BALANCED,
                "Default choice based on Google SRE best practices. "
                "Good balance between alert latency and noise."
            ),
            (
                ThresholdVariantEnum.AGGRESSIVE,
                "Use for rapidly-changing services or development environments. "
                "Faster alerting, more potential noise."
            )
        ]

        logger.debug(f"Retrieved threshold variant recommendations for SLI {sli_id}")
        return recommendations
