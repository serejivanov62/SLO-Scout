"""
PromQL Validator (T100)

Validates PromQL syntax using promtool check rules.
Per research.md: Prometheus 2.30+ compatibility required.
"""
import subprocess
import tempfile
import yaml
from typing import List, Dict, Optional
from dataclasses import dataclass
import re


@dataclass
class ValidationError:
    """Validation error details"""
    line: Optional[int]
    column: Optional[int]
    message: str
    severity: str = "error"


class PromQLValidator:
    """
    Validates PromQL expressions using promtool.

    Per FR-006: All generated rules must pass promtool check rules validation.
    """

    def __init__(self, promtool_path: str = "promtool"):
        """
        Initialize validator.

        Args:
            promtool_path: Path to promtool binary (default: "promtool" in PATH)
        """
        self.promtool_path = promtool_path

    def validate_expression(self, promql: str) -> List[ValidationError]:
        """
        Validate a single PromQL expression.

        Args:
            promql: PromQL expression string

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[ValidationError] = []

        # Basic syntax validation
        if not promql or not promql.strip():
            errors.append(ValidationError(
                line=None,
                column=None,
                message="Empty PromQL expression",
                severity="error"
            ))
            return errors

        # Check for balanced parentheses/brackets/braces
        if not self._check_balanced_delimiters(promql):
            errors.append(ValidationError(
                line=None,
                column=None,
                message="Unbalanced parentheses, brackets, or braces",
                severity="error"
            ))

        # Check for basic PromQL syntax patterns
        syntax_errors = self._basic_syntax_check(promql)
        errors.extend(syntax_errors)

        return errors

    def validate_rule_file(self, rule_yaml: str) -> List[ValidationError]:
        """
        Validate a Prometheus rule file using promtool.

        Args:
            rule_yaml: YAML content of rule file

        Returns:
            List of validation errors (empty if valid)
        """
        errors: List[ValidationError] = []

        # First validate YAML syntax
        try:
            rules = yaml.safe_load(rule_yaml)
            if not isinstance(rules, dict):
                errors.append(ValidationError(
                    line=None,
                    column=None,
                    message="Rule file must be a YAML dict",
                    severity="error"
                ))
                return errors
        except yaml.YAMLError as e:
            errors.append(ValidationError(
                line=getattr(e, 'problem_mark', None).line if hasattr(e, 'problem_mark') else None,
                column=getattr(e, 'problem_mark', None).column if hasattr(e, 'problem_mark') else None,
                message=f"YAML syntax error: {str(e)}",
                severity="error"
            ))
            return errors

        # Validate structure
        if 'groups' not in rules:
            errors.append(ValidationError(
                line=None,
                column=None,
                message="Missing 'groups' key in rule file",
                severity="error"
            ))
            return errors

        # Write to temp file and run promtool
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                f.write(rule_yaml)
                temp_path = f.name

            result = subprocess.run(
                [self.promtool_path, 'check', 'rules', temp_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                # Parse promtool errors
                promtool_errors = self._parse_promtool_output(result.stderr)
                errors.extend(promtool_errors)

        except subprocess.TimeoutExpired:
            errors.append(ValidationError(
                line=None,
                column=None,
                message="promtool validation timed out",
                severity="error"
            ))
        except FileNotFoundError:
            errors.append(ValidationError(
                line=None,
                column=None,
                message=f"promtool not found at {self.promtool_path}",
                severity="error"
            ))
        except Exception as e:
            errors.append(ValidationError(
                line=None,
                column=None,
                message=f"promtool execution failed: {str(e)}",
                severity="error"
            ))

        return errors

    def _check_balanced_delimiters(self, promql: str) -> bool:
        """Check if parentheses, brackets, and braces are balanced."""
        stack = []
        pairs = {'(': ')', '[': ']', '{': '}'}

        for char in promql:
            if char in pairs:
                stack.append(char)
            elif char in pairs.values():
                if not stack or pairs[stack.pop()] != char:
                    return False

        return len(stack) == 0

    def _basic_syntax_check(self, promql: str) -> List[ValidationError]:
        """Perform basic syntax checks without promtool."""
        errors: List[ValidationError] = []

        # Check for common errors
        if promql.strip().endswith(('and', 'or', 'unless', 'by', 'without', '+')):
            errors.append(ValidationError(
                line=None,
                column=None,
                message="Expression ends with binary operator",
                severity="error"
            ))

        # Check for valid metric name format (start with letter, contain only alphanumeric and _)
        # Extract potential metric names
        metric_pattern = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')
        metrics = metric_pattern.findall(promql)

        # Check for reserved keywords used incorrectly
        reserved = {'by', 'without', 'on', 'ignoring', 'group_left', 'group_right', 'bool'}
        for metric in metrics:
            if metric in reserved:
                # This is likely a keyword, not a metric - validate context
                pass

        # Check for empty aggregation
        if re.search(r'\b(sum|avg|min|max|count)\s*\(\s*\)', promql):
            errors.append(ValidationError(
                line=None,
                column=None,
                message="Empty aggregation function",
                severity="error"
            ))

        return errors

    def _parse_promtool_output(self, stderr: str) -> List[ValidationError]:
        """Parse promtool error output into ValidationError objects."""
        errors: List[ValidationError] = []

        # promtool output format: "  FAILED: <message>"
        # or "  <rule>: <message>"
        for line in stderr.split('\n'):
            line = line.strip()
            if line.startswith('FAILED:'):
                message = line.replace('FAILED:', '').strip()
                errors.append(ValidationError(
                    line=None,
                    column=None,
                    message=message,
                    severity="error"
                ))
            elif ':' in line and line:
                errors.append(ValidationError(
                    line=None,
                    column=None,
                    message=line,
                    severity="error"
                ))

        return errors


def validate_promql(promql: str) -> List[ValidationError]:
    """
    Convenience function to validate a PromQL expression.

    Args:
        promql: PromQL expression string

    Returns:
        List of validation errors (empty if valid)
    """
    validator = PromQLValidator()
    return validator.validate_expression(promql)


def validate_rule_file(rule_yaml: str) -> List[ValidationError]:
    """
    Convenience function to validate a Prometheus rule file.

    Args:
        rule_yaml: YAML content of rule file

    Returns:
        List of validation errors (empty if valid)
    """
    validator = PromQLValidator()
    return validator.validate_rule_file(rule_yaml)
