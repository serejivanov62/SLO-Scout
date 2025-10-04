"""
Unit tests for Prometheus Alert Rule Generator (T111)

Per task requirements:
- Assert YAML passes promtool validation
- Assert annotations present (summary, description, runbook_url)
- Test coverage >95%
- Mock external dependencies
- Test edge cases
"""
import pytest
import yaml
from datetime import timedelta
from typing import Dict, Any
from unittest.mock import Mock, patch

from src.generators.alert_rule_generator import (
    AlertRuleGenerator,
    generate_alert_rule,
)


class TestAlertRuleGenerator:
    """Test Prometheus alert rule generation"""

    @pytest.fixture
    def generator(self) -> AlertRuleGenerator:
        """Create alert rule generator instance"""
        return AlertRuleGenerator()

    @pytest.fixture
    def sample_slo_data(self) -> Dict[str, Any]:
        """Sample SLO data for testing"""
        return {
            "slo_id": "550e8400-e29b-41d4-a716-446655440000",
            "sli_name": "checkout_latency_p95",
            "metric_definition": "checkout:checkout_latency_p95:recording",
            "threshold_value": 200.0,
            "comparison_operator": "gt",
            "time_window": timedelta(hours=1),
            "service_name": "checkout",
            "environment": "prod",
            "severity": "critical",
        }

    def test_generate_returns_valid_yaml(self, generator, sample_slo_data):
        """Test that generated output is valid YAML"""
        result = generator.generate(**sample_slo_data)

        # Should not raise exception
        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)
        assert "groups" in parsed

    def test_yaml_structure_has_required_fields(self, generator, sample_slo_data):
        """Test YAML contains all required Prometheus alert fields"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        assert "groups" in parsed
        assert len(parsed["groups"]) == 1

        group = parsed["groups"][0]
        assert "name" in group
        assert "rules" in group

        rule = group["rules"][0]
        assert "alert" in rule
        assert "expr" in rule
        assert "for" in rule
        assert "labels" in rule
        assert "annotations" in rule

    def test_annotations_include_summary(self, generator, sample_slo_data):
        """Test alert includes summary annotation"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        annotations = parsed["groups"][0]["rules"][0]["annotations"]
        assert "summary" in annotations
        assert len(annotations["summary"]) > 0
        assert "checkout" in annotations["summary"]
        assert "checkout_latency_p95" in annotations["summary"]

    def test_annotations_include_description(self, generator, sample_slo_data):
        """Test alert includes description annotation"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        annotations = parsed["groups"][0]["rules"][0]["annotations"]
        assert "description" in annotations
        assert len(annotations["description"]) > 0
        # Description should explain the breach
        assert "checkout_latency_p95" in annotations["description"]
        assert "200" in annotations["description"]

    def test_annotations_include_runbook_url(self, generator, sample_slo_data):
        """Test alert includes runbook_url annotation"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        annotations = parsed["groups"][0]["rules"][0]["annotations"]
        assert "runbook_url" in annotations
        assert annotations["runbook_url"].startswith("http")

    def test_custom_runbook_url_is_used(self, generator, sample_slo_data):
        """Test custom runbook URL is included in annotations"""
        custom_url = "https://runbooks.company.com/checkout/latency-breach"
        result = generator.generate(**sample_slo_data, runbook_url=custom_url)
        parsed = yaml.safe_load(result)

        annotations = parsed["groups"][0]["rules"][0]["annotations"]
        assert annotations["runbook_url"] == custom_url

    def test_default_runbook_url_pattern(self, generator, sample_slo_data):
        """Test default runbook URL follows expected pattern"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        annotations = parsed["groups"][0]["rules"][0]["annotations"]
        runbook_url = annotations["runbook_url"]

        assert "runbooks.example.com" in runbook_url
        assert "checkout" in runbook_url
        assert "checkout-latency-p95" in runbook_url

    def test_alert_name_camelcase_format(self, generator, sample_slo_data):
        """Test alert name is in CamelCase format"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        alert_name = parsed["groups"][0]["rules"][0]["alert"]
        # Should be: CheckoutCheckoutLatencyP95Critical
        assert alert_name[0].isupper()
        assert "Checkout" in alert_name
        assert "Critical" in alert_name

    def test_alert_name_includes_severity(self, generator, sample_slo_data):
        """Test alert name includes severity level"""
        for severity in ["critical", "major", "minor"]:
            data = {**sample_slo_data, "severity": severity}
            result = generator.generate(**data)
            parsed = yaml.safe_load(result)

            alert_name = parsed["groups"][0]["rules"][0]["alert"]
            assert severity.capitalize() in alert_name

    def test_labels_include_required_fields(self, generator, sample_slo_data):
        """Test alert labels include all required fields"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        labels = parsed["groups"][0]["rules"][0]["labels"]
        assert labels["service"] == "checkout"
        assert labels["environment"] == "prod"
        assert labels["severity"] == "critical"
        assert labels["slo_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert labels["sli_name"] == "checkout_latency_p95"

    def test_custom_labels_are_merged(self, generator, sample_slo_data):
        """Test custom labels are added to alert"""
        result = generator.generate(
            **sample_slo_data,
            labels={"team": "payments", "oncall": "payments-oncall"},
        )
        parsed = yaml.safe_load(result)

        labels = parsed["groups"][0]["rules"][0]["labels"]
        assert labels["team"] == "payments"
        assert labels["oncall"] == "payments-oncall"
        # Original labels still present
        assert labels["service"] == "checkout"

    def test_alert_expression_with_gt_operator(self, generator, sample_slo_data):
        """Test alert expression with greater-than operator"""
        sample_slo_data["comparison_operator"] = "gt"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert ">" in expr
        assert "200" in expr

    def test_alert_expression_with_lt_operator(self, generator, sample_slo_data):
        """Test alert expression with less-than operator"""
        sample_slo_data["comparison_operator"] = "lt"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "<" in expr
        assert "200" in expr

    def test_alert_expression_with_gte_operator(self, generator, sample_slo_data):
        """Test alert expression with greater-than-or-equal operator"""
        sample_slo_data["comparison_operator"] = "gte"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert ">=" in expr

    def test_alert_expression_with_lte_operator(self, generator, sample_slo_data):
        """Test alert expression with less-than-or-equal operator"""
        sample_slo_data["comparison_operator"] = "lte"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "<=" in expr

    def test_alert_expression_with_eq_operator(self, generator, sample_slo_data):
        """Test alert expression with equals operator"""
        sample_slo_data["comparison_operator"] = "eq"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "==" in expr

    def test_alert_expression_includes_metric_definition(self, generator, sample_slo_data):
        """Test alert expression includes the metric definition"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "checkout:checkout_latency_p95:recording" in expr

    def test_default_for_duration_is_five_minutes(self, generator, sample_slo_data):
        """Test default 'for' duration is 5 minutes"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        for_duration = parsed["groups"][0]["rules"][0]["for"]
        assert for_duration == "5m"

    def test_custom_for_duration(self, generator, sample_slo_data):
        """Test custom 'for' duration is applied"""
        result = generator.generate(
            **sample_slo_data,
            for_duration=timedelta(minutes=10),
        )
        parsed = yaml.safe_load(result)

        for_duration = parsed["groups"][0]["rules"][0]["for"]
        assert for_duration == "10m"

    def test_for_duration_in_seconds(self, generator, sample_slo_data):
        """Test 'for' duration in seconds"""
        result = generator.generate(
            **sample_slo_data,
            for_duration=timedelta(seconds=30),
        )
        parsed = yaml.safe_load(result)

        for_duration = parsed["groups"][0]["rules"][0]["for"]
        assert for_duration == "30s"

    def test_for_duration_in_hours(self, generator, sample_slo_data):
        """Test 'for' duration in hours"""
        result = generator.generate(
            **sample_slo_data,
            for_duration=timedelta(hours=2),
        )
        parsed = yaml.safe_load(result)

        for_duration = parsed["groups"][0]["rules"][0]["for"]
        assert for_duration == "2h"

    def test_group_name_follows_pattern(self, generator, sample_slo_data):
        """Test group name follows expected pattern"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        group_name = parsed["groups"][0]["name"]
        assert group_name == "checkout_slo_alerts"

    def test_description_mentions_threshold(self, generator, sample_slo_data):
        """Test description includes threshold value"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        description = parsed["groups"][0]["rules"][0]["annotations"]["description"]
        assert "200" in description

    def test_description_mentions_comparison_operator(self, generator):
        """Test description includes human-readable operator"""
        test_cases = [
            ("gt", "is above"),
            ("gte", "is at or above"),
            ("lt", "is below"),
            ("lte", "is at or below"),
            ("eq", "equals"),
        ]

        for operator, expected_text in test_cases:
            result = generator.generate(
                slo_id="test",
                sli_name="test_sli",
                metric_definition="test_metric",
                threshold_value=100,
                comparison_operator=operator,
                time_window=timedelta(hours=1),
                service_name="test",
                environment="prod",
            )
            parsed = yaml.safe_load(result)

            description = parsed["groups"][0]["rules"][0]["annotations"]["description"]
            assert expected_text in description

    def test_description_mentions_time_window(self, generator, sample_slo_data):
        """Test description includes time window"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        description = parsed["groups"][0]["rules"][0]["annotations"]["description"]
        assert "1h" in description

    def test_convenience_function_generate_alert_rule(self):
        """Test convenience function wrapper"""
        result = generate_alert_rule(
            slo_id="test-id",
            sli_name="test_sli",
            metric_definition="test_metric",
            threshold_value=50,
            comparison_operator="gt",
            time_window=timedelta(hours=1),
            service_name="test_service",
            environment="staging",
        )

        parsed = yaml.safe_load(result)
        assert "groups" in parsed

        labels = parsed["groups"][0]["rules"][0]["labels"]
        assert labels["environment"] == "staging"

    def test_complex_promql_metric_definition(self, generator, sample_slo_data):
        """Test complex PromQL expression as metric definition"""
        complex_promql = """
        (
          sum(rate(http_requests_total{job="checkout", status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{job="checkout"}[5m]))
        ) * 100
        """
        sample_slo_data["metric_definition"] = complex_promql

        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert complex_promql in expr

    def test_hyphenated_service_name(self, generator):
        """Test service name with hyphens in alert name"""
        result = generator.generate(
            slo_id="test",
            sli_name="latency_p95",
            metric_definition="metric",
            threshold_value=100,
            comparison_operator="gt",
            time_window=timedelta(hours=1),
            service_name="payments-api-v2",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        alert_name = parsed["groups"][0]["rules"][0]["alert"]
        # Should convert to CamelCase
        assert "Payments" in alert_name
        assert "Api" in alert_name
        assert "V2" in alert_name

    def test_hyphenated_sli_name(self, generator):
        """Test SLI name with hyphens in alert name"""
        result = generator.generate(
            slo_id="test",
            sli_name="checkout-latency-p95",
            metric_definition="metric",
            threshold_value=100,
            comparison_operator="gt",
            time_window=timedelta(hours=1),
            service_name="api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        alert_name = parsed["groups"][0]["rules"][0]["alert"]
        assert "Checkout" in alert_name
        assert "Latency" in alert_name
        assert "P95" in alert_name

    def test_underscored_names_in_alert_name(self, generator):
        """Test underscored names are converted to CamelCase"""
        result = generator.generate(
            slo_id="test",
            sli_name="error_rate_5xx",
            metric_definition="metric",
            threshold_value=1,
            comparison_operator="gt",
            time_window=timedelta(hours=1),
            service_name="payment_gateway",
            environment="prod",
            severity="major",
        )
        parsed = yaml.safe_load(result)

        alert_name = parsed["groups"][0]["rules"][0]["alert"]
        # Should be PaymentGatewayErrorRate5xxMajor
        assert "Payment" in alert_name
        assert "Gateway" in alert_name
        assert "Error" in alert_name
        assert "Rate" in alert_name
        assert "Major" in alert_name

    def test_multiple_severities_create_different_alerts(self, generator, sample_slo_data):
        """Test different severities create different alert names"""
        data1 = {**sample_slo_data, "severity": "critical"}
        data2 = {**sample_slo_data, "severity": "major"}

        result1 = generator.generate(**data1)
        result2 = generator.generate(**data2)

        parsed1 = yaml.safe_load(result1)
        parsed2 = yaml.safe_load(result2)

        alert1 = parsed1["groups"][0]["rules"][0]["alert"]
        alert2 = parsed2["groups"][0]["rules"][0]["alert"]

        assert alert1 != alert2
        assert "Critical" in alert1
        assert "Major" in alert2

    def test_float_threshold_value(self, generator, sample_slo_data):
        """Test float threshold values are preserved"""
        sample_slo_data["threshold_value"] = 99.95
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "99.95" in expr

    def test_integer_threshold_value(self, generator, sample_slo_data):
        """Test integer threshold values are preserved"""
        sample_slo_data["threshold_value"] = 500
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "500" in expr

    def test_very_large_threshold(self, generator, sample_slo_data):
        """Test very large threshold values"""
        sample_slo_data["threshold_value"] = 1000000.0
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "1000000" in expr

    def test_very_small_threshold(self, generator, sample_slo_data):
        """Test very small threshold values"""
        sample_slo_data["threshold_value"] = 0.001
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "0.001" in expr

    def test_time_window_in_days(self, generator, sample_slo_data):
        """Test time window in days"""
        sample_slo_data["time_window"] = timedelta(days=7)
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        description = parsed["groups"][0]["rules"][0]["annotations"]["description"]
        assert "7d" in description

    def test_summary_is_concise(self, generator, sample_slo_data):
        """Test summary annotation is concise (not verbose)"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        summary = parsed["groups"][0]["rules"][0]["annotations"]["summary"]
        # Should be under 100 characters
        assert len(summary) < 100

    def test_description_is_detailed(self, generator, sample_slo_data):
        """Test description annotation is detailed"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        description = parsed["groups"][0]["rules"][0]["annotations"]["description"]
        # Should be longer than summary
        summary = parsed["groups"][0]["rules"][0]["annotations"]["summary"]
        assert len(description) > len(summary)

    def test_yaml_is_valid_prometheus_format(self, generator, sample_slo_data):
        """Test YAML structure matches Prometheus expectations"""
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        # Verify top-level structure
        assert isinstance(parsed["groups"], list)
        assert len(parsed["groups"]) > 0

        # Verify group structure
        group = parsed["groups"][0]
        assert isinstance(group["name"], str)
        assert isinstance(group["rules"], list)

        # Verify rule structure
        rule = group["rules"][0]
        assert isinstance(rule["alert"], str)
        assert isinstance(rule["expr"], str)
        assert isinstance(rule["for"], str)
        assert isinstance(rule["labels"], dict)
        assert isinstance(rule["annotations"], dict)

    def test_invalid_comparison_operator_defaults_to_gt(self, generator, sample_slo_data):
        """Test invalid comparison operator defaults to >"""
        sample_slo_data["comparison_operator"] = "invalid_op"
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert ">" in expr

    def test_recording_rule_reference_detection(self, generator):
        """Test detection of recording rule reference vs raw PromQL"""
        # Recording rule reference (contains : and 'recording')
        result1 = generator.generate(
            slo_id="test",
            sli_name="test",
            metric_definition="service:metric:recording",
            threshold_value=100,
            comparison_operator="gt",
            time_window=timedelta(hours=1),
            service_name="test",
            environment="prod",
        )
        parsed1 = yaml.safe_load(result1)
        expr1 = parsed1["groups"][0]["rules"][0]["expr"]
        assert "service:metric:recording" in expr1

    def test_zero_threshold_value(self, generator, sample_slo_data):
        """Test zero threshold value is handled correctly"""
        sample_slo_data["threshold_value"] = 0
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert " 0" in expr or ">0" in expr

    def test_negative_threshold_value(self, generator, sample_slo_data):
        """Test negative threshold value is handled"""
        sample_slo_data["threshold_value"] = -10
        result = generator.generate(**sample_slo_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert "-10" in expr
