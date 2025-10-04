"""
Recording Rule Generator (T101)

Generates Prometheus recording rule YAML from SLI metric_definition.
Per research.md: Follow naming convention job:metric:operation
"""
from typing import Dict, Any, List
import yaml
from datetime import timedelta


class RecordingRuleGenerator:
    """
    Generates Prometheus recording rules from SLI definitions.

    Per FR-006: Generated rules must pass promtool check rules validation.
    Per research.md: Recording rules follow job:metric:operation naming convention.
    """

    def generate(
        self,
        sli_name: str,
        metric_definition: str,
        service_name: str,
        environment: str,
        evaluation_interval: timedelta = timedelta(minutes=1),
        labels: Dict[str, str] = None
    ) -> str:
        """
        Generate recording rule YAML from SLI.

        Args:
            sli_name: Name of the SLI (e.g., "checkout_latency_p95")
            metric_definition: PromQL expression for the metric
            service_name: Service name (used in job label)
            environment: Environment (prod, staging, etc.)
            evaluation_interval: How often to evaluate the rule
            labels: Additional labels to add to the recording rule

        Returns:
            YAML string containing the recording rule

        Example:
            >>> generator = RecordingRuleGenerator()
            >>> rule = generator.generate(
            ...     sli_name="checkout_latency_p95",
            ...     metric_definition='histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))',
            ...     service_name="checkout",
            ...     environment="prod"
            ... )
        """
        # Generate rule name following job:metric:operation convention
        # Format: service:sli_name:interval
        rule_name = self._generate_rule_name(service_name, sli_name)

        # Build labels
        rule_labels = {
            "service": service_name,
            "environment": environment,
            "sli_name": sli_name,
        }
        if labels:
            rule_labels.update(labels)

        # Create rule structure
        rule = {
            "record": rule_name,
            "expr": metric_definition,
            "labels": rule_labels
        }

        # Wrap in group
        group_name = f"{service_name}_sli_recording_rules"
        rule_file = {
            "groups": [
                {
                    "name": group_name,
                    "interval": f"{int(evaluation_interval.total_seconds())}s",
                    "rules": [rule]
                }
            ]
        }

        return yaml.dump(rule_file, default_flow_style=False, sort_keys=False)

    def generate_batch(
        self,
        slis: List[Dict[str, Any]],
        service_name: str,
        environment: str,
        evaluation_interval: timedelta = timedelta(minutes=1)
    ) -> str:
        """
        Generate recording rules for multiple SLIs in a single file.

        Args:
            slis: List of SLI dicts with 'name' and 'metric_definition' keys
            service_name: Service name
            environment: Environment
            evaluation_interval: How often to evaluate the rules

        Returns:
            YAML string containing all recording rules
        """
        rules = []

        for sli in slis:
            rule_name = self._generate_rule_name(service_name, sli['name'])
            rule = {
                "record": rule_name,
                "expr": sli['metric_definition'],
                "labels": {
                    "service": service_name,
                    "environment": environment,
                    "sli_name": sli['name'],
                }
            }
            rules.append(rule)

        group_name = f"{service_name}_sli_recording_rules"
        rule_file = {
            "groups": [
                {
                    "name": group_name,
                    "interval": f"{int(evaluation_interval.total_seconds())}s",
                    "rules": rules
                }
            ]
        }

        return yaml.dump(rule_file, default_flow_style=False, sort_keys=False)

    def _generate_rule_name(self, service_name: str, sli_name: str) -> str:
        """
        Generate recording rule name following job:metric:operation convention.

        Per research.md: Recording rules follow naming convention job:metric:operation

        Args:
            service_name: Service name (job component)
            sli_name: SLI name (metric component)

        Returns:
            Rule name in format "service:sli_name:recording"
        """
        # Sanitize names (replace invalid characters with _)
        safe_service = service_name.replace('-', '_').replace('.', '_')
        safe_sli = sli_name.replace('-', '_').replace('.', '_')

        # Format: job:metric:operation
        return f"{safe_service}:{safe_sli}:recording"

    def _sanitize_interval(self, interval: timedelta) -> str:
        """Convert timedelta to Prometheus duration format."""
        seconds = int(interval.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"


def generate_recording_rule(
    sli_name: str,
    metric_definition: str,
    service_name: str,
    environment: str,
    **kwargs
) -> str:
    """
    Convenience function to generate a single recording rule.

    Args:
        sli_name: Name of the SLI
        metric_definition: PromQL expression
        service_name: Service name
        environment: Environment
        **kwargs: Additional arguments passed to generator

    Returns:
        YAML string containing the recording rule
    """
    generator = RecordingRuleGenerator()
    return generator.generate(
        sli_name=sli_name,
        metric_definition=metric_definition,
        service_name=service_name,
        environment=environment,
        **kwargs
    )
