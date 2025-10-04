"""
Panel Template Library (T105)

Templated panels for latency, error rate, availability with variables
for service/environment.
Per research.md: Reusable panel templates with variables
"""
from typing import Dict, Any, Optional, List
from enum import Enum


class PanelType(str, Enum):
    """Types of panel templates"""
    LATENCY = "latency"
    ERROR_RATE = "error_rate"
    AVAILABILITY = "availability"
    THROUGHPUT = "throughput"
    CUSTOM = "custom"


class GrafanaPanelTemplates:
    """
    Library of reusable Grafana panel templates.

    Per research.md: Templated panels for latency, error rate, availability
    with variables for service/environment.
    """

    def __init__(self, datasource_uid: str = "${DS_PROMETHEUS}"):
        """
        Initialize panel templates.

        Args:
            datasource_uid: UID of Prometheus datasource
        """
        self.datasource_uid = datasource_uid

    def latency_panel(
        self,
        panel_id: int,
        service_var: str = "$service",
        environment_var: str = "$environment",
        percentile: float = 0.95,
        title: Optional[str] = None,
        unit: str = "s",
        grid_pos: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """
        Create a latency panel template.

        Args:
            panel_id: Unique panel ID
            service_var: Template variable for service (default: $service)
            environment_var: Template variable for environment
            percentile: Latency percentile to display (0.5, 0.95, 0.99)
            title: Panel title (default: auto-generated)
            unit: Unit for latency (s, ms, etc.)
            grid_pos: Grid position {x, y, w, h}

        Returns:
            Panel definition dict
        """
        percentile_str = str(int(percentile * 100))
        if not title:
            title = f"Latency P{percentile_str}"

        targets = [
            {
                "expr": f'histogram_quantile({percentile}, sum(rate(http_request_duration_seconds_bucket{{service="{service_var}", environment="{environment_var}"}}[$time_range])) by (le))',
                "legendFormat": f"P{percentile_str}",
                "refId": "A",
                "datasource": {"uid": self.datasource_uid}
            },
            {
                "expr": f'histogram_quantile(0.50, sum(rate(http_request_duration_seconds_bucket{{service="{service_var}", environment="{environment_var}"}}[$time_range])) by (le))',
                "legendFormat": "P50 (median)",
                "refId": "B",
                "datasource": {"uid": self.datasource_uid}
            },
            {
                "expr": f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket{{service="{service_var}", environment="{environment_var}"}}[$time_range])) by (le))',
                "legendFormat": "P99",
                "refId": "C",
                "datasource": {"uid": self.datasource_uid}
            }
        ]

        return {
            "id": panel_id,
            "title": title,
            "type": "timeseries",
            "gridPos": grid_pos or {"x": 0, "y": 0, "w": 12, "h": 8},
            "targets": targets,
            "options": {
                "tooltip": {"mode": "multi", "sort": "none"},
                "legend": {
                    "displayMode": "table",
                    "placement": "right",
                    "calcs": ["mean", "max", "last"]
                }
            },
            "fieldConfig": {
                "defaults": {
                    "unit": unit,
                    "custom": {
                        "axisPlacement": "auto",
                        "drawStyle": "line",
                        "lineInterpolation": "smooth",
                        "lineWidth": 2,
                        "fillOpacity": 10,
                        "showPoints": "never"
                    },
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": 0, "color": "green"},
                            {"value": 0.1, "color": "yellow"},
                            {"value": 0.5, "color": "red"}
                        ]
                    }
                }
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def error_rate_panel(
        self,
        panel_id: int,
        service_var: str = "$service",
        environment_var: str = "$environment",
        title: Optional[str] = None,
        grid_pos: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """
        Create an error rate panel template.

        Args:
            panel_id: Unique panel ID
            service_var: Template variable for service
            environment_var: Template variable for environment
            title: Panel title
            grid_pos: Grid position

        Returns:
            Panel definition dict
        """
        if not title:
            title = "Error Rate"

        targets = [
            {
                "expr": f'sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}", status=~"5.."}}[$time_range])) / sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}"}}[$time_range])) * 100',
                "legendFormat": "5xx Error Rate (%)",
                "refId": "A",
                "datasource": {"uid": self.datasource_uid}
            },
            {
                "expr": f'sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}", status=~"4.."}}[$time_range])) / sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}"}}[$time_range])) * 100',
                "legendFormat": "4xx Error Rate (%)",
                "refId": "B",
                "datasource": {"uid": self.datasource_uid}
            }
        ]

        return {
            "id": panel_id,
            "title": title,
            "type": "timeseries",
            "gridPos": grid_pos or {"x": 12, "y": 0, "w": 12, "h": 8},
            "targets": targets,
            "options": {
                "tooltip": {"mode": "multi", "sort": "none"},
                "legend": {
                    "displayMode": "table",
                    "placement": "right",
                    "calcs": ["mean", "max", "last"]
                }
            },
            "fieldConfig": {
                "defaults": {
                    "unit": "percent",
                    "min": 0,
                    "max": 100,
                    "custom": {
                        "axisPlacement": "auto",
                        "drawStyle": "line",
                        "lineInterpolation": "smooth",
                        "lineWidth": 2,
                        "fillOpacity": 20,
                        "showPoints": "never"
                    },
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": 0, "color": "green"},
                            {"value": 1, "color": "yellow"},
                            {"value": 5, "color": "red"}
                        ]
                    }
                }
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def availability_panel(
        self,
        panel_id: int,
        service_var: str = "$service",
        environment_var: str = "$environment",
        title: Optional[str] = None,
        grid_pos: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """
        Create an availability panel template.

        Args:
            panel_id: Unique panel ID
            service_var: Template variable for service
            environment_var: Template variable for environment
            title: Panel title
            grid_pos: Grid position

        Returns:
            Panel definition dict
        """
        if not title:
            title = "Availability"

        # Availability = (total requests - 5xx errors) / total requests * 100
        targets = [
            {
                "expr": f'(sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}"}}[$time_range])) - sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}", status=~"5.."}}[$time_range]))) / sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}"}}[$time_range])) * 100',
                "legendFormat": "Availability",
                "refId": "A",
                "datasource": {"uid": self.datasource_uid}
            }
        ]

        return {
            "id": panel_id,
            "title": title,
            "type": "stat",
            "gridPos": grid_pos or {"x": 0, "y": 8, "w": 8, "h": 4},
            "targets": targets,
            "options": {
                "orientation": "auto",
                "textMode": "value_and_name",
                "colorMode": "background",
                "graphMode": "area",
                "justifyMode": "auto"
            },
            "fieldConfig": {
                "defaults": {
                    "unit": "percent",
                    "min": 99,
                    "max": 100,
                    "decimals": 3,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": 0, "color": "red"},
                            {"value": 99.5, "color": "yellow"},
                            {"value": 99.9, "color": "green"}
                        ]
                    }
                }
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def throughput_panel(
        self,
        panel_id: int,
        service_var: str = "$service",
        environment_var: str = "$environment",
        title: Optional[str] = None,
        grid_pos: Dict[str, int] = None
    ) -> Dict[str, Any]:
        """
        Create a throughput (requests per second) panel template.

        Args:
            panel_id: Unique panel ID
            service_var: Template variable for service
            environment_var: Template variable for environment
            title: Panel title
            grid_pos: Grid position

        Returns:
            Panel definition dict
        """
        if not title:
            title = "Throughput (RPS)"

        targets = [
            {
                "expr": f'sum(rate(http_requests_total{{service="{service_var}", environment="{environment_var}"}}[$time_range]))',
                "legendFormat": "Requests/sec",
                "refId": "A",
                "datasource": {"uid": self.datasource_uid}
            }
        ]

        return {
            "id": panel_id,
            "title": title,
            "type": "timeseries",
            "gridPos": grid_pos or {"x": 8, "y": 8, "w": 16, "h": 4},
            "targets": targets,
            "options": {
                "tooltip": {"mode": "multi", "sort": "none"},
                "legend": {
                    "displayMode": "list",
                    "placement": "bottom",
                    "calcs": ["mean", "max"]
                }
            },
            "fieldConfig": {
                "defaults": {
                    "unit": "reqps",
                    "custom": {
                        "axisPlacement": "auto",
                        "drawStyle": "line",
                        "lineInterpolation": "smooth",
                        "lineWidth": 2,
                        "fillOpacity": 20,
                        "showPoints": "never"
                    }
                }
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def get_panel_by_type(
        self,
        panel_type: PanelType,
        panel_id: int,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get a panel by type using template.

        Args:
            panel_type: Type of panel to create
            panel_id: Unique panel ID
            **kwargs: Additional arguments for specific panel type

        Returns:
            Panel definition dict
        """
        panel_map = {
            PanelType.LATENCY: self.latency_panel,
            PanelType.ERROR_RATE: self.error_rate_panel,
            PanelType.AVAILABILITY: self.availability_panel,
            PanelType.THROUGHPUT: self.throughput_panel
        }

        panel_func = panel_map.get(panel_type)
        if not panel_func:
            raise ValueError(f"Unknown panel type: {panel_type}")

        return panel_func(panel_id, **kwargs)


def create_slo_dashboard_from_templates(
    service_name: str,
    environment: str,
    panel_types: List[PanelType] = None
) -> Dict[str, Any]:
    """
    Create a complete SLO dashboard using panel templates.

    Args:
        service_name: Service name
        environment: Environment
        panel_types: List of panel types to include (default: all)

    Returns:
        Dashboard definition dict
    """
    if panel_types is None:
        panel_types = [
            PanelType.LATENCY,
            PanelType.ERROR_RATE,
            PanelType.AVAILABILITY,
            PanelType.THROUGHPUT
        ]

    templates = GrafanaPanelTemplates()
    panels = []

    # Create panels with auto-layout
    y_position = 0
    panel_id = 1

    for panel_type in panel_types:
        if panel_type == PanelType.LATENCY:
            panel = templates.latency_panel(
                panel_id=panel_id,
                service_var=service_name,
                environment_var=environment,
                grid_pos={"x": 0, "y": y_position, "w": 24, "h": 8}
            )
            y_position += 8
        elif panel_type == PanelType.ERROR_RATE:
            panel = templates.error_rate_panel(
                panel_id=panel_id,
                service_var=service_name,
                environment_var=environment,
                grid_pos={"x": 0, "y": y_position, "w": 24, "h": 8}
            )
            y_position += 8
        elif panel_type == PanelType.AVAILABILITY:
            panel = templates.availability_panel(
                panel_id=panel_id,
                service_var=service_name,
                environment_var=environment,
                grid_pos={"x": 0, "y": y_position, "w": 12, "h": 4}
            )
        elif panel_type == PanelType.THROUGHPUT:
            panel = templates.throughput_panel(
                panel_id=panel_id,
                service_var=service_name,
                environment_var=environment,
                grid_pos={"x": 12, "y": y_position, "w": 12, "h": 4}
            )

        panels.append(panel)
        panel_id += 1

        # Move to next row after availability+throughput pair
        if panel_type == PanelType.THROUGHPUT:
            y_position += 4

    return {
        "title": f"{service_name.title()} SLO Dashboard",
        "panels": panels,
        "templating": {
            "list": [
                {"name": "service", "type": "constant", "current": {"value": service_name}},
                {"name": "environment", "type": "constant", "current": {"value": environment}},
                {"name": "time_range", "type": "interval", "current": {"value": "5m"}}
            ]
        }
    }
