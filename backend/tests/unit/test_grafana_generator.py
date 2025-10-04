"""
Unit tests for Grafana Dashboard Generator (T112)

Per task requirements:
- Assert JSON schema valid
- Assert panels contain SLI queries
- Test coverage >95%
- Mock external dependencies
- Test edge cases
"""
import pytest
import json
from datetime import timedelta
from typing import Dict, Any, List

from src.generators.grafana_generator import (
    GrafanaDashboardGenerator,
    generate_grafana_dashboard,
)


class TestGrafanaDashboardGenerator:
    """Test Grafana dashboard generation"""

    @pytest.fixture
    def generator(self) -> GrafanaDashboardGenerator:
        """Create Grafana dashboard generator instance"""
        return GrafanaDashboardGenerator()

    @pytest.fixture
    def sample_slis(self) -> List[Dict[str, Any]]:
        """Sample SLI definitions"""
        return [
            {
                "name": "checkout_latency_p95",
                "metric_definition": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
                "unit": "ms",
            },
            {
                "name": "checkout_error_rate",
                "metric_definition": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) * 100",
                "unit": "%",
            },
        ]

    @pytest.fixture
    def sample_slos(self) -> List[Dict[str, Any]]:
        """Sample SLO definitions"""
        return [
            {
                "sli_name": "checkout_latency_p95",
                "threshold_value": 200,
                "time_window": timedelta(hours=1),
            },
            {
                "sli_name": "checkout_error_rate",
                "threshold_value": 1.0,
                "time_window": timedelta(hours=1),
            },
        ]

    def test_generate_returns_valid_json(self, generator, sample_slis, sample_slos):
        """Test that generated output is valid JSON"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )

        # Should not raise exception
        parsed = json.loads(result)
        assert isinstance(parsed, dict)
        assert "dashboard" in parsed

    def test_json_structure_has_required_fields(self, generator, sample_slis, sample_slos):
        """Test JSON contains all required Grafana dashboard fields"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        dashboard = parsed["dashboard"]
        assert "title" in dashboard
        assert "panels" in dashboard
        assert "templating" in dashboard
        assert "time" in dashboard
        assert "schemaVersion" in dashboard

    def test_dashboard_has_overwrite_true(self, generator, sample_slis, sample_slos):
        """Test dashboard has overwrite flag set to true"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert parsed["overwrite"] is True

    def test_panels_contain_sli_queries(self, generator, sample_slis, sample_slos):
        """Test panels contain the SLI PromQL queries"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panels = parsed["dashboard"]["panels"]

        # Find panel with latency query
        latency_panel_found = False
        for panel in panels:
            if "targets" in panel:
                for target in panel["targets"]:
                    if "histogram_quantile(0.95" in target.get("expr", ""):
                        latency_panel_found = True
                        break

        assert latency_panel_found, "Should have panel with latency SLI query"

    def test_panels_contain_error_rate_query(self, generator, sample_slis, sample_slos):
        """Test panels contain error rate SLI query"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panels = parsed["dashboard"]["panels"]

        error_panel_found = False
        for panel in panels:
            if "targets" in panel:
                for target in panel["targets"]:
                    if 'status=~"5.."' in target.get("expr", ""):
                        error_panel_found = True
                        break

        assert error_panel_found, "Should have panel with error rate SLI query"

    def test_creates_timeseries_panel_for_each_sli(self, generator, sample_slis, sample_slos):
        """Test creates time series panel for each SLI"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panels = parsed["dashboard"]["panels"]
        timeseries_panels = [p for p in panels if p.get("type") == "timeseries"]

        # Should have at least one timeseries panel per SLI
        assert len(timeseries_panels) >= len(sample_slis)

    def test_creates_error_budget_gauge(self, generator, sample_slis, sample_slos):
        """Test creates error budget gauge panels"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panels = parsed["dashboard"]["panels"]
        gauge_panels = [p for p in panels if p.get("type") == "gauge"]

        assert len(gauge_panels) > 0, "Should have at least one gauge panel"

    def test_slo_threshold_lines_added_to_panels(self, generator, sample_slis, sample_slos):
        """Test SLO threshold lines are added to time series panels"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        # Find latency panel
        for panel in parsed["dashboard"]["panels"]:
            if "checkout_latency_p95" in panel.get("title", ""):
                targets = panel.get("targets", [])
                # Should have at least 2 targets: actual metric + threshold
                assert len(targets) >= 2

                # Check for threshold target
                threshold_found = False
                for target in targets:
                    if target.get("expr") == "200":
                        threshold_found = True
                        break

                assert threshold_found, "Should have threshold line target"
                break

    def test_panel_titles_include_sli_names(self, generator, sample_slis, sample_slos):
        """Test panel titles include SLI names"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panels = parsed["dashboard"]["panels"]
        titles = [p.get("title", "") for p in panels]

        assert any("checkout_latency_p95" in t for t in titles)
        assert any("checkout_error_rate" in t for t in titles)

    def test_dashboard_title_includes_service_and_environment(self, generator, sample_slis, sample_slos):
        """Test dashboard title includes service name and environment"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        title = parsed["dashboard"]["title"]
        assert "checkout" in title.lower()
        assert "prod" in title.lower()

    def test_custom_dashboard_title(self, generator, sample_slis, sample_slos):
        """Test custom dashboard title is used"""
        custom_title = "My Custom SLO Dashboard"
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
            title=custom_title,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["title"] == custom_title

    def test_dashboard_description(self, generator, sample_slis, sample_slos):
        """Test dashboard has description"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert "description" in parsed["dashboard"]
        assert len(parsed["dashboard"]["description"]) > 0

    def test_custom_dashboard_description(self, generator, sample_slis, sample_slos):
        """Test custom dashboard description is used"""
        custom_desc = "Custom description for testing"
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
            description=custom_desc,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["description"] == custom_desc

    def test_dashboard_tags_include_defaults(self, generator, sample_slis, sample_slos):
        """Test dashboard tags include default tags"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        tags = parsed["dashboard"]["tags"]
        assert "slo" in tags
        assert "sli" in tags
        assert "checkout" in tags
        assert "prod" in tags

    def test_custom_dashboard_tags(self, generator, sample_slis, sample_slos):
        """Test custom dashboard tags are used"""
        custom_tags = ["custom-tag", "test-tag"]
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
            tags=custom_tags,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["tags"] == custom_tags

    def test_templating_variables_include_service(self, generator, sample_slis, sample_slos):
        """Test templating includes service variable"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        variables = parsed["dashboard"]["templating"]["list"]
        service_var = next((v for v in variables if v["name"] == "service"), None)

        assert service_var is not None
        assert service_var["current"]["value"] == "checkout"

    def test_templating_variables_include_environment(self, generator, sample_slis, sample_slos):
        """Test templating includes environment variable"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        variables = parsed["dashboard"]["templating"]["list"]
        env_var = next((v for v in variables if v["name"] == "environment"), None)

        assert env_var is not None
        assert env_var["current"]["value"] == "prod"

    def test_templating_variables_include_time_range(self, generator, sample_slis, sample_slos):
        """Test templating includes time_range variable"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        variables = parsed["dashboard"]["templating"]["list"]
        time_var = next((v for v in variables if v["name"] == "time_range"), None)

        assert time_var is not None
        assert time_var["type"] == "interval"

    def test_time_range_defaults(self, generator, sample_slis, sample_slos):
        """Test default time range is set"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        time = parsed["dashboard"]["time"]
        assert "from" in time
        assert "to" in time
        assert time["to"] == "now"

    def test_refresh_intervals_configured(self, generator, sample_slis, sample_slos):
        """Test refresh intervals are configured"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        timepicker = parsed["dashboard"]["timepicker"]
        assert "refresh_intervals" in timepicker
        assert len(timepicker["refresh_intervals"]) > 0

    def test_schema_version_is_grafana_v7_plus(self, generator, sample_slis, sample_slos):
        """Test schema version is Grafana v7+ compatible"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        schema_version = parsed["dashboard"]["schemaVersion"]
        assert schema_version >= 30, "Schema version should be v7+ (>= 30)"

    def test_panels_have_unique_ids(self, generator, sample_slis, sample_slos):
        """Test all panels have unique IDs"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panel_ids = [p["id"] for p in parsed["dashboard"]["panels"]]
        assert len(panel_ids) == len(set(panel_ids)), "Panel IDs should be unique"

    def test_panels_have_grid_positions(self, generator, sample_slis, sample_slos):
        """Test panels have grid positions"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        for panel in parsed["dashboard"]["panels"]:
            assert "gridPos" in panel
            assert "x" in panel["gridPos"]
            assert "y" in panel["gridPos"]
            assert "w" in panel["gridPos"]
            assert "h" in panel["gridPos"]

    def test_panel_datasource_configured(self, generator, sample_slis, sample_slos):
        """Test panels have datasource configured"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        for panel in parsed["dashboard"]["panels"]:
            assert "datasource" in panel
            assert "uid" in panel["datasource"]

    def test_panel_units_match_sli_units(self, generator, sample_slis, sample_slos):
        """Test panel units match SLI units"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        # Find latency panel (should have 'ms' unit)
        for panel in parsed["dashboard"]["panels"]:
            if "latency" in panel.get("title", "").lower():
                unit = panel["fieldConfig"]["defaults"]["unit"]
                assert unit == "ms"
                break

    def test_annotations_configured(self, generator, sample_slis, sample_slos):
        """Test annotations are configured"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert "annotations" in parsed["dashboard"]
        assert "list" in parsed["dashboard"]["annotations"]

    def test_deployment_annotations_enabled(self, generator, sample_slis, sample_slos):
        """Test deployment annotations are enabled"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        annotations = parsed["dashboard"]["annotations"]["list"]
        deployment_annotation = next(
            (a for a in annotations if a["name"] == "Deployments"), None
        )

        assert deployment_annotation is not None
        assert deployment_annotation["enable"] is True

    def test_convenience_function_generate_grafana_dashboard(self, sample_slis, sample_slos):
        """Test convenience function wrapper"""
        result = generate_grafana_dashboard(
            service_name="test",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )

        parsed = json.loads(result)
        assert "dashboard" in parsed

    def test_empty_slis_list(self, generator):
        """Test with empty SLIs list"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=[],
            slos=[],
        )
        parsed = json.loads(result)

        assert len(parsed["dashboard"]["panels"]) == 0

    def test_sli_without_matching_slo(self, generator, sample_slis):
        """Test SLI without matching SLO (no threshold line)"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=[],  # No SLOs
        )
        parsed = json.loads(result)

        # Should still create panels for SLIs
        panels = parsed["dashboard"]["panels"]
        assert len(panels) > 0

    def test_multiple_slos_for_same_sli(self, generator, sample_slis):
        """Test multiple SLOs for same SLI (multiple threshold lines)"""
        slos = [
            {
                "sli_name": "checkout_latency_p95",
                "threshold_value": 200,
                "time_window": timedelta(hours=1),
                "variant": "conservative",
            },
            {
                "sli_name": "checkout_latency_p95",
                "threshold_value": 500,
                "time_window": timedelta(hours=1),
                "variant": "relaxed",
            },
        ]

        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=slos,
        )
        parsed = json.loads(result)

        # Find latency panel
        for panel in parsed["dashboard"]["panels"]:
            if "checkout_latency_p95" in panel.get("title", ""):
                targets = panel.get("targets", [])
                # Should have 3 targets: actual + 2 thresholds
                assert len(targets) >= 3
                break

    def test_panel_legend_configuration(self, generator, sample_slis, sample_slos):
        """Test panel legend is configured"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        for panel in parsed["dashboard"]["panels"]:
            if panel.get("type") == "timeseries":
                assert "options" in panel
                assert "legend" in panel["options"]

    def test_gauge_panel_thresholds(self, generator, sample_slis, sample_slos):
        """Test gauge panel has threshold configuration"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        gauge_panels = [p for p in parsed["dashboard"]["panels"] if p.get("type") == "gauge"]

        for gauge in gauge_panels:
            thresholds = gauge["fieldConfig"]["defaults"]["thresholds"]
            assert "mode" in thresholds
            assert "steps" in thresholds
            assert len(thresholds["steps"]) > 0

    def test_gauge_panel_unit_is_percent(self, generator, sample_slis, sample_slos):
        """Test error budget gauge uses percent unit"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        gauge_panels = [p for p in parsed["dashboard"]["panels"] if p.get("type") == "gauge"]

        for gauge in gauge_panels:
            unit = gauge["fieldConfig"]["defaults"]["unit"]
            assert unit == "percent"

    def test_dashboard_is_editable(self, generator, sample_slis, sample_slos):
        """Test dashboard is marked as editable"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["editable"] is True

    def test_graph_tooltip_shared_crosshair(self, generator, sample_slis, sample_slos):
        """Test dashboard uses shared crosshair tooltip"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["graphTooltip"] == 1

    def test_dashboard_timezone_browser(self, generator, sample_slis, sample_slos):
        """Test dashboard uses browser timezone"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        assert parsed["dashboard"]["timezone"] == "browser"

    def test_custom_datasource_uid(self):
        """Test custom datasource UID is used"""
        custom_uid = "my-prometheus-uid"
        generator = GrafanaDashboardGenerator(datasource_uid=custom_uid)

        result = generator.generate(
            service_name="test",
            environment="prod",
            slis=[{"name": "test", "metric_definition": "test", "unit": "short"}],
            slos=[],
        )
        parsed = json.loads(result)

        for panel in parsed["dashboard"]["panels"]:
            assert panel["datasource"]["uid"] == custom_uid

    def test_sli_with_no_unit_defaults_to_short(self, generator):
        """Test SLI without unit defaults to 'short'"""
        slis = [{"name": "test_sli", "metric_definition": "test_metric"}]

        result = generator.generate(
            service_name="test",
            environment="prod",
            slis=slis,
            slos=[],
        )
        parsed = json.loads(result)

        panel = parsed["dashboard"]["panels"][0]
        unit = panel["fieldConfig"]["defaults"]["unit"]
        assert unit == "short"

    def test_panel_id_counter_increments(self, generator, sample_slis, sample_slos):
        """Test panel ID counter increments correctly"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        panel_ids = [p["id"] for p in parsed["dashboard"]["panels"]]
        # IDs should start from 1 and increment
        assert min(panel_ids) == 1
        assert max(panel_ids) == len(panel_ids)

    def test_json_is_pretty_printed(self, generator, sample_slis, sample_slos):
        """Test JSON output is pretty-printed (indented)"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )

        # Should have newlines and indentation
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_target_ref_ids_are_unique(self, generator, sample_slis, sample_slos):
        """Test target refIds are unique within panel"""
        result = generator.generate(
            service_name="checkout",
            environment="prod",
            slis=sample_slis,
            slos=sample_slos,
        )
        parsed = json.loads(result)

        for panel in parsed["dashboard"]["panels"]:
            if "targets" in panel:
                ref_ids = [t["refId"] for t in panel["targets"]]
                assert len(ref_ids) == len(set(ref_ids)), "RefIds should be unique"
