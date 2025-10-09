"""
Analysis Service - Job creation, status tracking, and async task dispatch.

Manages background analysis jobs for SLI/SLO discovery and artifact generation.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
from enum import Enum
import logging
import asyncio

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Analysis job status enumeration."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(str, Enum):
    """Analysis job type enumeration."""
    SLI_DISCOVERY = "sli_discovery"
    SLO_GENERATION = "slo_generation"
    ARTIFACT_GENERATION = "artifact_generation"
    JOURNEY_DISCOVERY = "journey_discovery"


class AnalysisJobNotFoundError(Exception):
    """Raised when an analysis job is not found."""
    pass


class AnalysisJob:
    """
    In-memory representation of an analysis job.

    Note: For production, this should be backed by a database table or
    distributed task queue (Celery, RQ, etc.)
    """

    def __init__(
        self,
        job_id: UUID,
        job_type: JobType,
        service_id: UUID,
        parameters: Dict[str, Any],
        status: JobStatus = JobStatus.PENDING,
        created_at: Optional[datetime] = None
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.service_id = service_id
        self.parameters = parameters
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.result: Optional[Dict[str, Any]] = None
        self.progress_percentage: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary representation."""
        return {
            "job_id": str(self.job_id),
            "job_type": self.job_type.value,
            "service_id": str(self.service_id),
            "parameters": self.parameters,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "result": self.result,
            "progress_percentage": self.progress_percentage
        }


class AnalysisService:
    """
    Analysis Service for managing background analysis jobs.

    Handles job creation, status tracking, and async task dispatch for
    SLI/SLO discovery and artifact generation workflows.
    """

    def __init__(self, db_session: Session):
        """
        Initialize analysis service.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session
        # In-memory job storage (for production, use database or Redis)
        self._jobs: Dict[UUID, AnalysisJob] = {}
        # Background task tracking
        self._running_tasks: Dict[UUID, asyncio.Task] = {}

    async def create_job(
        self,
        job_type: JobType,
        service_id: UUID,
        parameters: Optional[Dict[str, Any]] = None
    ) -> AnalysisJob:
        """
        Create a new analysis job.

        Args:
            job_type: Type of analysis job
            service_id: UUID of the service to analyze
            parameters: Job-specific parameters

        Returns:
            Created AnalysisJob instance

        Raises:
            ValueError: If validation fails
        """
        if not service_id:
            raise ValueError("Service ID is required")

        job_id = uuid4()
        job = AnalysisJob(
            job_id=job_id,
            job_type=job_type,
            service_id=service_id,
            parameters=parameters or {}
        )

        self._jobs[job_id] = job

        logger.info(
            f"Created analysis job: {job_id} "
            f"(type={job_type.value}, service={service_id})"
        )

        return job

    async def start_job(self, job_id: UUID) -> AnalysisJob:
        """
        Start a pending analysis job.

        Args:
            job_id: UUID of the job to start

        Returns:
            Updated AnalysisJob instance

        Raises:
            AnalysisJobNotFoundError: If job not found
            ValueError: If job is not in pending status
        """
        job = await self.get_job(job_id)

        if job.status != JobStatus.PENDING:
            raise ValueError(
                f"Cannot start job {job_id}: status is {job.status.value}, "
                "expected pending"
            )

        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()

        logger.info(f"Started analysis job: {job_id}")

        # Dispatch async task
        await self._dispatch_task(job)

        return job

    async def _dispatch_task(self, job: AnalysisJob) -> None:
        """
        Dispatch async task for job execution.

        Args:
            job: AnalysisJob to execute
        """
        # Create background task
        task = asyncio.create_task(self._execute_job(job))
        self._running_tasks[job.job_id] = task

        logger.debug(f"Dispatched background task for job: {job.job_id}")

    async def _execute_job(self, job: AnalysisJob) -> None:
        """
        Execute analysis job in background.

        Args:
            job: AnalysisJob to execute
        """
        try:
            logger.info(f"Executing job: {job.job_id} (type={job.job_type.value})")

            # Simulate job execution (in production, call actual analysis methods)
            if job.job_type == JobType.SLI_DISCOVERY:
                result = await self._execute_sli_discovery(job)
            elif job.job_type == JobType.SLO_GENERATION:
                result = await self._execute_slo_generation(job)
            elif job.job_type == JobType.ARTIFACT_GENERATION:
                result = await self._execute_artifact_generation(job)
            elif job.job_type == JobType.JOURNEY_DISCOVERY:
                result = await self._execute_journey_discovery(job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            # Mark job as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result
            job.progress_percentage = 100

            logger.info(f"Completed job: {job.job_id}")

        except Exception as e:
            logger.error(f"Job {job.job_id} failed: {str(e)}", exc_info=True)
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.error_message = str(e)

        finally:
            # Clean up task reference
            if job.job_id in self._running_tasks:
                del self._running_tasks[job.job_id]

    async def _execute_sli_discovery(self, job: AnalysisJob) -> Dict[str, Any]:
        """
        Execute SLI discovery job.

        Args:
            job: AnalysisJob with parameters

        Returns:
            Job result dictionary
        """
        # Simulate async work
        await asyncio.sleep(0.1)
        job.progress_percentage = 50

        # In production, this would call SLI generation service
        return {
            "sli_count": 5,
            "sli_ids": [str(uuid4()) for _ in range(5)]
        }

    async def _execute_slo_generation(self, job: AnalysisJob) -> Dict[str, Any]:
        """
        Execute SLO generation job.

        Args:
            job: AnalysisJob with parameters

        Returns:
            Job result dictionary
        """
        # Simulate async work
        await asyncio.sleep(0.1)
        job.progress_percentage = 50

        # In production, this would call SLO service
        return {
            "slo_count": 3,
            "slo_ids": [str(uuid4()) for _ in range(3)]
        }

    async def _execute_artifact_generation(self, job: AnalysisJob) -> Dict[str, Any]:
        """
        Execute artifact generation job.

        Args:
            job: AnalysisJob with parameters

        Returns:
            Job result dictionary
        """
        # Simulate async work
        await asyncio.sleep(0.1)
        job.progress_percentage = 50

        # In production, this would call ArtifactGenerator
        return {
            "artifact_count": 2,
            "artifact_ids": [str(uuid4()) for _ in range(2)]
        }

    async def _execute_journey_discovery(self, job: AnalysisJob) -> Dict[str, Any]:
        """
        Execute journey discovery job.

        Args:
            job: AnalysisJob with parameters

        Returns:
            Job result dictionary
        """
        # Simulate async work
        await asyncio.sleep(0.1)
        job.progress_percentage = 50

        # In production, this would call journey discovery service
        return {
            "journey_count": 10,
            "journey_ids": [str(uuid4()) for _ in range(10)]
        }

    async def get_job(self, job_id: UUID) -> AnalysisJob:
        """
        Get analysis job by ID.

        Args:
            job_id: UUID of the job

        Returns:
            AnalysisJob instance

        Raises:
            AnalysisJobNotFoundError: If job not found
        """
        job = self._jobs.get(job_id)

        if not job:
            raise AnalysisJobNotFoundError(f"Job {job_id} not found")

        logger.debug(f"Retrieved job: {job_id} (status={job.status.value})")
        return job

    async def get_job_status(self, job_id: UUID) -> JobStatus:
        """
        Get job status.

        Args:
            job_id: UUID of the job

        Returns:
            JobStatus enum value

        Raises:
            AnalysisJobNotFoundError: If job not found
        """
        job = await self.get_job(job_id)
        return job.status

    async def list_jobs(
        self,
        service_id: Optional[UUID] = None,
        job_type: Optional[JobType] = None,
        status: Optional[JobStatus] = None,
        limit: int = 100
    ) -> List[AnalysisJob]:
        """
        List analysis jobs with optional filters.

        Args:
            service_id: Filter by service ID
            job_type: Filter by job type
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of AnalysisJob instances
        """
        jobs = list(self._jobs.values())

        if service_id:
            jobs = [j for j in jobs if j.service_id == service_id]

        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]

        if status:
            jobs = [j for j in jobs if j.status == status]

        # Sort by created_at descending
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        jobs = jobs[:limit]

        logger.debug(
            f"Listed {len(jobs)} jobs "
            f"(service={service_id}, type={job_type}, status={status})"
        )

        return jobs

    async def cancel_job(self, job_id: UUID) -> AnalysisJob:
        """
        Cancel a running or pending job.

        Args:
            job_id: UUID of the job to cancel

        Returns:
            Updated AnalysisJob instance

        Raises:
            AnalysisJobNotFoundError: If job not found
            ValueError: If job cannot be cancelled
        """
        job = await self.get_job(job_id)

        if job.status not in [JobStatus.PENDING, JobStatus.RUNNING]:
            raise ValueError(
                f"Cannot cancel job {job_id}: status is {job.status.value}"
            )

        # Cancel background task if running
        if job.job_id in self._running_tasks:
            task = self._running_tasks[job.job_id]
            task.cancel()
            del self._running_tasks[job.job_id]

        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.utcnow()

        logger.info(f"Cancelled job: {job_id}")
        return job

    async def cleanup_completed_jobs(self, max_age_hours: int = 24) -> int:
        """
        Clean up completed jobs older than specified hours.

        Args:
            max_age_hours: Maximum age in hours for completed jobs

        Returns:
            Number of jobs cleaned up
        """
        cutoff_time = datetime.utcnow().replace(
            hour=datetime.utcnow().hour - max_age_hours
        )

        cleaned_count = 0
        for job_id, job in list(self._jobs.items()):
            if (
                job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]
                and job.completed_at
                and job.completed_at < cutoff_time
            ):
                del self._jobs[job_id]
                cleaned_count += 1

        logger.info(f"Cleaned up {cleaned_count} completed jobs older than {max_age_hours}h")
        return cleaned_count
