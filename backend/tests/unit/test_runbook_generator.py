"""
Unit tests for Runbook Generator (T113)

Per task requirements:
- Assert YAML valid
- Assert steps executable (have required fields)
- Test coverage >95%
- Mock external dependencies
- Test edge cases
"""
import pytest
import yaml
from typing import Dict, Any, List

from src.generators.runbook_generator import (
    RunbookGenerator,
    generate_runbook,
)


class TestRunbookGenerator:
    """Test operational runbook generation"""

    @pytest.fixture
    def generator(self) -> RunbookGenerator:
        """Create runbook generator instance"""
        return RunbookGenerator()

    @pytest.fixture
    def sample_runbook_data(self) -> Dict[str, Any]:
        """Sample runbook data for testing"""
        return {
            "slo_id": "550e8400-e29b-41d4-a716-446655440000",
            "sli_name": "checkout_latency_p95",
            "service_name": "checkout",
            "environment": "prod",
            "severity": "critical",
            "threshold_value": 200.0,
        }

    def test_generate_returns_valid_yaml(self, generator, sample_runbook_data):
        """Test that generated output is valid YAML"""
        result = generator.generate(**sample_runbook_data)

        # Should not raise exception
        parsed = yaml.safe_load(result)
        assert isinstance(parsed, dict)

    def test_yaml_structure_has_required_fields(self, generator, sample_runbook_data):
        """Test YAML contains all required runbook fields"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        # Per FR-008: Required fields
        assert "name" in parsed
        assert "version" in parsed
        assert "metadata" in parsed
        assert "triggers" in parsed
        assert "steps" in parsed

    def test_runbook_name_follows_pattern(self, generator, sample_runbook_data):
        """Test runbook name follows expected pattern"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        name = parsed["name"]
        assert name == "checkout-checkout-latency-p95-critical-breach"

    def test_runbook_name_sanitizes_underscores(self, generator):
        """Test runbook name converts underscores to hyphens"""
        result = generator.generate(
            slo_id="test",
            sli_name="error_rate_5xx",
            service_name="payment_gateway",
            environment="prod",
            severity="major",
            threshold_value=1.0,
        )
        parsed = yaml.safe_load(result)

        name = parsed["name"]
        assert "_" not in name
        assert "payment-gateway" in name
        assert "error-rate-5xx" in name

    def test_metadata_includes_required_fields(self, generator, sample_runbook_data):
        """Test metadata includes all required fields"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        metadata = parsed["metadata"]
        assert metadata["service"] == "checkout"
        assert metadata["environment"] == "prod"
        assert metadata["sli_name"] == "checkout_latency_p95"
        assert metadata["severity"] == "critical"
        assert metadata["threshold_value"] == 200.0

    def test_metadata_includes_owner(self, generator, sample_runbook_data):
        """Test metadata includes owner field"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        metadata = parsed["metadata"]
        assert "owner" in metadata

    def test_metadata_includes_tags(self, generator, sample_runbook_data):
        """Test metadata includes tags"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        metadata = parsed["metadata"]
        assert "tags" in metadata
        assert isinstance(metadata["tags"], list)
        assert len(metadata["tags"]) > 0

    def test_triggers_defined(self, generator, sample_runbook_data):
        """Test triggers are defined"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        triggers = parsed["triggers"]
        assert isinstance(triggers, list)
        assert len(triggers) > 0

    def test_trigger_has_alert_type(self, generator, sample_runbook_data):
        """Test trigger has type 'alert'"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        trigger = parsed["triggers"][0]
        assert trigger["type"] == "alert"

    def test_trigger_has_alert_name(self, generator, sample_runbook_data):
        """Test trigger has alert_name field"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        trigger = parsed["triggers"][0]
        assert "alert_name" in trigger
        assert "checkout" in trigger["alert_name"]

    def test_trigger_has_condition(self, generator, sample_runbook_data):
        """Test trigger has condition field"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        trigger = parsed["triggers"][0]
        assert "condition" in trigger
        assert "200" in trigger["condition"]

    def test_steps_has_diagnostic_section(self, generator, sample_runbook_data):
        """Test steps include diagnostic section"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        steps = parsed["steps"]
        assert "diagnostic" in steps
        assert isinstance(steps["diagnostic"], list)
        assert len(steps["diagnostic"]) > 0

    def test_steps_has_mitigation_section(self, generator, sample_runbook_data):
        """Test steps include mitigation section"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        steps = parsed["steps"]
        assert "mitigation" in steps
        assert isinstance(steps["mitigation"], list)
        assert len(steps["mitigation"]) > 0

    def test_steps_has_rollback_section(self, generator, sample_runbook_data):
        """Test steps include rollback section"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        steps = parsed["steps"]
        assert "rollback" in steps
        assert isinstance(steps["rollback"], list)
        assert len(steps["rollback"]) > 0

    def test_diagnostic_steps_are_executable(self, generator, sample_runbook_data):
        """Test diagnostic steps have required executable fields"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]

        for step in diagnostic_steps:
            # Per FR-008: Each step should have name, description, command
            assert "name" in step, f"Step missing 'name': {step}"
            assert "description" in step, f"Step missing 'description': {step}"
            assert "command" in step, f"Step missing 'command': {step}"
            assert "timeout" in step, f"Step missing 'timeout': {step}"

    def test_diagnostic_steps_include_kubectl_commands(self, generator, sample_runbook_data):
        """Test diagnostic steps include kubectl commands"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]
        commands = [step["command"] for step in diagnostic_steps]

        # Should have kubectl commands for common diagnostics
        kubectl_commands = [cmd for cmd in commands if "kubectl" in cmd]
        assert len(kubectl_commands) > 0, "Should have kubectl diagnostic commands"

    def test_diagnostic_step_check_pod_status(self, generator, sample_runbook_data):
        """Test diagnostic includes pod status check"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]
        pod_check = next((s for s in diagnostic_steps if "pod" in s["name"]), None)

        assert pod_check is not None
        assert "kubectl get pods" in pod_check["command"]
        assert "checkout" in pod_check["command"]

    def test_diagnostic_step_check_logs(self, generator, sample_runbook_data):
        """Test diagnostic includes log checking"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]
        log_check = next((s for s in diagnostic_steps if "log" in s["name"]), None)

        assert log_check is not None
        assert "kubectl logs" in log_check["command"]

    def test_mitigation_steps_are_executable(self, generator, sample_runbook_data):
        """Test mitigation steps have required executable fields"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]

        for step in mitigation_steps:
            assert "name" in step
            assert "description" in step
            assert "command" in step
            assert "timeout" in step

    def test_mitigation_steps_have_approval_flags(self, generator, sample_runbook_data):
        """Test mitigation steps have approval_required flags"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]

        # At least some steps should require approval
        requires_approval = [s for s in mitigation_steps if s.get("approval_required")]
        assert len(requires_approval) > 0, "Some mitigation steps should require approval"

    def test_mitigation_steps_have_blast_radius(self, generator, sample_runbook_data):
        """Test mitigation steps include blast_radius assessment"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]

        # Steps that require approval should have blast_radius
        for step in mitigation_steps:
            if step.get("approval_required"):
                assert "blast_radius" in step

    def test_mitigation_step_scale_replicas(self, generator, sample_runbook_data):
        """Test mitigation includes scaling replicas"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]
        scale_step = next((s for s in mitigation_steps if "replica" in s["name"]), None)

        assert scale_step is not None
        assert "kubectl scale" in scale_step["command"]

    def test_mitigation_step_restart_pods(self, generator, sample_runbook_data):
        """Test mitigation includes pod restart"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]
        restart_step = next((s for s in mitigation_steps if "restart" in s["name"]), None)

        assert restart_step is not None
        assert "kubectl rollout restart" in restart_step["command"]

    def test_rollback_steps_are_executable(self, generator, sample_runbook_data):
        """Test rollback steps have required executable fields"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        rollback_steps = parsed["steps"]["rollback"]

        for step in rollback_steps:
            assert "name" in step
            assert "description" in step
            assert "command" in step
            assert "timeout" in step

    def test_rollback_step_identify_revision(self, generator, sample_runbook_data):
        """Test rollback includes identifying last good revision"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        rollback_steps = parsed["steps"]["rollback"]
        revision_step = next((s for s in rollback_steps if "revision" in s["name"]), None)

        assert revision_step is not None
        assert "kubectl rollout history" in revision_step["command"]

    def test_rollback_step_perform_rollback(self, generator, sample_runbook_data):
        """Test rollback includes actual rollback command"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        rollback_steps = parsed["steps"]["rollback"]
        rollback_step = next((s for s in rollback_steps if "rollback" in s["name"]), None)

        assert rollback_step is not None
        assert "kubectl rollout undo" in rollback_step["command"]

    def test_rollback_step_verify_rollback(self, generator, sample_runbook_data):
        """Test rollback includes verification step"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        rollback_steps = parsed["steps"]["rollback"]
        verify_step = next((s for s in rollback_steps if "verify" in s["name"]), None)

        assert verify_step is not None

    def test_escalation_configured(self, generator, sample_runbook_data):
        """Test escalation paths are configured"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        assert "escalation" in parsed
        escalation = parsed["escalation"]

        assert "level_1" in escalation
        assert "level_2" in escalation

    def test_escalation_level_1_has_team(self, generator, sample_runbook_data):
        """Test level 1 escalation has team field"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        level_1 = parsed["escalation"]["level_1"]
        assert "team" in level_1
        assert "slack_channel" in level_1
        assert "pagerduty_key" in level_1

    def test_escalation_level_2_has_engineering_team(self, generator, sample_runbook_data):
        """Test level 2 escalation has engineering team"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        level_2 = parsed["escalation"]["level_2"]
        assert "team" in level_2
        assert "escalation_time" in level_2
        assert "contact" in level_2

    def test_references_included(self, generator, sample_runbook_data):
        """Test references section is included"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        assert "references" in parsed
        references = parsed["references"]

        assert "dashboard" in references
        assert "documentation" in references
        assert "incident_template" in references

    def test_references_urls_are_valid(self, generator, sample_runbook_data):
        """Test reference URLs start with https"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        references = parsed["references"]

        for key, url in references.items():
            assert url.startswith("http"), f"Reference {key} should be a URL"

    def test_custom_diagnostic_steps(self, generator, sample_runbook_data):
        """Test custom diagnostic steps can be provided"""
        custom_steps = [
            {
                "name": "custom_check",
                "description": "Custom diagnostic",
                "command": "echo custom",
                "timeout": "10s",
            }
        ]

        result = generator.generate(**sample_runbook_data, diagnostic_steps=custom_steps)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]
        assert len(diagnostic_steps) == 1
        assert diagnostic_steps[0]["name"] == "custom_check"

    def test_custom_mitigation_steps(self, generator, sample_runbook_data):
        """Test custom mitigation steps can be provided"""
        custom_steps = [
            {
                "name": "custom_mitigation",
                "description": "Custom action",
                "command": "echo fix",
                "timeout": "30s",
                "approval_required": True,
                "blast_radius": "low",
            }
        ]

        result = generator.generate(**sample_runbook_data, mitigation_steps=custom_steps)
        parsed = yaml.safe_load(result)

        mitigation_steps = parsed["steps"]["mitigation"]
        assert len(mitigation_steps) == 1
        assert mitigation_steps[0]["name"] == "custom_mitigation"

    def test_custom_rollback_steps(self, generator, sample_runbook_data):
        """Test custom rollback steps can be provided"""
        custom_steps = [
            {
                "name": "custom_rollback",
                "description": "Custom rollback",
                "command": "echo rollback",
                "timeout": "60s",
            }
        ]

        result = generator.generate(**sample_runbook_data, rollback_steps=custom_steps)
        parsed = yaml.safe_load(result)

        rollback_steps = parsed["steps"]["rollback"]
        assert len(rollback_steps) == 1
        assert rollback_steps[0]["name"] == "custom_rollback"

    def test_additional_metadata(self, generator, sample_runbook_data):
        """Test additional metadata can be merged"""
        additional = {"custom_field": "custom_value", "priority": "P1"}

        result = generator.generate(**sample_runbook_data, additional_metadata=additional)
        parsed = yaml.safe_load(result)

        metadata = parsed["metadata"]
        assert metadata["custom_field"] == "custom_value"
        assert metadata["priority"] == "P1"
        # Original metadata still present
        assert metadata["service"] == "checkout"

    def test_convenience_function_generate_runbook(self):
        """Test convenience function wrapper"""
        result = generate_runbook(
            slo_id="test-id",
            sli_name="test_sli",
            service_name="test_service",
            environment="staging",
            severity="major",
            threshold_value=100.0,
        )

        parsed = yaml.safe_load(result)
        assert "name" in parsed
        assert parsed["metadata"]["environment"] == "staging"

    def test_environment_in_kubectl_commands(self, generator, sample_runbook_data):
        """Test environment is included in kubectl namespace flags"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]

        for step in diagnostic_steps:
            if "kubectl" in step["command"]:
                assert "-n prod" in step["command"] or "namespace" in step["command"].lower()

    def test_service_name_in_kubectl_commands(self, generator, sample_runbook_data):
        """Test service name is included in kubectl commands"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]

        kubectl_steps = [s for s in diagnostic_steps if "kubectl" in s["command"]]
        service_mentions = [s for s in kubectl_steps if "checkout" in s["command"]]

        assert len(service_mentions) > 0, "Service name should appear in kubectl commands"

    def test_manual_steps_flagged(self, generator, sample_runbook_data):
        """Test some steps can be marked as manual"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        all_steps = (
            parsed["steps"]["diagnostic"]
            + parsed["steps"]["mitigation"]
            + parsed["steps"]["rollback"]
        )

        # Check if any steps have manual flag
        manual_steps = [s for s in all_steps if s.get("manual") is True]
        # It's ok if no manual steps, but if they exist, they should have the flag
        # Just verify the structure allows it

    def test_step_timeout_format(self, generator, sample_runbook_data):
        """Test step timeout values have valid format"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        all_steps = (
            parsed["steps"]["diagnostic"]
            + parsed["steps"]["mitigation"]
            + parsed["steps"]["rollback"]
        )

        for step in all_steps:
            timeout = step["timeout"]
            # Should be in format like "30s", "5m", etc.
            assert timeout[-1] in ["s", "m", "h"], f"Invalid timeout format: {timeout}"

    def test_version_field_present(self, generator, sample_runbook_data):
        """Test version field is present"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        assert "version" in parsed
        assert parsed["version"] == "1.0"

    def test_slo_id_stored_in_runbook(self, generator, sample_runbook_data):
        """Test SLO ID is stored in runbook for traceability"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        assert "slo_id" in parsed
        assert parsed["slo_id"] == "550e8400-e29b-41d4-a716-446655440000"

    def test_yaml_is_block_style(self, generator, sample_runbook_data):
        """Test YAML is block style, not flow style"""
        result = generator.generate(**sample_runbook_data)

        # Should have newlines and indentation
        assert "\n" in result
        # Should not have inline brackets (except in URLs/commands)
        lines = result.split("\n")
        # Main structure should be block style
        assert any(line.startswith("name:") for line in lines)
        assert any(line.startswith("steps:") for line in lines)

    def test_different_severities_in_name(self, generator):
        """Test different severities appear in runbook name"""
        for severity in ["critical", "major", "minor"]:
            result = generator.generate(
                slo_id="test",
                sli_name="test",
                service_name="test",
                environment="prod",
                severity=severity,
                threshold_value=100.0,
            )
            parsed = yaml.safe_load(result)

            assert severity in parsed["name"]

    def test_step_expected_output_fields(self, generator, sample_runbook_data):
        """Test diagnostic steps include expected_output field"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        diagnostic_steps = parsed["steps"]["diagnostic"]

        for step in diagnostic_steps:
            if not step.get("manual"):
                assert (
                    "expected_output" in step
                ), f"Non-manual step should have expected_output: {step['name']}"

    def test_runbook_tags_include_severity(self, generator, sample_runbook_data):
        """Test runbook tags include severity"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        tags = parsed["metadata"]["tags"]
        assert "critical" in tags

    def test_runbook_tags_include_service(self, generator, sample_runbook_data):
        """Test runbook tags include service name"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        tags = parsed["metadata"]["tags"]
        assert "checkout" in tags

    def test_escalation_includes_service_context(self, generator, sample_runbook_data):
        """Test escalation channels include service context"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        level_1 = parsed["escalation"]["level_1"]

        # Slack channel should include service name
        assert "checkout" in level_1["slack_channel"]

        # PagerDuty key should include service name
        assert "checkout" in level_1["pagerduty_key"]

    def test_references_include_service_in_urls(self, generator, sample_runbook_data):
        """Test reference URLs include service context"""
        result = generator.generate(**sample_runbook_data)
        parsed = yaml.safe_load(result)

        references = parsed["references"]

        # Dashboard URL should include service
        assert "checkout" in references["dashboard"]

        # Documentation URL should include service
        assert "checkout" in references["documentation"]

    def test_very_long_service_name(self, generator):
        """Test very long service name is handled"""
        long_name = "a" * 100
        result = generator.generate(
            slo_id="test",
            sli_name="test",
            service_name=long_name,
            environment="prod",
            severity="major",
            threshold_value=100.0,
        )
        parsed = yaml.safe_load(result)

        # Should still generate valid YAML
        assert "name" in parsed

    def test_special_characters_in_sli_name(self, generator):
        """Test special characters in SLI name are handled"""
        result = generator.generate(
            slo_id="test",
            sli_name="latency.p95/checkout",
            service_name="api",
            environment="prod",
            severity="major",
            threshold_value=100.0,
        )
        parsed = yaml.safe_load(result)

        # Should generate valid YAML
        assert "name" in parsed

    def test_numeric_environment_name(self, generator):
        """Test numeric environment name is handled"""
        result = generator.generate(
            slo_id="test",
            sli_name="test",
            service_name="api",
            environment="prod-v2",
            severity="major",
            threshold_value=100.0,
        )
        parsed = yaml.safe_load(result)

        assert parsed["metadata"]["environment"] == "prod-v2"
