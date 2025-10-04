"""
Example usage of artifact generators (for documentation purposes)

This demonstrates how to use the generators to create Prometheus rules,
Grafana dashboards, and runbooks from SLO/SLI definitions.
"""
from datetime import timedelta
from recording_rule_generator import generate_recording_rule
from alert_rule_generator import generate_alert_rule
from grafana_generator import generate_grafana_dashboard
from runbook_generator import generate_runbook
from validators.promql_validator import validate_promql, validate_rule_file
from validators.grafana_validator import validate_grafana_dashboard
from validators.runbook_validator import validate_runbook


def example_complete_slo_workflow():
    """
    Complete example: Generate all artifacts for a single SLO.
    """
    # SLO Definition
    service_name = "checkout"
    environment = "prod"
    sli_name = "checkout_latency_p95"
    metric_definition = (
        'histogram_quantile(0.95, '
        'sum(rate(http_request_duration_seconds_bucket{service="checkout"}[5m])) by (le))'
    )
    threshold_value = 0.2  # 200ms
    slo_id = "uuid-123-456-789"

    print("=" * 80)
    print("SLO Artifact Generation Example")
    print("=" * 80)

    # Step 1: Validate PromQL expression
    print("\n1. Validating PromQL expression...")
    promql_errors = validate_promql(metric_definition)
    if promql_errors:
        print(f"   ✗ PromQL validation failed: {promql_errors}")
    else:
        print("   ✓ PromQL expression is valid")

    # Step 2: Generate Recording Rule
    print("\n2. Generating Prometheus recording rule...")
    recording_rule = generate_recording_rule(
        sli_name=sli_name,
        metric_definition=metric_definition,
        service_name=service_name,
        environment=environment,
        evaluation_interval=timedelta(minutes=1)
    )
    print("   ✓ Recording rule generated")
    print(f"   Preview:\n{recording_rule[:200]}...")

    # Validate recording rule
    rule_errors = validate_rule_file(recording_rule)
    if rule_errors:
        print(f"   ✗ Rule validation failed: {rule_errors}")
    else:
        print("   ✓ Recording rule validated successfully")

    # Step 3: Generate Alert Rule
    print("\n3. Generating Prometheus alert rule...")
    alert_rule = generate_alert_rule(
        slo_id=slo_id,
        sli_name=sli_name,
        metric_definition=f"{service_name}:{sli_name}:recording",  # Use recording rule
        threshold_value=threshold_value,
        comparison_operator="gt",
        time_window=timedelta(hours=1),
        service_name=service_name,
        environment=environment,
        severity="critical",
        runbook_url=f"https://runbooks.example.com/{service_name}/{sli_name}"
    )
    print("   ✓ Alert rule generated")
    print(f"   Preview:\n{alert_rule[:200]}...")

    # Step 4: Generate Grafana Dashboard
    print("\n4. Generating Grafana dashboard...")
    dashboard = generate_grafana_dashboard(
        service_name=service_name,
        environment=environment,
        slis=[{
            "name": sli_name,
            "metric_definition": metric_definition,
            "unit": "s"
        }],
        slos=[{
            "sli_name": sli_name,
            "threshold_value": threshold_value,
            "time_window": timedelta(hours=1),
            "variant": "balanced"
        }]
    )
    print("   ✓ Grafana dashboard generated")
    print(f"   Preview: {len(dashboard)} characters")

    # Validate dashboard
    dashboard_errors = validate_grafana_dashboard(dashboard)
    if dashboard_errors:
        print(f"   ✗ Dashboard validation failed: {dashboard_errors}")
    else:
        print("   ✓ Dashboard validated successfully")

    # Step 5: Generate Runbook
    print("\n5. Generating operational runbook...")
    runbook = generate_runbook(
        slo_id=slo_id,
        sli_name=sli_name,
        service_name=service_name,
        environment=environment,
        severity="critical",
        threshold_value=threshold_value
    )
    print("   ✓ Runbook generated")
    print(f"   Preview:\n{runbook[:200]}...")

    # Validate runbook
    runbook_errors = validate_runbook(runbook)
    if runbook_errors:
        print(f"   ✗ Runbook validation failed: {runbook_errors}")
    else:
        print("   ✓ Runbook validated successfully")

    print("\n" + "=" * 80)
    print("All artifacts generated and validated successfully!")
    print("=" * 80)

    return {
        "recording_rule": recording_rule,
        "alert_rule": alert_rule,
        "dashboard": dashboard,
        "runbook": runbook
    }


if __name__ == "__main__":
    # Run example
    artifacts = example_complete_slo_workflow()

    # Save artifacts to files for inspection
    import os
    output_dir = "/tmp/slo-scout-artifacts"
    os.makedirs(output_dir, exist_ok=True)

    with open(f"{output_dir}/recording_rule.yaml", "w") as f:
        f.write(artifacts["recording_rule"])

    with open(f"{output_dir}/alert_rule.yaml", "w") as f:
        f.write(artifacts["alert_rule"])

    with open(f"{output_dir}/dashboard.json", "w") as f:
        f.write(artifacts["dashboard"])

    with open(f"{output_dir}/runbook.yaml", "w") as f:
        f.write(artifacts["runbook"])

    print(f"\nArtifacts saved to: {output_dir}")
