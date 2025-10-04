"""
Grafana Schema Validator (T106)

Validate dashboard JSON against Grafana API v7+ schema.
Per research.md: JSON schema validation for Grafana dashboards
"""
import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Validation error details"""
    path: str
    message: str
    severity: str = "error"


class GrafanaSchemaValidator:
    """
    Validates Grafana dashboard JSON against schema requirements.

    Per FR-007: System MUST generate Grafana dashboard JSON schemas that are
    syntactically valid and include time-range comparators and deployment annotations.
    Per research.md: Format is JSON model API v7+ schema.
    """

    # Minimum required schema version for Grafana v7+
    MIN_SCHEMA_VERSION = 16

    # Required top-level dashboard fields
    REQUIRED_DASHBOARD_FIELDS = [
        "title",
        "panels",
        "schemaVersion"
    ]

    # Required panel fields
    REQUIRED_PANEL_FIELDS = [
        "id",
        "title",
        "type",
        "gridPos",
        "targets"
    ]

    # Valid panel types
    VALID_PANEL_TYPES = [
        "timeseries",
        "graph",
        "stat",
        "gauge",
        "bargauge",
        "table",
        "heatmap",
        "logs",
        "text",
        "alertlist",
        "dashlist",
        "news"
    ]

    def validate(self, dashboard_json: str) -> List[ValidationError]:
        """
        Validate a Grafana dashboard JSON string.

        Args:
            dashboard_json: JSON string containing dashboard definition

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[ValidationError] = []

        # Parse JSON
        try:
            data = json.loads(dashboard_json)
        except json.JSONDecodeError as e:
            errors.append(ValidationError(
                path="root",
                message=f"Invalid JSON: {str(e)}",
                severity="error"
            ))
            return errors

        # Extract dashboard (might be wrapped in {"dashboard": {...}})
        if "dashboard" in data:
            dashboard = data["dashboard"]
        else:
            dashboard = data

        if not isinstance(dashboard, dict):
            errors.append(ValidationError(
                path="root",
                message="Dashboard must be a JSON object",
                severity="error"
            ))
            return errors

        # Validate required fields
        errors.extend(self._validate_required_fields(dashboard))

        # Validate schema version
        errors.extend(self._validate_schema_version(dashboard))

        # Validate panels
        if "panels" in dashboard:
            errors.extend(self._validate_panels(dashboard["panels"]))

        # Validate templating (if present)
        if "templating" in dashboard:
            errors.extend(self._validate_templating(dashboard["templating"]))

        # Validate annotations (if present)
        if "annotations" in dashboard:
            errors.extend(self._validate_annotations(dashboard["annotations"]))

        return errors

    def _validate_required_fields(self, dashboard: Dict[str, Any]) -> List[ValidationError]:
        """Validate that required dashboard fields are present."""
        errors: List[ValidationError] = []

        for field in self.REQUIRED_DASHBOARD_FIELDS:
            if field not in dashboard:
                errors.append(ValidationError(
                    path=f"dashboard.{field}",
                    message=f"Missing required field: {field}",
                    severity="error"
                ))

        return errors

    def _validate_schema_version(self, dashboard: Dict[str, Any]) -> List[ValidationError]:
        """Validate schema version is compatible with Grafana v7+."""
        errors: List[ValidationError] = []

        schema_version = dashboard.get("schemaVersion")
        if schema_version is None:
            return errors  # Already reported in required fields

        if not isinstance(schema_version, int):
            errors.append(ValidationError(
                path="dashboard.schemaVersion",
                message="schemaVersion must be an integer",
                severity="error"
            ))
            return errors

        if schema_version < self.MIN_SCHEMA_VERSION:
            errors.append(ValidationError(
                path="dashboard.schemaVersion",
                message=f"schemaVersion {schema_version} is too old (minimum: {self.MIN_SCHEMA_VERSION} for Grafana v7+)",
                severity="warning"
            ))

        return errors

    def _validate_panels(self, panels: Any) -> List[ValidationError]:
        """Validate panels array."""
        errors: List[ValidationError] = []

        if not isinstance(panels, list):
            errors.append(ValidationError(
                path="dashboard.panels",
                message="panels must be an array",
                severity="error"
            ))
            return errors

        panel_ids = set()
        for i, panel in enumerate(panels):
            if not isinstance(panel, dict):
                errors.append(ValidationError(
                    path=f"dashboard.panels[{i}]",
                    message="Panel must be an object",
                    severity="error"
                ))
                continue

            # Validate required panel fields
            for field in self.REQUIRED_PANEL_FIELDS:
                if field not in panel:
                    errors.append(ValidationError(
                        path=f"dashboard.panels[{i}].{field}",
                        message=f"Missing required panel field: {field}",
                        severity="error"
                    ))

            # Validate panel ID uniqueness
            panel_id = panel.get("id")
            if panel_id is not None:
                if panel_id in panel_ids:
                    errors.append(ValidationError(
                        path=f"dashboard.panels[{i}].id",
                        message=f"Duplicate panel ID: {panel_id}",
                        severity="error"
                    ))
                panel_ids.add(panel_id)

            # Validate panel type
            panel_type = panel.get("type")
            if panel_type and panel_type not in self.VALID_PANEL_TYPES:
                errors.append(ValidationError(
                    path=f"dashboard.panels[{i}].type",
                    message=f"Unknown panel type: {panel_type}",
                    severity="warning"
                ))

            # Validate gridPos
            grid_pos = panel.get("gridPos")
            if grid_pos:
                errors.extend(self._validate_grid_pos(grid_pos, f"dashboard.panels[{i}].gridPos"))

            # Validate targets
            targets = panel.get("targets")
            if targets:
                errors.extend(self._validate_targets(targets, f"dashboard.panels[{i}].targets"))

        return errors

    def _validate_grid_pos(self, grid_pos: Any, path: str) -> List[ValidationError]:
        """Validate panel grid position."""
        errors: List[ValidationError] = []

        if not isinstance(grid_pos, dict):
            errors.append(ValidationError(
                path=path,
                message="gridPos must be an object",
                severity="error"
            ))
            return errors

        required_fields = ["x", "y", "w", "h"]
        for field in required_fields:
            if field not in grid_pos:
                errors.append(ValidationError(
                    path=f"{path}.{field}",
                    message=f"Missing required gridPos field: {field}",
                    severity="error"
                ))
            elif not isinstance(grid_pos[field], int):
                errors.append(ValidationError(
                    path=f"{path}.{field}",
                    message=f"gridPos.{field} must be an integer",
                    severity="error"
                ))

        # Validate ranges
        if "x" in grid_pos and (grid_pos["x"] < 0 or grid_pos["x"] >= 24):
            errors.append(ValidationError(
                path=f"{path}.x",
                message="gridPos.x must be between 0 and 23 (24-column grid)",
                severity="warning"
            ))

        if "w" in grid_pos and (grid_pos["w"] <= 0 or grid_pos["w"] > 24):
            errors.append(ValidationError(
                path=f"{path}.w",
                message="gridPos.w must be between 1 and 24",
                severity="warning"
            ))

        return errors

    def _validate_targets(self, targets: Any, path: str) -> List[ValidationError]:
        """Validate panel targets (queries)."""
        errors: List[ValidationError] = []

        if not isinstance(targets, list):
            errors.append(ValidationError(
                path=path,
                message="targets must be an array",
                severity="error"
            ))
            return errors

        for i, target in enumerate(targets):
            if not isinstance(target, dict):
                errors.append(ValidationError(
                    path=f"{path}[{i}]",
                    message="Target must be an object",
                    severity="error"
                ))
                continue

            # Validate refId
            if "refId" not in target:
                errors.append(ValidationError(
                    path=f"{path}[{i}].refId",
                    message="Missing required target field: refId",
                    severity="error"
                ))

        return errors

    def _validate_templating(self, templating: Any) -> List[ValidationError]:
        """Validate templating variables."""
        errors: List[ValidationError] = []

        if not isinstance(templating, dict):
            errors.append(ValidationError(
                path="dashboard.templating",
                message="templating must be an object",
                severity="error"
            ))
            return errors

        if "list" in templating:
            variables = templating["list"]
            if not isinstance(variables, list):
                errors.append(ValidationError(
                    path="dashboard.templating.list",
                    message="templating.list must be an array",
                    severity="error"
                ))

        return errors

    def _validate_annotations(self, annotations: Any) -> List[ValidationError]:
        """Validate annotations configuration."""
        errors: List[ValidationError] = []

        if not isinstance(annotations, dict):
            errors.append(ValidationError(
                path="dashboard.annotations",
                message="annotations must be an object",
                severity="error"
            ))
            return errors

        if "list" in annotations:
            anno_list = annotations["list"]
            if not isinstance(anno_list, list):
                errors.append(ValidationError(
                    path="dashboard.annotations.list",
                    message="annotations.list must be an array",
                    severity="error"
                ))

        return errors


def validate_grafana_dashboard(dashboard_json: str) -> List[ValidationError]:
    """
    Convenience function to validate a Grafana dashboard.

    Args:
        dashboard_json: JSON string containing dashboard definition

    Returns:
        List of validation errors (empty if valid)
    """
    validator = GrafanaSchemaValidator()
    return validator.validate(dashboard_json)
