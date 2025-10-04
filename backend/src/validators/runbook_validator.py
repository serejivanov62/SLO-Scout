"""
Runbook Validator (T109)

Validate YAML syntax, assert required fields: name, triggers, steps.
Per spec.md FR-008: Validate runbook structure
"""
import yaml
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class ValidationError:
    """Validation error details"""
    path: str
    message: str
    severity: str = "error"


class RunbookValidator:
    """
    Validates runbook YAML structure and content.

    Per FR-008: System MUST generate executable runbook YAML templates.
    This validator ensures runbooks meet required structure and standards.
    """

    # Required top-level runbook fields
    REQUIRED_FIELDS = [
        "name",
        "triggers",
        "steps"
    ]

    # Required step fields
    REQUIRED_STEP_FIELDS = [
        "name",
        "description",
        "command"
    ]

    # Valid step types
    VALID_STEP_TYPES = [
        "diagnostic",
        "mitigation",
        "rollback",
        "verification"
    ]

    # Valid blast radius levels
    VALID_BLAST_RADIUS = [
        "low",
        "medium",
        "high"
    ]

    def validate(self, runbook_yaml: str) -> List[ValidationError]:
        """
        Validate a runbook YAML string.

        Args:
            runbook_yaml: YAML string containing runbook definition

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[ValidationError] = []

        # Parse YAML
        try:
            runbook = yaml.safe_load(runbook_yaml)
        except yaml.YAMLError as e:
            errors.append(ValidationError(
                path="root",
                message=f"Invalid YAML: {str(e)}",
                severity="error"
            ))
            return errors

        if not isinstance(runbook, dict):
            errors.append(ValidationError(
                path="root",
                message="Runbook must be a YAML dict",
                severity="error"
            ))
            return errors

        # Validate required fields
        errors.extend(self._validate_required_fields(runbook))

        # Validate name
        if "name" in runbook:
            errors.extend(self._validate_name(runbook["name"]))

        # Validate triggers
        if "triggers" in runbook:
            errors.extend(self._validate_triggers(runbook["triggers"]))

        # Validate steps
        if "steps" in runbook:
            errors.extend(self._validate_steps(runbook["steps"]))

        # Validate metadata (optional but recommended)
        if "metadata" in runbook:
            errors.extend(self._validate_metadata(runbook["metadata"]))

        # Validate escalation (optional)
        if "escalation" in runbook:
            errors.extend(self._validate_escalation(runbook["escalation"]))

        return errors

    def _validate_required_fields(self, runbook: Dict[str, Any]) -> List[ValidationError]:
        """Validate that required runbook fields are present."""
        errors: List[ValidationError] = []

        for field in self.REQUIRED_FIELDS:
            if field not in runbook:
                errors.append(ValidationError(
                    path=f"runbook.{field}",
                    message=f"Missing required field: {field}",
                    severity="error"
                ))

        return errors

    def _validate_name(self, name: Any) -> List[ValidationError]:
        """Validate runbook name."""
        errors: List[ValidationError] = []

        if not isinstance(name, str):
            errors.append(ValidationError(
                path="runbook.name",
                message="name must be a string",
                severity="error"
            ))
        elif not name.strip():
            errors.append(ValidationError(
                path="runbook.name",
                message="name cannot be empty",
                severity="error"
            ))
        elif len(name) > 255:
            errors.append(ValidationError(
                path="runbook.name",
                message="name exceeds maximum length of 255 characters",
                severity="warning"
            ))

        return errors

    def _validate_triggers(self, triggers: Any) -> List[ValidationError]:
        """Validate triggers array."""
        errors: List[ValidationError] = []

        if not isinstance(triggers, list):
            errors.append(ValidationError(
                path="runbook.triggers",
                message="triggers must be an array",
                severity="error"
            ))
            return errors

        if len(triggers) == 0:
            errors.append(ValidationError(
                path="runbook.triggers",
                message="triggers array cannot be empty",
                severity="error"
            ))

        for i, trigger in enumerate(triggers):
            if not isinstance(trigger, dict):
                errors.append(ValidationError(
                    path=f"runbook.triggers[{i}]",
                    message="Trigger must be a dict",
                    severity="error"
                ))
                continue

            # Validate trigger type
            if "type" not in trigger:
                errors.append(ValidationError(
                    path=f"runbook.triggers[{i}].type",
                    message="Missing required trigger field: type",
                    severity="error"
                ))

        return errors

    def _validate_steps(self, steps: Any) -> List[ValidationError]:
        """Validate steps structure."""
        errors: List[ValidationError] = []

        if not isinstance(steps, dict):
            errors.append(ValidationError(
                path="runbook.steps",
                message="steps must be a dict with keys: diagnostic, mitigation, rollback",
                severity="error"
            ))
            return errors

        # Validate each step category
        for category in ["diagnostic", "mitigation", "rollback"]:
            if category in steps:
                category_steps = steps[category]
                if not isinstance(category_steps, list):
                    errors.append(ValidationError(
                        path=f"runbook.steps.{category}",
                        message=f"{category} steps must be an array",
                        severity="error"
                    ))
                    continue

                # Validate individual steps
                for i, step in enumerate(category_steps):
                    errors.extend(self._validate_step(step, f"runbook.steps.{category}[{i}]"))

        # Warn if no diagnostic steps
        if "diagnostic" not in steps or not steps["diagnostic"]:
            errors.append(ValidationError(
                path="runbook.steps.diagnostic",
                message="Runbook should include diagnostic steps",
                severity="warning"
            ))

        return errors

    def _validate_step(self, step: Any, path: str) -> List[ValidationError]:
        """Validate an individual step."""
        errors: List[ValidationError] = []

        if not isinstance(step, dict):
            errors.append(ValidationError(
                path=path,
                message="Step must be a dict",
                severity="error"
            ))
            return errors

        # Validate required step fields
        for field in self.REQUIRED_STEP_FIELDS:
            if field not in step:
                errors.append(ValidationError(
                    path=f"{path}.{field}",
                    message=f"Missing required step field: {field}",
                    severity="error"
                ))

        # Validate step type if present
        if "type" in step:
            step_type = step["type"]
            if step_type not in self.VALID_STEP_TYPES:
                errors.append(ValidationError(
                    path=f"{path}.type",
                    message=f"Invalid step type: {step_type}. Must be one of {self.VALID_STEP_TYPES}",
                    severity="warning"
                ))

        # Validate blast_radius if present
        if "blast_radius" in step:
            blast_radius = step["blast_radius"]
            if blast_radius not in self.VALID_BLAST_RADIUS:
                errors.append(ValidationError(
                    path=f"{path}.blast_radius",
                    message=f"Invalid blast_radius: {blast_radius}. Must be one of {self.VALID_BLAST_RADIUS}",
                    severity="warning"
                ))

        # Validate timeout format if present
        if "timeout" in step:
            timeout = step["timeout"]
            if not isinstance(timeout, str):
                errors.append(ValidationError(
                    path=f"{path}.timeout",
                    message="timeout must be a string (e.g., '30s', '5m')",
                    severity="error"
                ))
            elif not self._is_valid_duration(timeout):
                errors.append(ValidationError(
                    path=f"{path}.timeout",
                    message=f"Invalid timeout format: {timeout}. Expected format: <number><unit> (e.g., 30s, 5m)",
                    severity="warning"
                ))

        # Warn if manual step has no approval_required
        if step.get("manual") and not step.get("approval_required"):
            errors.append(ValidationError(
                path=f"{path}.approval_required",
                message="Manual steps should typically require approval",
                severity="warning"
            ))

        return errors

    def _validate_metadata(self, metadata: Any) -> List[ValidationError]:
        """Validate metadata structure."""
        errors: List[ValidationError] = []

        if not isinstance(metadata, dict):
            errors.append(ValidationError(
                path="runbook.metadata",
                message="metadata must be a dict",
                severity="error"
            ))
            return errors

        # Check for recommended metadata fields
        recommended_fields = ["service", "environment", "severity", "owner"]
        for field in recommended_fields:
            if field not in metadata:
                errors.append(ValidationError(
                    path=f"runbook.metadata.{field}",
                    message=f"Recommended metadata field missing: {field}",
                    severity="warning"
                ))

        return errors

    def _validate_escalation(self, escalation: Any) -> List[ValidationError]:
        """Validate escalation structure."""
        errors: List[ValidationError] = []

        if not isinstance(escalation, dict):
            errors.append(ValidationError(
                path="runbook.escalation",
                message="escalation must be a dict",
                severity="error"
            ))
            return errors

        # Validate escalation levels
        for level_name, level_config in escalation.items():
            if not isinstance(level_config, dict):
                errors.append(ValidationError(
                    path=f"runbook.escalation.{level_name}",
                    message="Escalation level must be a dict",
                    severity="error"
                ))
                continue

            # Check for team or contact
            if "team" not in level_config and "contact" not in level_config:
                errors.append(ValidationError(
                    path=f"runbook.escalation.{level_name}",
                    message="Escalation level should have 'team' or 'contact' field",
                    severity="warning"
                ))

        return errors

    def _is_valid_duration(self, duration: str) -> bool:
        """Check if duration string is valid (e.g., 30s, 5m, 2h)."""
        if not duration:
            return False

        # Simple regex check for <number><unit>
        import re
        pattern = r'^\d+[smhd]$'
        return bool(re.match(pattern, duration))


def validate_runbook(runbook_yaml: str) -> List[ValidationError]:
    """
    Convenience function to validate a runbook.

    Args:
        runbook_yaml: YAML string containing runbook definition

    Returns:
        List of validation errors (empty if valid)
    """
    validator = RunbookValidator()
    return validator.validate(runbook_yaml)
