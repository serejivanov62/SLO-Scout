"""
Runbook Template Engine (T107)

Generate YAML runbook with diagnostic steps, mitigation actions.
Per spec.md FR-008: Generate executable runbook YAML templates
"""
from typing import List, Dict, Any, Optional
from datetime import timedelta
import yaml


class RunbookGenerator:
    """
    Generates operational runbook YAML from SLO definitions.

    Per FR-008: System MUST generate executable runbook YAML templates containing
    diagnostic steps, mitigation actions, and rollback procedures.
    """

    def generate(
        self,
        slo_id: str,
        sli_name: str,
        service_name: str,
        environment: str,
        severity: str,
        threshold_value: float,
        diagnostic_steps: Optional[List[Dict[str, Any]]] = None,
        mitigation_steps: Optional[List[Dict[str, Any]]] = None,
        rollback_steps: Optional[List[Dict[str, Any]]] = None,
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate runbook YAML from SLO definition.

        Args:
            slo_id: SLO unique identifier
            sli_name: Name of the SLI
            service_name: Service name
            environment: Environment
            severity: Alert severity (critical, major, minor)
            threshold_value: SLO threshold value
            diagnostic_steps: List of diagnostic step definitions
            mitigation_steps: List of mitigation action definitions
            rollback_steps: List of rollback procedure definitions
            additional_metadata: Additional metadata to include

        Returns:
            YAML string containing the runbook

        Example:
            >>> generator = RunbookGenerator()
            >>> runbook = generator.generate(
            ...     slo_id="uuid-123",
            ...     sli_name="checkout_latency_p95",
            ...     service_name="checkout",
            ...     environment="prod",
            ...     severity="critical",
            ...     threshold_value=0.2
            ... )
        """
        # Build runbook name
        runbook_name = self._generate_runbook_name(service_name, sli_name, severity)

        # Get default steps if not provided
        if diagnostic_steps is None:
            diagnostic_steps = self._get_default_diagnostic_steps(service_name, environment)

        if mitigation_steps is None:
            mitigation_steps = self._get_default_mitigation_steps(service_name, environment)

        if rollback_steps is None:
            rollback_steps = self._get_default_rollback_steps(service_name, environment)

        # Build runbook structure
        runbook = {
            "name": runbook_name,
            "version": "1.0",
            "slo_id": slo_id,
            "metadata": {
                "service": service_name,
                "environment": environment,
                "sli_name": sli_name,
                "severity": severity,
                "threshold_value": threshold_value,
                "owner": "sre-team",
                "tags": [service_name, environment, severity, "slo-breach"]
            },
            "triggers": [
                {
                    "type": "alert",
                    "alert_name": f"{service_name}_{sli_name}_{severity}",
                    "condition": f"SLO breach: {sli_name} exceeds {threshold_value}"
                }
            ],
            "steps": {
                "diagnostic": diagnostic_steps,
                "mitigation": mitigation_steps,
                "rollback": rollback_steps
            },
            "escalation": {
                "level_1": {
                    "team": "sre-team",
                    "slack_channel": f"#alerts-{service_name}",
                    "pagerduty_key": f"{service_name}-on-call"
                },
                "level_2": {
                    "team": "engineering-team",
                    "escalation_time": "15m",
                    "contact": f"{service_name}-team@example.com"
                }
            },
            "references": {
                "dashboard": f"https://grafana.example.com/d/{service_name}-slo",
                "documentation": f"https://docs.example.com/services/{service_name}",
                "incident_template": f"https://incidents.example.com/template/{service_name}"
            }
        }

        # Add additional metadata if provided
        if additional_metadata:
            runbook["metadata"].update(additional_metadata)

        return yaml.dump(runbook, default_flow_style=False, sort_keys=False)

    def _generate_runbook_name(self, service_name: str, sli_name: str, severity: str) -> str:
        """Generate runbook name from service, SLI, and severity."""
        safe_service = service_name.replace('_', '-')
        safe_sli = sli_name.replace('_', '-')
        return f"{safe_service}-{safe_sli}-{severity}-breach"

    def _get_default_diagnostic_steps(
        self,
        service_name: str,
        environment: str
    ) -> List[Dict[str, Any]]:
        """
        Get default diagnostic steps.

        Per research.md: Include kubectl logs, rollout status, etc.
        """
        return [
            {
                "name": "check_pod_status",
                "description": "Verify pod health and readiness",
                "command": f"kubectl get pods -n {environment} -l app={service_name}",
                "expected_output": "All pods in Running state",
                "timeout": "30s"
            },
            {
                "name": "check_recent_logs",
                "description": "Review recent application logs for errors",
                "command": f"kubectl logs -n {environment} -l app={service_name} --tail=100 | grep -i error",
                "expected_output": "No critical errors in recent logs",
                "timeout": "60s"
            },
            {
                "name": "check_resource_usage",
                "description": "Check CPU and memory usage",
                "command": f"kubectl top pods -n {environment} -l app={service_name}",
                "expected_output": "Resources within acceptable limits",
                "timeout": "30s"
            },
            {
                "name": "check_deployment_status",
                "description": "Verify deployment rollout status",
                "command": f"kubectl rollout status deployment/{service_name} -n {environment}",
                "expected_output": "Deployment successfully rolled out",
                "timeout": "60s"
            },
            {
                "name": "check_recent_changes",
                "description": "Identify recent deployments or config changes",
                "command": f"kubectl rollout history deployment/{service_name} -n {environment}",
                "expected_output": "Review recent revisions",
                "timeout": "30s"
            },
            {
                "name": "check_dependencies",
                "description": "Verify downstream service health",
                "command": "# Check service mesh or API gateway for dependency status",
                "manual": True,
                "timeout": "120s"
            }
        ]

    def _get_default_mitigation_steps(
        self,
        service_name: str,
        environment: str
    ) -> List[Dict[str, Any]]:
        """
        Get default mitigation steps.

        Per research.md: Include scale deployment, rollback, etc.
        """
        return [
            {
                "name": "increase_replicas",
                "description": "Scale up replicas to handle increased load",
                "command": f"kubectl scale deployment/{service_name} -n {environment} --replicas=5",
                "approval_required": True,
                "blast_radius": "medium",
                "timeout": "120s"
            },
            {
                "name": "restart_pods",
                "description": "Restart pods to clear transient issues",
                "command": f"kubectl rollout restart deployment/{service_name} -n {environment}",
                "approval_required": True,
                "blast_radius": "high",
                "timeout": "300s"
            },
            {
                "name": "adjust_rate_limits",
                "description": "Temporarily adjust rate limits to protect service",
                "command": "# Update rate limit configuration in API gateway",
                "manual": True,
                "approval_required": True,
                "blast_radius": "medium",
                "timeout": "60s"
            },
            {
                "name": "enable_circuit_breaker",
                "description": "Enable circuit breaker for failing dependencies",
                "command": "# Configure circuit breaker in service mesh",
                "manual": True,
                "approval_required": True,
                "blast_radius": "medium",
                "timeout": "60s"
            }
        ]

    def _get_default_rollback_steps(
        self,
        service_name: str,
        environment: str
    ) -> List[Dict[str, Any]]:
        """
        Get default rollback steps.

        Per spec.md FR-008: Include rollback procedures
        """
        return [
            {
                "name": "identify_last_good_revision",
                "description": "Identify the last known good deployment revision",
                "command": f"kubectl rollout history deployment/{service_name} -n {environment}",
                "timeout": "30s"
            },
            {
                "name": "rollback_deployment",
                "description": "Rollback to previous stable revision",
                "command": f"kubectl rollout undo deployment/{service_name} -n {environment}",
                "approval_required": True,
                "blast_radius": "high",
                "timeout": "300s"
            },
            {
                "name": "verify_rollback",
                "description": "Verify rollback succeeded and metrics improved",
                "command": f"kubectl rollout status deployment/{service_name} -n {environment}",
                "timeout": "120s"
            },
            {
                "name": "monitor_post_rollback",
                "description": "Monitor SLI for 10 minutes post-rollback",
                "command": "# Check Grafana dashboard for SLI recovery",
                "manual": True,
                "timeout": "600s"
            }
        ]


def generate_runbook(
    slo_id: str,
    sli_name: str,
    service_name: str,
    environment: str,
    severity: str,
    threshold_value: float,
    **kwargs
) -> str:
    """
    Convenience function to generate a runbook.

    Args:
        slo_id: SLO unique identifier
        sli_name: Name of the SLI
        service_name: Service name
        environment: Environment
        severity: Alert severity
        threshold_value: SLO threshold
        **kwargs: Additional arguments

    Returns:
        YAML string containing the runbook
    """
    generator = RunbookGenerator()
    return generator.generate(
        slo_id=slo_id,
        sli_name=sli_name,
        service_name=service_name,
        environment=environment,
        severity=severity,
        threshold_value=threshold_value,
        **kwargs
    )
