"""
Grafana Dashboard Generator (T104)

Creates dashboard JSON with panels for SLI time series, SLO threshold line,
error budget gauge.
Per research.md: JSON model API v7+ with templating variables
"""
from typing import Dict, Any, List, Optional
from datetime import timedelta
import json


class GrafanaDashboardGenerator:
    """
    Generates Grafana dashboard JSON from SLO/SLI definitions.

    Per FR-007: Generated dashboards must be syntactically valid JSON.
    Per research.md: Format is JSON model API v7+ with templating variables
    for service, environment, time_range.
    """

    def __init__(self, datasource_uid: str = "${DS_PROMETHEUS}"):
        """
        Initialize dashboard generator.

        Args:
            datasource_uid: UID of Prometheus datasource (default uses templating variable)
        """
        self.datasource_uid = datasource_uid
        self.panel_id_counter = 1

    def generate(
        self,
        service_name: str,
        environment: str,
        slis: List[Dict[str, Any]],
        slos: List[Dict[str, Any]],
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: List[str] = None
    ) -> str:
        """
        Generate complete Grafana dashboard JSON.

        Args:
            service_name: Service name
            environment: Environment (prod, staging, etc.)
            slis: List of SLI definitions with 'name', 'metric_definition', 'unit'
            slos: List of SLO definitions with 'sli_name', 'threshold_value', 'time_window'
            title: Dashboard title (default: generated from service name)
            description: Dashboard description
            tags: Dashboard tags

        Returns:
            JSON string containing the dashboard definition

        Example:
            >>> generator = GrafanaDashboardGenerator()
            >>> dashboard = generator.generate(
            ...     service_name="checkout",
            ...     environment="prod",
            ...     slis=[{
            ...         "name": "checkout_latency_p95",
            ...         "metric_definition": "histogram_quantile(0.95, ...)",
            ...         "unit": "seconds"
            ...     }],
            ...     slos=[{
            ...         "sli_name": "checkout_latency_p95",
            ...         "threshold_value": 0.2,
            ...         "time_window": timedelta(hours=1)
            ...     }]
            ... )
        """
        if not title:
            title = f"{service_name.title()} SLO Dashboard - {environment}"

        # Create dashboard structure
        dashboard = {
            "title": title,
            "description": description or f"SLO monitoring dashboard for {service_name}",
            "tags": tags or ["slo", "sli", service_name, environment],
            "timezone": "browser",
            "editable": True,
            "graphTooltip": 1,  # Shared crosshair
            "time": {
                "from": "now-6h",
                "to": "now"
            },
            "timepicker": {
                "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h"]
            },
            "templating": self._create_template_variables(service_name, environment),
            "panels": [],
            "annotations": {
                "list": self._create_annotations()
            },
            "schemaVersion": 38,  # Grafana v7+ schema
            "version": 1,
            "refresh": "1m"
        }

        # Add panels for each SLI
        y_position = 0
        for sli in slis:
            # Find matching SLOs
            sli_slos = [slo for slo in slos if slo.get('sli_name') == sli['name']]

            # Create SLI time series panel
            panel = self._create_sli_timeseries_panel(
                sli=sli,
                slos=sli_slos,
                y_position=y_position
            )
            dashboard['panels'].append(panel)
            y_position += 8

            # Create error budget gauge if SLOs exist
            if sli_slos:
                gauge_panel = self._create_error_budget_gauge(
                    sli=sli,
                    slo=sli_slos[0],  # Use first SLO
                    y_position=y_position
                )
                dashboard['panels'].append(gauge_panel)
                y_position += 6

        return json.dumps({"dashboard": dashboard, "overwrite": True}, indent=2)

    def _create_template_variables(self, service_name: str, environment: str) -> Dict[str, Any]:
        """
        Create template variables for dashboard.

        Per research.md: Variables for service, environment, time_range
        """
        return {
            "list": [
                {
                    "name": "service",
                    "type": "constant",
                    "current": {
                        "value": service_name,
                        "text": service_name
                    },
                    "hide": 2,  # Hide variable
                    "label": "Service",
                    "query": service_name
                },
                {
                    "name": "environment",
                    "type": "constant",
                    "current": {
                        "value": environment,
                        "text": environment
                    },
                    "hide": 2,
                    "label": "Environment",
                    "query": environment
                },
                {
                    "name": "time_range",
                    "type": "interval",
                    "current": {
                        "value": "5m",
                        "text": "5m"
                    },
                    "options": [
                        {"text": "1m", "value": "1m"},
                        {"text": "5m", "value": "5m"},
                        {"text": "10m", "value": "10m"},
                        {"text": "30m", "value": "30m"},
                        {"text": "1h", "value": "1h"}
                    ],
                    "label": "Time Range",
                    "auto": True,
                    "auto_count": 30,
                    "auto_min": "10s"
                }
            ]
        }

    def _create_annotations(self) -> List[Dict[str, Any]]:
        """
        Create annotations configuration.

        Per research.md: Deployment events from Git webhooks
        """
        return [
            {
                "name": "Deployments",
                "datasource": self.datasource_uid,
                "enable": True,
                "iconColor": "green",
                "tags": ["deployment"]
            }
        ]

    def _create_sli_timeseries_panel(
        self,
        sli: Dict[str, Any],
        slos: List[Dict[str, Any]],
        y_position: int
    ) -> Dict[str, Any]:
        """
        Create time series panel for SLI with SLO threshold lines.

        Per research.md: Panel shows SLI time series + SLO threshold line
        """
        panel_id = self._get_next_panel_id()

        targets = [
            {
                "expr": sli['metric_definition'],
                "legendFormat": f"{sli['name']} - Actual",
                "refId": "A",
                "datasource": {"uid": self.datasource_uid}
            }
        ]

        # Add threshold lines for each SLO
        ref_id_ord = ord('B')
        for slo in slos:
            targets.append({
                "expr": str(slo['threshold_value']),
                "legendFormat": f"SLO Threshold ({slo.get('variant', 'balanced')})",
                "refId": chr(ref_id_ord),
                "datasource": {"uid": self.datasource_uid}
            })
            ref_id_ord += 1

        return {
            "id": panel_id,
            "title": f"{sli['name']} - SLI Monitoring",
            "type": "timeseries",
            "gridPos": {
                "x": 0,
                "y": y_position,
                "w": 24,
                "h": 8
            },
            "targets": targets,
            "options": {
                "tooltip": {
                    "mode": "multi",
                    "sort": "none"
                },
                "legend": {
                    "displayMode": "table",
                    "placement": "right",
                    "calcs": ["mean", "max", "last"]
                }
            },
            "fieldConfig": {
                "defaults": {
                    "unit": sli.get('unit', 'short'),
                    "custom": {
                        "axisPlacement": "auto",
                        "drawStyle": "line",
                        "lineInterpolation": "smooth",
                        "lineWidth": 2,
                        "fillOpacity": 10,
                        "showPoints": "never"
                    }
                },
                "overrides": [
                    {
                        "matcher": {"id": "byName", "options": "SLO Threshold*"},
                        "properties": [
                            {
                                "id": "custom.lineStyle",
                                "value": {"fill": "dash"}
                            },
                            {
                                "id": "color",
                                "value": {"mode": "fixed", "fixedColor": "red"}
                            }
                        ]
                    }
                ]
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def _create_error_budget_gauge(
        self,
        sli: Dict[str, Any],
        slo: Dict[str, Any],
        y_position: int
    ) -> Dict[str, Any]:
        """
        Create error budget gauge panel.

        Per research.md: Error budget gauge shows remaining budget
        """
        panel_id = self._get_next_panel_id()

        # Calculate error budget consumption query
        # This is a simplified version - real implementation would be more complex
        threshold = slo['threshold_value']
        metric = sli['metric_definition']

        # Error budget: (actual - threshold) / threshold * 100
        error_budget_query = f"(({metric}) - {threshold}) / {threshold} * 100"

        return {
            "id": panel_id,
            "title": f"{sli['name']} - Error Budget Remaining",
            "type": "gauge",
            "gridPos": {
                "x": 0,
                "y": y_position,
                "w": 12,
                "h": 6
            },
            "targets": [
                {
                    "expr": error_budget_query,
                    "refId": "A",
                    "datasource": {"uid": self.datasource_uid}
                }
            ],
            "options": {
                "orientation": "auto",
                "showThresholdLabels": True,
                "showThresholdMarkers": True
            },
            "fieldConfig": {
                "defaults": {
                    "unit": "percent",
                    "min": 0,
                    "max": 100,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {"value": 0, "color": "red"},
                            {"value": 25, "color": "orange"},
                            {"value": 50, "color": "yellow"},
                            {"value": 75, "color": "green"}
                        ]
                    }
                }
            },
            "datasource": {"uid": self.datasource_uid}
        }

    def _get_next_panel_id(self) -> int:
        """Get next panel ID and increment counter."""
        panel_id = self.panel_id_counter
        self.panel_id_counter += 1
        return panel_id


def generate_grafana_dashboard(
    service_name: str,
    environment: str,
    slis: List[Dict[str, Any]],
    slos: List[Dict[str, Any]],
    **kwargs
) -> str:
    """
    Convenience function to generate a Grafana dashboard.

    Args:
        service_name: Service name
        environment: Environment
        slis: List of SLI definitions
        slos: List of SLO definitions
        **kwargs: Additional arguments

    Returns:
        JSON string containing the dashboard
    """
    generator = GrafanaDashboardGenerator()
    return generator.generate(
        service_name=service_name,
        environment=environment,
        slis=slis,
        slos=slos,
        **kwargs
    )
