"""
Artifact Generator - Generate and validate Prometheus/Grafana artifacts.

Provides artifact generation with promtool validation for Prometheus rules.
"""
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import UUID
from decimal import Decimal
import logging
import subprocess
import tempfile
import yaml
import json
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.models.artifact import Artifact, ArtifactTypeEnum, ArtifactStatusEnum
from src.models.slo import SLO

logger = logging.getLogger(__name__)


class ArtifactNotFoundError(Exception):
    """Raised when an artifact is not found."""
    pass


class ArtifactValidationError(Exception):
    """Raised when artifact validation fails."""
    pass


class PromtoolNotAvailableError(Exception):
    """Raised when promtool is not available."""
    pass


class ArtifactGenerator:
    """
    Artifact Generator for creating and validating monitoring artifacts.

    Generates Prometheus rules, Grafana dashboards, and runbooks with
    validation using promtool for Prometheus rules.
    """

    def __init__(self, db_session: Session, promtool_path: str = "promtool"):
        """
        Initialize artifact generator.

        Args:
            db_session: SQLAlchemy database session
            promtool_path: Path to promtool binary (default: "promtool")
        """
        self.db = db_session
        self.promtool_path = promtool_path

    async def create(
        self,
        slo_id: UUID,
        artifact_type: ArtifactTypeEnum,
        content: str,
        confidence_score: Decimal,
        validate: bool = True
    ) -> Artifact:
        """
        Create a new artifact with optional validation.

        Args:
            slo_id: UUID of the associated SLO
            artifact_type: Type of artifact
            content: YAML/JSON configuration content
            confidence_score: AI confidence score (0.0-1.0)
            validate: Whether to validate the artifact (default: True)

        Returns:
            Created Artifact instance

        Raises:
            ValueError: If validation of inputs fails
            ArtifactValidationError: If artifact validation fails
        """
        # Validate inputs
        if not content or not content.strip():
            raise ValueError("Artifact content cannot be empty")

        if confidence_score < 0 or confidence_score > 1:
            raise ValueError(
                f"Confidence score must be between 0 and 1, got {confidence_score}"
            )

        # Verify SLO exists
        slo = self.db.query(SLO).filter(SLO.slo_id == slo_id).first()
        if not slo:
            raise ValueError(f"SLO {slo_id} not found")

        # Validate artifact content if requested
        if validate:
            validation_result = await self.validate_content(
                artifact_type,
                content
            )
            if not validation_result[0]:
                raise ArtifactValidationError(
                    f"Artifact validation failed: {validation_result[1]}"
                )

        # Create artifact instance
        artifact = Artifact(
            slo_id=slo_id,
            artifact_type=artifact_type,
            content=content.strip(),
            confidence_score=confidence_score,
            status=ArtifactStatusEnum.DRAFT
        )

        try:
            self.db.add(artifact)
            self.db.flush()
            logger.info(
                f"Created artifact: {artifact.artifact_id} "
                f"(type={artifact_type.value}, confidence={confidence_score:.3f})"
            )
            return artifact
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create artifact: {str(e)}")
            raise

    async def get(self, artifact_id: UUID) -> Artifact:
        """
        Get an artifact by ID.

        Args:
            artifact_id: UUID of the artifact

        Returns:
            Artifact instance

        Raises:
            ArtifactNotFoundError: If artifact not found
        """
        artifact = self.db.query(Artifact).filter(
            Artifact.artifact_id == artifact_id
        ).first()

        if not artifact:
            raise ArtifactNotFoundError(f"Artifact with ID {artifact_id} not found")

        logger.debug(f"Retrieved artifact: {artifact.artifact_id}")
        return artifact

    async def validate_content(
        self,
        artifact_type: ArtifactTypeEnum,
        content: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate artifact content.

        For Prometheus rules, uses promtool for validation.
        For other types, validates YAML/JSON syntax.

        Args:
            artifact_type: Type of artifact
            content: Artifact content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # First, validate basic syntax (YAML or JSON)
            syntax_valid, syntax_error = self._validate_syntax(content)
            if not syntax_valid:
                return False, syntax_error

            # For Prometheus rules, use promtool
            if artifact_type == ArtifactTypeEnum.PROMETHEUS_RULE:
                return await self._validate_prometheus_rule(content)

            # For Grafana dashboards, validate JSON structure
            elif artifact_type == ArtifactTypeEnum.GRAFANA_DASHBOARD:
                return self._validate_grafana_dashboard(content)

            # For runbooks, just validate it's valid YAML/Markdown
            elif artifact_type == ArtifactTypeEnum.RUNBOOK:
                return True, None

            else:
                logger.warning(f"No specific validation for type {artifact_type.value}")
                return True, None

        except Exception as e:
            logger.error(f"Validation error: {str(e)}", exc_info=True)
            return False, str(e)

    def _validate_syntax(self, content: str) -> Tuple[bool, Optional[str]]:
        """
        Validate YAML or JSON syntax.

        Args:
            content: Content to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Try YAML first
        try:
            yaml.safe_load(content)
            return True, None
        except yaml.YAMLError as yaml_error:
            # Try JSON as fallback
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as json_error:
                return False, f"Invalid YAML/JSON syntax: {str(yaml_error)}"

    async def _validate_prometheus_rule(
        self,
        content: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate Prometheus rule using promtool.

        Args:
            content: Prometheus rule YAML content

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Create temporary file for validation
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.yaml',
                delete=False
            ) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name

            try:
                # Run promtool check rules
                result = subprocess.run(
                    [self.promtool_path, 'check', 'rules', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if result.returncode == 0:
                    logger.info(f"Prometheus rule validation successful")
                    return True, None
                else:
                    error_msg = result.stderr or result.stdout
                    logger.warning(f"Prometheus rule validation failed: {error_msg}")
                    return False, f"promtool validation failed: {error_msg}"

            finally:
                # Clean up temporary file
                Path(temp_path).unlink(missing_ok=True)

        except FileNotFoundError:
            # promtool not available - log warning and fail-open
            logger.warning(
                f"promtool not found at {self.promtool_path}. "
                "Skipping Prometheus rule validation."
            )
            # Return True to fail-open when promtool is not available
            return True, None

        except subprocess.TimeoutExpired:
            logger.error("promtool validation timed out")
            return False, "Validation timed out"

        except Exception as e:
            logger.error(f"promtool validation error: {str(e)}", exc_info=True)
            # Fail-open on unexpected errors
            return True, None

    def _validate_grafana_dashboard(
        self,
        content: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate Grafana dashboard JSON structure.

        Args:
            content: Grafana dashboard JSON content

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            dashboard = json.loads(content)

            # Basic structure validation
            required_fields = ['title', 'panels']
            for field in required_fields:
                if field not in dashboard:
                    return False, f"Missing required field: {field}"

            # Validate panels structure
            if not isinstance(dashboard['panels'], list):
                return False, "Panels must be a list"

            logger.info("Grafana dashboard validation successful")
            return True, None

        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {str(e)}"
        except Exception as e:
            logger.error(f"Dashboard validation error: {str(e)}", exc_info=True)
            return False, str(e)

    async def generate_prometheus_rule(
        self,
        slo_id: UUID,
        confidence_score: Decimal
    ) -> Artifact:
        """
        Generate Prometheus alerting rule from SLO.

        Args:
            slo_id: UUID of the SLO
            confidence_score: AI confidence score

        Returns:
            Created Artifact instance with Prometheus rule

        Raises:
            ValueError: If SLO not found
        """
        slo = self.db.query(SLO).filter(SLO.slo_id == slo_id).first()
        if not slo:
            raise ValueError(f"SLO {slo_id} not found")

        # Generate Prometheus rule YAML
        rule_content = self._build_prometheus_rule(slo)

        # Create artifact
        artifact = await self.create(
            slo_id=slo_id,
            artifact_type=ArtifactTypeEnum.PROMETHEUS_RULE,
            content=rule_content,
            confidence_score=confidence_score,
            validate=True
        )

        logger.info(f"Generated Prometheus rule for SLO {slo_id}")
        return artifact

    def _build_prometheus_rule(self, slo: SLO) -> str:
        """
        Build Prometheus rule YAML from SLO.

        Args:
            slo: SLO instance

        Returns:
            Prometheus rule YAML string
        """
        # Get error budget (for alert annotations)
        allowed_error_rate = Decimal("100") - slo.target_percentage

        rule = {
            'groups': [
                {
                    'name': f'slo_{slo.name.lower().replace(" ", "_")}',
                    'interval': '30s',
                    'rules': [
                        {
                            'alert': f'SLOBurnRate{slo.threshold_variant.value.capitalize()}',
                            'expr': f'(1 - (sum(rate(http_requests_total{{job=~".*"}}[{slo.time_window}])) / sum(rate(http_requests_total{{job=~".*"}}[{slo.time_window}])))) > {float(allowed_error_rate) / 100}',
                            'for': '5m',
                            'labels': {
                                'severity': 'critical',
                                'slo_id': str(slo.slo_id),
                                'threshold_variant': slo.threshold_variant.value
                            },
                            'annotations': {
                                'summary': f'SLO {slo.name} burn rate exceeded',
                                'description': f'Error budget for {slo.name} is being consumed too fast. Target: {slo.target_percentage}%, Window: {slo.time_window}',
                                'runbook_url': 'https://runbooks.example.com/slo-burn-rate'
                            }
                        }
                    ]
                }
            ]
        }

        return yaml.dump(rule, default_flow_style=False, sort_keys=False)

    async def update_status(
        self,
        artifact_id: UUID,
        status: ArtifactStatusEnum,
        pr_url: Optional[str] = None
    ) -> Artifact:
        """
        Update artifact deployment status.

        Args:
            artifact_id: UUID of the artifact
            status: New deployment status
            pr_url: Optional PR URL for deployment

        Returns:
            Updated Artifact instance

        Raises:
            ArtifactNotFoundError: If artifact not found
        """
        artifact = await self.get(artifact_id)

        artifact.status = status

        if pr_url:
            artifact.pr_url = pr_url

        if status == ArtifactStatusEnum.DEPLOYED:
            artifact.deployed_at = datetime.utcnow()

        self.db.flush()

        logger.info(
            f"Updated artifact {artifact_id} status to {status.value}"
        )

        return artifact

    async def list(
        self,
        slo_id: Optional[UUID] = None,
        artifact_type: Optional[ArtifactTypeEnum] = None,
        status: Optional[ArtifactStatusEnum] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Artifact]:
        """
        List artifacts with optional filters.

        Args:
            slo_id: Filter by SLO ID
            artifact_type: Filter by artifact type
            status: Filter by status
            limit: Maximum number of results (default: 100)
            offset: Pagination offset (default: 0)

        Returns:
            List of Artifact instances
        """
        query = self.db.query(Artifact).order_by(Artifact.created_at.desc())

        if slo_id:
            query = query.filter(Artifact.slo_id == slo_id)

        if artifact_type:
            query = query.filter(Artifact.artifact_type == artifact_type)

        if status:
            query = query.filter(Artifact.status == status)

        artifacts = query.limit(limit).offset(offset).all()

        logger.debug(
            f"Listed {len(artifacts)} artifacts "
            f"(slo={slo_id}, type={artifact_type}, status={status})"
        )

        return artifacts

    async def delete(self, artifact_id: UUID) -> None:
        """
        Delete an artifact.

        Args:
            artifact_id: UUID of the artifact to delete

        Raises:
            ArtifactNotFoundError: If artifact not found
        """
        artifact = await self.get(artifact_id)

        self.db.delete(artifact)
        self.db.flush()

        logger.info(f"Deleted artifact: {artifact_id}")

    def check_promtool_available(self) -> bool:
        """
        Check if promtool is available.

        Returns:
            True if promtool is available, False otherwise
        """
        try:
            result = subprocess.run(
                [self.promtool_path, '--version'],
                capture_output=True,
                timeout=5
            )
            available = result.returncode == 0
            if available:
                logger.info(f"promtool is available at {self.promtool_path}")
            else:
                logger.warning(f"promtool not available at {self.promtool_path}")
            return available
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning(f"promtool not available at {self.promtool_path}")
            return False
