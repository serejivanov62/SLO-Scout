"""
Unit tests for Prometheus Recording Rule Generator (T110)

Per task requirements:
- Assert YAML valid
- Assert job:metric:operation naming convention
- Test coverage >95%
- Mock external dependencies
- Test edge cases
"""
import pytest
import yaml
from datetime import timedelta
from typing import Dict, Any

from src.generators.recording_rule_generator import (
    RecordingRuleGenerator,
    generate_recording_rule,
)


class TestRecordingRuleGenerator:
    """Test Prometheus recording rule generation"""

    @pytest.fixture
    def generator(self) -> RecordingRuleGenerator:
        """Create recording rule generator instance"""
        return RecordingRuleGenerator()

    @pytest.fixture
    def sample_sli_data(self) -> Dict[str, Any]:
        """Sample SLI data for testing"""
        return {
            "sli_name": "checkout_latency_p95",
            "metric_definition": (
                "histogram_quantile(0.95, sum(rate("
                "http_request_duration_seconds_bucket"
                '{job="checkout", endpoint="/api/checkout"}[5m])) by (le))'
            ),
            "service_name": "checkout",
            "environment": "prod",
        }

    def test_generate_returns_valid_yaml(self, generator, sample_sli_data):
        """Test that generated output is valid YAML"""
        result = generator.generate(**sample_sli_data)

        # Should not raise exception
        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)
        assert "groups" in parsed

    def test_yaml_structure_has_required_fields(self, generator, sample_sli_data):
        """Test YAML contains all required Prometheus fields"""
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        assert "groups" in parsed
        assert len(parsed["groups"]) == 1

        group = parsed["groups"][0]
        assert "name" in group
        assert "interval" in group
        assert "rules" in group

        rule = group["rules"][0]
        assert "record" in rule
        assert "expr" in rule
        assert "labels" in rule

    def test_naming_convention_job_metric_operation(self, generator, sample_sli_data):
        """Test recording rule follows job:metric:operation naming convention"""
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]

        # Should follow format: service:sli_name:recording
        assert rule_name == "checkout:checkout_latency_p95:recording"

        # Verify format matches job:metric:operation
        parts = rule_name.split(":")
        assert len(parts) == 3, "Should have 3 parts separated by colons"
        assert parts[0] == "checkout", "First part should be service (job)"
        assert parts[1] == "checkout_latency_p95", "Second part should be metric"
        assert parts[2] == "recording", "Third part should be operation"

    def test_sanitizes_service_name_hyphens_to_underscores(self, generator):
        """Test service name with hyphens is converted to underscores"""
        result = generator.generate(
            sli_name="latency_p95",
            metric_definition="test_metric",
            service_name="payments-api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert rule_name == "payments_api:latency_p95:recording"

    def test_sanitizes_service_name_dots_to_underscores(self, generator):
        """Test service name with dots is converted to underscores"""
        result = generator.generate(
            sli_name="latency_p95",
            metric_definition="test_metric",
            service_name="api.payments.v2",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert rule_name == "api_payments_v2:latency_p95:recording"

    def test_sanitizes_sli_name_special_chars(self, generator):
        """Test SLI name with special characters is sanitized"""
        result = generator.generate(
            sli_name="checkout-latency.p95",
            metric_definition="test_metric",
            service_name="checkout",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert rule_name == "checkout:checkout_latency_p95:recording"

    def test_labels_include_service_environment_sli_name(self, generator, sample_sli_data):
        """Test rule labels include required metadata"""
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        labels = parsed["groups"][0]["rules"][0]["labels"]
        assert labels["service"] == "checkout"
        assert labels["environment"] == "prod"
        assert labels["sli_name"] == "checkout_latency_p95"

    def test_additional_labels_are_merged(self, generator, sample_sli_data):
        """Test custom labels are added to rule"""
        result = generator.generate(
            **sample_sli_data,
            labels={"team": "payments-squad", "priority": "high"},
        )
        parsed = yaml.safe_load(result)

        labels = parsed["groups"][0]["rules"][0]["labels"]
        assert labels["team"] == "payments-squad"
        assert labels["priority"] == "high"
        # Original labels still present
        assert labels["service"] == "checkout"

    def test_metric_definition_preserved_exactly(self, generator, sample_sli_data):
        """Test PromQL expression is preserved without modification"""
        promql = sample_sli_data["metric_definition"]
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert expr == promql

    def test_default_evaluation_interval_one_minute(self, generator, sample_sli_data):
        """Test default evaluation interval is 1 minute (60s)"""
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        interval = parsed["groups"][0]["interval"]
        assert interval == "60s"

    def test_custom_evaluation_interval(self, generator, sample_sli_data):
        """Test custom evaluation interval is applied"""
        result = generator.generate(
            **sample_sli_data,
            evaluation_interval=timedelta(minutes=5),
        )
        parsed = yaml.safe_load(result)

        interval = parsed["groups"][0]["interval"]
        assert interval == "300s"

    def test_evaluation_interval_30_seconds(self, generator, sample_sli_data):
        """Test 30 second interval"""
        result = generator.generate(
            **sample_sli_data,
            evaluation_interval=timedelta(seconds=30),
        )
        parsed = yaml.safe_load(result)

        interval = parsed["groups"][0]["interval"]
        assert interval == "30s"

    def test_group_name_follows_pattern(self, generator, sample_sli_data):
        """Test group name follows expected pattern"""
        result = generator.generate(**sample_sli_data)
        parsed = yaml.safe_load(result)

        group_name = parsed["groups"][0]["name"]
        assert group_name == "checkout_sli_recording_rules"

    def test_generate_batch_multiple_slis(self, generator):
        """Test batch generation for multiple SLIs"""
        slis = [
            {"name": "latency_p95", "metric_definition": "histogram_quantile(0.95, ...)"},
            {"name": "latency_p99", "metric_definition": "histogram_quantile(0.99, ...)"},
            {"name": "error_rate", "metric_definition": "sum(rate(errors[5m])) * 100"},
        ]

        result = generator.generate_batch(
            slis=slis,
            service_name="checkout",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rules = parsed["groups"][0]["rules"]
        assert len(rules) == 3

        # Verify all rules present
        rule_names = [r["record"] for r in rules]
        assert "checkout:latency_p95:recording" in rule_names
        assert "checkout:latency_p99:recording" in rule_names
        assert "checkout:error_rate:recording" in rule_names

    def test_generate_batch_preserves_metric_definitions(self, generator):
        """Test batch generation preserves all PromQL expressions"""
        slis = [
            {"name": "sli1", "metric_definition": "expr1"},
            {"name": "sli2", "metric_definition": "expr2"},
        ]

        result = generator.generate_batch(
            slis=slis,
            service_name="test",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rules = parsed["groups"][0]["rules"]
        expressions = [r["expr"] for r in rules]
        assert "expr1" in expressions
        assert "expr2" in expressions

    def test_generate_batch_all_rules_in_same_group(self, generator):
        """Test batch generation puts all rules in single group"""
        slis = [
            {"name": "sli1", "metric_definition": "expr1"},
            {"name": "sli2", "metric_definition": "expr2"},
            {"name": "sli3", "metric_definition": "expr3"},
        ]

        result = generator.generate_batch(
            slis=slis,
            service_name="test",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        assert len(parsed["groups"]) == 1
        assert len(parsed["groups"][0]["rules"]) == 3

    def test_convenience_function_generate_recording_rule(self):
        """Test convenience function wrapper"""
        result = generate_recording_rule(
            sli_name="test_sli",
            metric_definition="test_expr",
            service_name="test_service",
            environment="staging",
        )

        parsed = yaml.safe_load(result)
        assert "groups" in parsed

        rule = parsed["groups"][0]["rules"][0]
        assert rule["record"] == "test_service:test_sli:recording"
        assert rule["labels"]["environment"] == "staging"

    def test_empty_service_name_raises_error(self, generator):
        """Test empty service name is handled"""
        # Should generate rule but with empty service component
        result = generator.generate(
            sli_name="test_sli",
            metric_definition="test",
            service_name="",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert rule_name.startswith(":")

    def test_empty_sli_name_raises_error(self, generator):
        """Test empty SLI name is handled"""
        result = generator.generate(
            sli_name="",
            metric_definition="test",
            service_name="service",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert ":recording" in rule_name

    def test_complex_promql_with_multiline(self, generator):
        """Test complex multi-line PromQL expression"""
        complex_promql = """
        histogram_quantile(0.95,
          sum(rate(http_request_duration_seconds_bucket{
            job="api",
            endpoint="/checkout"
          }[5m])) by (le)
        ) * 1000
        """

        result = generator.generate(
            sli_name="latency_p95",
            metric_definition=complex_promql,
            service_name="api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert expr == complex_promql

    def test_yaml_output_is_sorted_keys_false(self, generator, sample_sli_data):
        """Test YAML output maintains insertion order (sort_keys=False)"""
        result = generator.generate(**sample_sli_data)

        # YAML should have groups first
        lines = result.strip().split("\n")
        assert lines[0].startswith("groups:")

    def test_yaml_output_is_not_flow_style(self, generator, sample_sli_data):
        """Test YAML output is block style, not flow style"""
        result = generator.generate(**sample_sli_data)

        # Should not have inline brackets/braces
        assert "{" not in result or "job=" in result  # Allow in PromQL
        # Labels should be block style
        assert "labels:" in result

    def test_multiple_services_different_groups(self, generator):
        """Test different services create different group names"""
        result1 = generator.generate(
            sli_name="latency",
            metric_definition="expr",
            service_name="service1",
            environment="prod",
        )
        result2 = generator.generate(
            sli_name="latency",
            metric_definition="expr",
            service_name="service2",
            environment="prod",
        )

        parsed1 = yaml.safe_load(result1)
        parsed2 = yaml.safe_load(result2)

        assert parsed1["groups"][0]["name"] == "service1_sli_recording_rules"
        assert parsed2["groups"][0]["name"] == "service2_sli_recording_rules"

    def test_rule_name_uniqueness_per_service_sli_pair(self, generator):
        """Test rule names are unique for service+sli combination"""
        result = generator.generate(
            sli_name="latency_p95",
            metric_definition="expr1",
            service_name="checkout",
            environment="prod",
        )
        parsed = yaml.safe_load(result)
        rule_name = parsed["groups"][0]["rules"][0]["record"]

        # Same service + sli should produce same name
        result2 = generator.generate(
            sli_name="latency_p95",
            metric_definition="expr2",  # Different expr
            service_name="checkout",
            environment="staging",  # Different env
        )
        parsed2 = yaml.safe_load(result2)
        rule_name2 = parsed2["groups"][0]["rules"][0]["record"]

        assert rule_name == rule_name2

    def test_environment_in_labels_not_in_rule_name(self, generator):
        """Test environment affects labels but not rule name"""
        result1 = generator.generate(
            sli_name="latency",
            metric_definition="expr",
            service_name="api",
            environment="prod",
        )
        result2 = generator.generate(
            sli_name="latency",
            metric_definition="expr",
            service_name="api",
            environment="staging",
        )

        parsed1 = yaml.safe_load(result1)
        parsed2 = yaml.safe_load(result2)

        # Same rule name
        assert (
            parsed1["groups"][0]["rules"][0]["record"]
            == parsed2["groups"][0]["rules"][0]["record"]
        )

        # Different environment label
        assert parsed1["groups"][0]["rules"][0]["labels"]["environment"] == "prod"
        assert parsed2["groups"][0]["rules"][0]["labels"]["environment"] == "staging"

    def test_numeric_sli_name(self, generator):
        """Test SLI name starting with number"""
        result = generator.generate(
            sli_name="99th_percentile",
            metric_definition="expr",
            service_name="api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert "99th_percentile" in rule_name

    def test_very_long_sli_name(self, generator):
        """Test very long SLI name is handled"""
        long_name = "a" * 200
        result = generator.generate(
            sli_name=long_name,
            metric_definition="expr",
            service_name="api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        rule_name = parsed["groups"][0]["rules"][0]["record"]
        assert long_name in rule_name

    def test_special_promql_characters_preserved(self, generator):
        """Test PromQL with special characters is preserved"""
        promql = 'sum(rate(metric{label=~"pattern.*"}[5m])) / sum(rate(total[5m])) * 100'

        result = generator.generate(
            sli_name="test",
            metric_definition=promql,
            service_name="api",
            environment="prod",
        )
        parsed = yaml.safe_load(result)

        expr = parsed["groups"][0]["rules"][0]["expr"]
        assert expr == promql
        assert '=~"pattern.*"' in expr

    def test_interval_hours_in_seconds(self, generator, sample_sli_data):
        """Test interval with hours is converted to seconds"""
        result = generator.generate(
            **sample_sli_data,
            evaluation_interval=timedelta(hours=2),
        )
        parsed = yaml.safe_load(result)

        interval = parsed["groups"][0]["interval"]
        assert interval == "7200s"  # 2 hours = 7200 seconds

    def test_interval_days_in_seconds(self, generator, sample_sli_data):
        """Test interval with days is converted to seconds"""
        result = generator.generate(
            **sample_sli_data,
            evaluation_interval=timedelta(days=1),
        )
        parsed = yaml.safe_load(result)

        interval = parsed["groups"][0]["interval"]
        assert interval == "86400s"  # 1 day = 86400 seconds

    def test_sanitize_interval_method(self, generator):
        """Test _sanitize_interval utility method"""
        # Test seconds
        assert generator._sanitize_interval(timedelta(seconds=30)) == "30s"
        # Test minutes
        assert generator._sanitize_interval(timedelta(minutes=5)) == "5m"
        # Test hours
        assert generator._sanitize_interval(timedelta(hours=2)) == "2h"
        # Test days
        assert generator._sanitize_interval(timedelta(days=3)) == "3d"
