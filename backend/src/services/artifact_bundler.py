"""Artifact bundler service for organizing approved artifacts.

This module collects approved artifacts and organizes them by type into
directory structures suitable for GitOps deployment.

Organization structure per spec.md FR-009:
- prometheus/
  - recording_rules/
  - alert_rules/
- grafana/
  - dashboards/
- runbooks/
"""

import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.artifact import Artifact, ArtifactTypeEnum, ArtifactStatusEnum


logger = logging.getLogger(__name__)


@dataclass
class BundledFile:
    """Represents a file in the artifact bundle."""

    path: str  # Relative path in repository
    content: str
    artifact_id: str
    artifact_type: str


@dataclass
class ArtifactBundle:
    """Collection of organized artifacts ready for GitOps deployment."""

    service_name: str
    files: List[BundledFile]
    artifact_count: int
    summary: Dict[str, int]  # Count by type


class ArtifactBundlerError(Exception):
    """Raised when artifact bundling fails."""

    pass


class ArtifactBundler:
    """Service for bundling approved artifacts into organized directory structure.

    Responsibilities:
    - Query approved artifacts from database
    - Organize by type into conventional directory structure
    - Generate file paths following GitOps repository conventions
    - Validate artifact approval status
    - Generate bundle summary for PR body

    Directory structure:
        prometheus/
            recording_rules/
                {service_name}_recording_rules.yml
            alert_rules/
                {service_name}_alert_rules.yml
        grafana/
            dashboards/
                {service_name}_dashboard.json
        runbooks/
            {service_name}_runbook.yml

    Example:
        >>> bundler = ArtifactBundler(db_session)
        >>> bundle = await bundler.bundle_artifacts(
        ...     artifact_ids=["uuid1", "uuid2", "uuid3"],
        ...     service_name="payments-api"
        ... )
        >>> print(bundle.summary)
        {'prometheus_alert': 1, 'grafana_dashboard': 1, 'runbook': 1}
        >>> for file in bundle.files:
        ...     print(f"{file.path}: {len(file.content)} bytes")
        prometheus/alert_rules/payments-api_alert_rules.yml: 1234 bytes
        grafana/dashboards/payments-api_dashboard.json: 5678 bytes
        runbooks/payments-api_runbook.yml: 910 bytes
    """

    # Directory structure mapping
    DIRECTORY_MAP = {
        ArtifactTypeEnum.PROMETHEUS_RECORDING: "prometheus/recording_rules",
        ArtifactTypeEnum.PROMETHEUS_ALERT: "prometheus/alert_rules",
        ArtifactTypeEnum.GRAFANA_DASHBOARD: "grafana/dashboards",
        ArtifactTypeEnum.RUNBOOK: "runbooks",
    }

    # File extension mapping
    EXTENSION_MAP = {
        ArtifactTypeEnum.PROMETHEUS_RECORDING: ".yml",
        ArtifactTypeEnum.PROMETHEUS_ALERT: ".yml",
        ArtifactTypeEnum.GRAFANA_DASHBOARD: ".json",
        ArtifactTypeEnum.RUNBOOK: ".yml",
    }

    # File name template
    FILENAME_MAP = {
        ArtifactTypeEnum.PROMETHEUS_RECORDING: "{service}_recording_rules{ext}",
        ArtifactTypeEnum.PROMETHEUS_ALERT: "{service}_alert_rules{ext}",
        ArtifactTypeEnum.GRAFANA_DASHBOARD: "{service}_dashboard{ext}",
        ArtifactTypeEnum.RUNBOOK: "{service}_runbook{ext}",
    }

    def __init__(self, session: AsyncSession):
        """Initialize artifact bundler.

        Args:
            session: Database session for querying artifacts
        """
        self.session = session

    async def get_artifacts(self, artifact_ids: List[str]) -> List[Artifact]:
        """Retrieve artifacts by IDs.

        Args:
            artifact_ids: List of artifact UUIDs

        Returns:
            List of Artifact models

        Raises:
            ArtifactBundlerError: If any artifact not found
        """
        stmt = select(Artifact).where(Artifact.artifact_id.in_(artifact_ids))
        result = await self.session.execute(stmt)
        artifacts = result.scalars().all()

        if len(artifacts) != len(artifact_ids):
            found_ids = {str(a.artifact_id) for a in artifacts}
            missing_ids = set(artifact_ids) - found_ids
            raise ArtifactBundlerError(
                f"Artifacts not found: {', '.join(missing_ids)}"
            )

        return list(artifacts)

    def validate_approval_status(self, artifacts: List[Artifact]) -> None:
        """Validate that all artifacts are approved.

        Args:
            artifacts: List of artifacts to validate

        Raises:
            ArtifactBundlerError: If any artifact is not approved
        """
        unapproved = [
            str(a.artifact_id)
            for a in artifacts
            if a.approval_status != ArtifactStatusEnum.APPROVED
        ]

        if unapproved:
            raise ArtifactBundlerError(
                f"Cannot bundle unapproved artifacts: {', '.join(unapproved)}. "
                f"All artifacts must have approval_status=APPROVED."
            )

    def generate_file_path(
        self,
        artifact_type: ArtifactTypeEnum,
        service_name: str,
    ) -> str:
        """Generate conventional file path for artifact.

        Args:
            artifact_type: Type of artifact
            service_name: Service name for filename

        Returns:
            Relative file path in repository
        """
        # Get directory
        directory = self.DIRECTORY_MAP.get(artifact_type)
        if not directory:
            raise ArtifactBundlerError(f"Unknown artifact type: {artifact_type}")

        # Get extension
        extension = self.EXTENSION_MAP.get(artifact_type, "")

        # Get filename template
        filename_template = self.FILENAME_MAP.get(
            artifact_type,
            "{service}_{type}{ext}",
        )

        # Sanitize service name (replace spaces/special chars with hyphens)
        safe_service_name = service_name.lower().replace(" ", "-").replace("_", "-")

        # Build filename
        filename = filename_template.format(
            service=safe_service_name,
            type=artifact_type.value,
            ext=extension,
        )

        # Combine directory and filename
        return f"{directory}/{filename}"

    def generate_bundle_summary(self, artifacts: List[Artifact]) -> Dict[str, int]:
        """Generate summary of artifacts by type.

        Args:
            artifacts: List of artifacts

        Returns:
            Dictionary mapping artifact type to count
        """
        summary: Dict[str, int] = {}

        for artifact in artifacts:
            type_key = artifact.artifact_type.value
            summary[type_key] = summary.get(type_key, 0) + 1

        return summary

    async def bundle_artifacts(
        self,
        artifact_ids: List[str],
        service_name: str,
        validate_approval: bool = True,
    ) -> ArtifactBundle:
        """Bundle approved artifacts into organized file structure.

        Args:
            artifact_ids: List of artifact UUIDs to bundle
            service_name: Service name for organizing files
            validate_approval: Validate approval status (default: True)

        Returns:
            ArtifactBundle with organized files

        Raises:
            ArtifactBundlerError: If artifacts not found or not approved
        """
        if not artifact_ids:
            raise ArtifactBundlerError("No artifact IDs provided")

        # Retrieve artifacts
        artifacts = await self.get_artifacts(artifact_ids)

        # Validate approval status
        if validate_approval:
            self.validate_approval_status(artifacts)

        # Bundle files
        files: List[BundledFile] = []

        for artifact in artifacts:
            file_path = self.generate_file_path(
                artifact_type=artifact.artifact_type,
                service_name=service_name,
            )

            files.append(
                BundledFile(
                    path=file_path,
                    content=artifact.content,
                    artifact_id=str(artifact.artifact_id),
                    artifact_type=artifact.artifact_type.value,
                )
            )

            logger.debug(
                f"Bundled artifact {artifact.artifact_id} to {file_path}",
                extra={
                    "artifact_id": str(artifact.artifact_id),
                    "artifact_type": artifact.artifact_type.value,
                    "file_path": file_path,
                    "content_size": len(artifact.content),
                },
            )

        # Generate summary
        summary = self.generate_bundle_summary(artifacts)

        bundle = ArtifactBundle(
            service_name=service_name,
            files=files,
            artifact_count=len(artifacts),
            summary=summary,
        )

        logger.info(
            f"Bundled {len(files)} artifacts for {service_name}",
            extra={
                "service_name": service_name,
                "artifact_count": len(files),
                "summary": summary,
            },
        )

        return bundle

    async def bundle_artifacts_by_slo(
        self,
        slo_id: str,
        service_name: str,
        approval_status: Optional[ArtifactStatusEnum] = ArtifactStatusEnum.APPROVED,
    ) -> ArtifactBundle:
        """Bundle all artifacts for a specific SLO.

        Convenience method to bundle all artifacts associated with an SLO.

        Args:
            slo_id: SLO UUID
            service_name: Service name for organizing files
            approval_status: Filter by approval status (default: APPROVED)

        Returns:
            ArtifactBundle with organized files
        """
        # Query artifacts by SLO ID
        stmt = select(Artifact).where(Artifact.slo_id == slo_id)

        if approval_status is not None:
            stmt = stmt.where(Artifact.approval_status == approval_status)

        result = await self.session.execute(stmt)
        artifacts = list(result.scalars().all())

        if not artifacts:
            raise ArtifactBundlerError(
                f"No artifacts found for SLO {slo_id} with approval status {approval_status}"
            )

        artifact_ids = [str(a.artifact_id) for a in artifacts]

        return await self.bundle_artifacts(
            artifact_ids=artifact_ids,
            service_name=service_name,
            validate_approval=False,  # Already filtered by status
        )

    def generate_pr_summary_markdown(self, bundle: ArtifactBundle) -> str:
        """Generate Markdown summary for PR body.

        Creates a formatted summary of bundled artifacts suitable for
        inclusion in pull request descriptions.

        Args:
            bundle: Artifact bundle to summarize

        Returns:
            Markdown-formatted summary
        """
        lines = [
            "## Artifact Summary",
            "",
            f"Service: **{bundle.service_name}**",
            f"Total Artifacts: **{bundle.artifact_count}**",
            "",
            "### Files Included",
            "",
        ]

        # Group files by directory
        files_by_dir: Dict[str, List[BundledFile]] = {}
        for file in bundle.files:
            directory = str(Path(file.path).parent)
            if directory not in files_by_dir:
                files_by_dir[directory] = []
            files_by_dir[directory].append(file)

        # List files by directory
        for directory in sorted(files_by_dir.keys()):
            lines.append(f"**{directory}/**")
            for file in sorted(files_by_dir[directory], key=lambda f: f.path):
                filename = Path(file.path).name
                size_kb = len(file.content) / 1024
                lines.append(f"- `{filename}` ({size_kb:.1f} KB)")
            lines.append("")

        # Add artifact type summary
        lines.extend([
            "### Artifact Types",
            "",
        ])

        for artifact_type, count in sorted(bundle.summary.items()):
            lines.append(f"- {artifact_type.replace('_', ' ').title()}: {count}")

        return "\n".join(lines)
