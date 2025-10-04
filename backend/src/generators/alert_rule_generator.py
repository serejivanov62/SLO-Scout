"""
Alert Rule Generator (T102)

Generates Prometheus alert rule YAML from SLO.
Per research.md: Include annotations summary/description/runbook_url
"""
from typing import Dict, Any, Optional
from datetime import timedelta
import yaml


class AlertRuleGenerator:
    """
    Generates Prometheus alert rules from SLO definitions.

    Per FR-006: Generated rules must pass promtool check rules validation.
    Per research.md: Alert rules include standard annotations (summary, description, runbook_url).
    """

    def generate(
        self,
        slo_id: str,
        sli_name: str,
        metric_definition: str,
        threshold_value: float,
        comparison_operator: str,
        time_window: timedelta,
        service_name: str,
        environment: str,
        severity: str = "major",
        runbook_url: Optional[str] = None,
        labels: Dict[str, str] = None,
        for_duration: timedelta = timedelta(minutes=5)
    ) -> str:
        """
        Generate alert rule YAML from SLO.

        Args:
            slo_id: SLO unique identifier
            sli_name: Name of the SLI
            metric_definition: PromQL expression for the SLI
            threshold_value: SLO threshold value
            comparison_operator: Comparison operator (lt, lte, gt, gte, eq)
            time_window: SLO time window
            service_name: Service name
            environment: Environment
            severity: Alert severity (critical, major, minor)
            runbook_url: URL to runbook (optional)
            labels: Additional labels for the alert
            for_duration: How long condition must be true before firing

        Returns:
            YAML string containing the alert rule

        Example:
            >>> generator = AlertRuleGenerator()
            >>> rule = generator.generate(
            ...     slo_id="uuid-123",
            ...     sli_name="checkout_latency_p95",
            ...     metric_definition='service:checkout_latency_p95:recording',
            ...     threshold_value=0.2,
            ...     comparison_operator="gt",
            ...     time_window=timedelta(hours=1),
            ...     service_name="checkout",
            ...     environment="prod",
            ...     severity="critical"
            ... )
        """
        # Generate alert name
        alert_name = self._generate_alert_name(service_name, sli_name, severity)

        # Build alert expression
        alert_expr = self._build_alert_expression(
            metric_definition=metric_definition,
            threshold_value=threshold_value,
            comparison_operator=comparison_operator,
            time_window=time_window
        )

        # Build labels
        alert_labels = {
            "service": service_name,
            "environment": environment,
            "severity": severity,
            "slo_id": slo_id,
            "sli_name": sli_name,
        }
        if labels:
            alert_labels.update(labels)

        # Build annotations
        annotations = self._build_annotations(
            sli_name=sli_name,
            service_name=service_name,
            threshold_value=threshold_value,
            comparison_operator=comparison_operator,
            time_window=time_window,
            runbook_url=runbook_url
        )

        # Create alert rule
        alert_rule = {
            "alert": alert_name,
            "expr": alert_expr,
            "for": self._format_duration(for_duration),
            "labels": alert_labels,
            "annotations": annotations
        }

        # Wrap in group
        group_name = f"{service_name}_slo_alerts"
        rule_file = {
            "groups": [
                {
                    "name": group_name,
                    "rules": [alert_rule]
                }
            ]
        }

        return yaml.dump(rule_file, default_flow_style=False, sort_keys=False)

    def _generate_alert_name(self, service_name: str, sli_name: str, severity: str) -> str:
        """
        Generate alert name from service, SLI, and severity.

        Format: ServiceNameSLINameSeverity
        Example: CheckoutLatencyP95Critical
        """
        # Convert to CamelCase
        service_parts = [p.capitalize() for p in service_name.replace('_', '-').split('-')]
        sli_parts = [p.capitalize() for p in sli_name.replace('_', '-').split('-')]
        severity_part = severity.capitalize()

        return f"{''.join(service_parts)}{''.join(sli_parts)}{severity_part}"

    def _build_alert_expression(
        self,
        metric_definition: str,
        threshold_value: float,
        comparison_operator: str,
        time_window: timedelta
    ) -> str:
        """
        Build PromQL alert expression.

        Args:
            metric_definition: Base metric (PromQL expression or recording rule)
            threshold_value: Threshold to compare against
            comparison_operator: Comparison operator
            time_window: Time window for aggregation

        Returns:
            PromQL expression for alert
        """
        # Map comparison operators to PromQL
        op_map = {
            "lt": "<",
            "lte": "<=",
            "gt": ">",
            "gte": ">=",
            "eq": "=="
        }

        operator = op_map.get(comparison_operator, ">")
        window_str = self._format_duration(time_window)

        # If metric_definition is a simple recording rule reference, use it directly
        # Otherwise, wrap in aggregation over time window
        if ':' in metric_definition and 'recording' in metric_definition:
            # This is likely a recording rule reference
            base_expr = metric_definition
        else:
            # This is a PromQL expression, might need time window
            base_expr = metric_definition

        # Build the comparison
        return f"{base_expr} {operator} {threshold_value}"

    def _build_annotations(
        self,
        sli_name: str,
        service_name: str,
        threshold_value: float,
        comparison_operator: str,
        time_window: timedelta,
        runbook_url: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Build alert annotations per research.md requirements.

        Required annotations: summary, description, runbook_url
        """
        # Human-readable operator
        op_text = {
            "lt": "is below",
            "lte": "is at or below",
            "gt": "is above",
            "gte": "is at or above",
            "eq": "equals"
        }.get(comparison_operator, "violates")

        summary = f"SLO violation: {sli_name} for {service_name}"

        description = (
            f"The SLI '{sli_name}' for service '{service_name}' {op_text} "
            f"the threshold of {threshold_value} over a {self._format_duration(time_window)} window. "
            f"This indicates an SLO breach that may impact user experience."
        )

        annotations = {
            "summary": summary,
            "description": description,
        }

        if runbook_url:
            annotations["runbook_url"] = runbook_url
        else:
            # Generate default runbook URL pattern
            safe_service = service_name.replace('_', '-')
            safe_sli = sli_name.replace('_', '-')
            annotations["runbook_url"] = (
                f"https://runbooks.example.com/{safe_service}/{safe_sli}"
            )

        return annotations

    def _format_duration(self, duration: timedelta) -> str:
        """Convert timedelta to Prometheus duration format."""
        seconds = int(duration.total_seconds())
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        elif seconds < 86400:
            return f"{seconds // 3600}h"
        else:
            return f"{seconds // 86400}d"


def generate_alert_rule(
    slo_id: str,
    sli_name: str,
    metric_definition: str,
    threshold_value: float,
    comparison_operator: str,
    time_window: timedelta,
    service_name: str,
    environment: str,
    **kwargs
) -> str:
    """
    Convenience function to generate a single alert rule.

    Args:
        slo_id: SLO unique identifier
        sli_name: Name of the SLI
        metric_definition: PromQL expression
        threshold_value: SLO threshold
        comparison_operator: Comparison operator
        time_window: SLO time window
        service_name: Service name
        environment: Environment
        **kwargs: Additional arguments

    Returns:
        YAML string containing the alert rule
    """
    generator = AlertRuleGenerator()
    return generator.generate(
        slo_id=slo_id,
        sli_name=sli_name,
        metric_definition=metric_definition,
        threshold_value=threshold_value,
        comparison_operator=comparison_operator,
        time_window=time_window,
        service_name=service_name,
        environment=environment,
        **kwargs
    )
