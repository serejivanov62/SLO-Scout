"""
Runbook Step Library (T108)

Template steps for kubectl logs, rollout status, scale deployment, rollback.
Per research.md: Reusable runbook step templates
"""
from typing import Dict, Any, List, Optional
from enum import Enum


class StepType(str, Enum):
    """Types of runbook steps"""
    DIAGNOSTIC = "diagnostic"
    MITIGATION = "mitigation"
    ROLLBACK = "rollback"
    VERIFICATION = "verification"


class RunbookStepLibrary:
    """
    Library of reusable runbook step templates.

    Per research.md: Template steps for kubectl logs, rollout status,
    scale deployment, rollback per runbook example.
    """

    @staticmethod
    def kubectl_logs(
        service_name: str,
        namespace: str,
        tail_lines: int = 100,
        since: str = "5m",
        grep_pattern: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Template for kubectl logs command.

        Args:
            service_name: Service/deployment name
            namespace: Kubernetes namespace
            tail_lines: Number of log lines to retrieve
            since: Time window (e.g., "5m", "1h")
            grep_pattern: Optional grep pattern to filter logs

        Returns:
            Step definition dict
        """
        command = f"kubectl logs -n {namespace} -l app={service_name} --tail={tail_lines} --since={since}"

        if grep_pattern:
            command += f" | grep -i '{grep_pattern}'"

        return {
            "name": "check_logs",
            "description": f"Review recent logs for {service_name}",
            "command": command,
            "expected_output": "No critical errors in logs" if grep_pattern == "error" else "Review log output",
            "timeout": "60s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def kubectl_rollout_status(
        service_name: str,
        namespace: str,
        resource_type: str = "deployment"
    ) -> Dict[str, Any]:
        """
        Template for kubectl rollout status command.

        Args:
            service_name: Service/deployment name
            namespace: Kubernetes namespace
            resource_type: Resource type (deployment, statefulset, daemonset)

        Returns:
            Step definition dict
        """
        return {
            "name": "check_rollout_status",
            "description": f"Verify {resource_type} rollout status",
            "command": f"kubectl rollout status {resource_type}/{service_name} -n {namespace}",
            "expected_output": f"{resource_type.title()} successfully rolled out",
            "timeout": "120s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def kubectl_get_pods(
        service_name: str,
        namespace: str,
        show_labels: bool = True
    ) -> Dict[str, Any]:
        """
        Template for kubectl get pods command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace
            show_labels: Whether to show pod labels

        Returns:
            Step definition dict
        """
        command = f"kubectl get pods -n {namespace} -l app={service_name}"
        if show_labels:
            command += " --show-labels"

        return {
            "name": "check_pod_status",
            "description": "Verify pod health and readiness",
            "command": command,
            "expected_output": "All pods in Running state with X/X ready",
            "timeout": "30s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def kubectl_top_pods(
        service_name: str,
        namespace: str
    ) -> Dict[str, Any]:
        """
        Template for kubectl top pods command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace

        Returns:
            Step definition dict
        """
        return {
            "name": "check_resource_usage",
            "description": "Check CPU and memory usage",
            "command": f"kubectl top pods -n {namespace} -l app={service_name}",
            "expected_output": "Resources within acceptable limits",
            "timeout": "30s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def kubectl_describe_pods(
        service_name: str,
        namespace: str
    ) -> Dict[str, Any]:
        """
        Template for kubectl describe pods command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace

        Returns:
            Step definition dict
        """
        return {
            "name": "describe_pods",
            "description": "Get detailed pod information and events",
            "command": f"kubectl describe pods -n {namespace} -l app={service_name}",
            "expected_output": "Review pod events for issues",
            "timeout": "60s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def kubectl_scale_deployment(
        service_name: str,
        namespace: str,
        replicas: int,
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Template for kubectl scale deployment command.

        Args:
            service_name: Deployment name
            namespace: Kubernetes namespace
            replicas: Target replica count
            require_approval: Whether to require approval before execution

        Returns:
            Step definition dict
        """
        return {
            "name": "scale_deployment",
            "description": f"Scale {service_name} to {replicas} replicas",
            "command": f"kubectl scale deployment/{service_name} -n {namespace} --replicas={replicas}",
            "expected_output": f"Deployment scaled to {replicas} replicas",
            "approval_required": require_approval,
            "blast_radius": "medium" if replicas > 3 else "low",
            "timeout": "120s",
            "type": StepType.MITIGATION.value
        }

    @staticmethod
    def kubectl_rollout_restart(
        service_name: str,
        namespace: str,
        resource_type: str = "deployment",
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Template for kubectl rollout restart command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace
            resource_type: Resource type
            require_approval: Whether to require approval

        Returns:
            Step definition dict
        """
        return {
            "name": "restart_deployment",
            "description": f"Restart {service_name} to clear transient issues",
            "command": f"kubectl rollout restart {resource_type}/{service_name} -n {namespace}",
            "expected_output": f"{resource_type.title()} restarted successfully",
            "approval_required": require_approval,
            "blast_radius": "high",
            "timeout": "300s",
            "type": StepType.MITIGATION.value
        }

    @staticmethod
    def kubectl_rollout_undo(
        service_name: str,
        namespace: str,
        resource_type: str = "deployment",
        to_revision: Optional[int] = None,
        require_approval: bool = True
    ) -> Dict[str, Any]:
        """
        Template for kubectl rollout undo command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace
            resource_type: Resource type
            to_revision: Specific revision to rollback to (None = previous)
            require_approval: Whether to require approval

        Returns:
            Step definition dict
        """
        command = f"kubectl rollout undo {resource_type}/{service_name} -n {namespace}"
        if to_revision:
            command += f" --to-revision={to_revision}"

        return {
            "name": "rollback_deployment",
            "description": f"Rollback {service_name} to previous stable version",
            "command": command,
            "expected_output": "Rollback completed successfully",
            "approval_required": require_approval,
            "blast_radius": "high",
            "timeout": "300s",
            "type": StepType.ROLLBACK.value
        }

    @staticmethod
    def kubectl_rollout_history(
        service_name: str,
        namespace: str,
        resource_type: str = "deployment"
    ) -> Dict[str, Any]:
        """
        Template for kubectl rollout history command.

        Args:
            service_name: Service name
            namespace: Kubernetes namespace
            resource_type: Resource type

        Returns:
            Step definition dict
        """
        return {
            "name": "check_rollout_history",
            "description": "View deployment revision history",
            "command": f"kubectl rollout history {resource_type}/{service_name} -n {namespace}",
            "expected_output": "Review revision history",
            "timeout": "30s",
            "type": StepType.DIAGNOSTIC.value
        }

    @staticmethod
    def check_metrics(
        service_name: str,
        metric_name: str,
        prometheus_url: str = "http://prometheus:9090"
    ) -> Dict[str, Any]:
        """
        Template for checking Prometheus metrics.

        Args:
            service_name: Service name
            metric_name: Metric to check
            prometheus_url: Prometheus server URL

        Returns:
            Step definition dict
        """
        return {
            "name": "check_metrics",
            "description": f"Check {metric_name} metric for {service_name}",
            "command": f"curl -s '{prometheus_url}/api/v1/query?query={metric_name}{{service=\"{service_name}\"}}'",
            "expected_output": "Review metric values",
            "timeout": "30s",
            "type": StepType.VERIFICATION.value
        }

    @staticmethod
    def verify_sli_recovery(
        service_name: str,
        sli_name: str,
        threshold_value: float,
        duration_minutes: int = 5
    ) -> Dict[str, Any]:
        """
        Template for verifying SLI recovery after mitigation.

        Args:
            service_name: Service name
            sli_name: SLI name
            threshold_value: SLO threshold
            duration_minutes: How long to monitor

        Returns:
            Step definition dict
        """
        return {
            "name": "verify_sli_recovery",
            "description": f"Monitor {sli_name} for {duration_minutes} minutes to verify recovery",
            "command": f"# Check Grafana dashboard or run: watch -n 30 'promtool query instant prometheus:9090 {sli_name}'",
            "expected_output": f"SLI remains below {threshold_value} for {duration_minutes} minutes",
            "manual": True,
            "timeout": f"{duration_minutes * 60}s",
            "type": StepType.VERIFICATION.value
        }


def create_diagnostic_sequence(
    service_name: str,
    namespace: str
) -> List[Dict[str, Any]]:
    """
    Create a standard diagnostic sequence.

    Args:
        service_name: Service name
        namespace: Kubernetes namespace

    Returns:
        List of diagnostic step definitions
    """
    lib = RunbookStepLibrary()
    return [
        lib.kubectl_get_pods(service_name, namespace),
        lib.kubectl_rollout_status(service_name, namespace),
        lib.kubectl_top_pods(service_name, namespace),
        lib.kubectl_logs(service_name, namespace, grep_pattern="error"),
        lib.kubectl_rollout_history(service_name, namespace),
        lib.kubectl_describe_pods(service_name, namespace)
    ]


def create_scale_mitigation_sequence(
    service_name: str,
    namespace: str,
    target_replicas: int
) -> List[Dict[str, Any]]:
    """
    Create a scale-based mitigation sequence.

    Args:
        service_name: Service name
        namespace: Kubernetes namespace
        target_replicas: Target replica count

    Returns:
        List of mitigation step definitions
    """
    lib = RunbookStepLibrary()
    return [
        lib.kubectl_scale_deployment(service_name, namespace, target_replicas),
        lib.kubectl_rollout_status(service_name, namespace),
        lib.kubectl_get_pods(service_name, namespace)
    ]


def create_rollback_sequence(
    service_name: str,
    namespace: str,
    to_revision: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Create a rollback sequence.

    Args:
        service_name: Service name
        namespace: Kubernetes namespace
        to_revision: Specific revision to rollback to

    Returns:
        List of rollback step definitions
    """
    lib = RunbookStepLibrary()
    return [
        lib.kubectl_rollout_history(service_name, namespace),
        lib.kubectl_rollout_undo(service_name, namespace, to_revision=to_revision),
        lib.kubectl_rollout_status(service_name, namespace),
        lib.kubectl_get_pods(service_name, namespace)
    ]
