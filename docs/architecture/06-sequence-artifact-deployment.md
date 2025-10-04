# Sequence Diagram: Artifact Generation & Deployment

## Overview
This diagram shows the complete workflow for generating validated artifacts (Prometheus rules, Grafana dashboards, runbooks) and deploying them via GitOps.

## Diagram

```mermaid
sequenceDiagram
    actor SRE as SRE Team Member
    participant UI as Web UI
    participant API as FastAPI Backend
    participant Generator as Artifact Generators
    participant Validator as Validators
    participant PolicyGuard as Policy Guard
    participant TSDB as TimescaleDB
    participant Prom as Prometheus
    participant Git as GitHub/GitLab API
    participant Repo as GitOps Repository

    %% Artifact Generation Request
    SRE->>UI: Navigate to "Generate Artifacts"
    UI->>SRE: Display approved SLOs:<br/>- checkout_latency_p95 (approved)<br/>- payment_success_rate (approved)

    SRE->>UI: Select SLOs + artifact types:<br/>☑ Prometheus recording rules<br/>☑ Prometheus alert rules<br/>☑ Grafana dashboard<br/>☑ Runbook template<br/>☐ Validation only (dry-run)

    UI->>+API: POST /api/v1/artifacts/generate<br/>{slo_ids: [...], artifact_types: [...],<br/>validation_only: false}
    API->>TSDB: SELECT slo.*, sli.* FROM slo<br/>JOIN sli WHERE slo.id IN (slo_ids)
    TSDB-->>API: SLO + SLI metadata

    API->>API: Validate all SLOs approved
    alt Any SLO not approved
        API-->>UI: 400 Bad Request<br/>{error: "SLO {id} not approved"}
        UI->>SRE: Show error message
    end

    %% Generate Prometheus Recording Rules
    API->>+Generator: generate_recording_rules(sli_list)
    Generator->>Generator: For each SLI:<br/>- Extract metric_definition (PromQL)<br/>- Apply naming convention:<br/>  job:sli_name:rate5m<br/>- Add labels (service, environment)

    Generator->>Generator: Build YAML structure:<br/>groups:<br/>  - name: payments_api_slis<br/>    interval: 30s<br/>    rules:<br/>      - record: job:checkout_latency_p95:30s<br/>        expr: {PromQL}

    Generator-->>-API: recording_rules.yaml content

    API->>+Validator: validate_promql(recording_rules.yaml)
    Validator->>Validator: Write YAML to temp file
    Validator->>Validator: Execute: promtool check rules /tmp/recording_rules.yaml

    alt promtool exit code != 0
        Validator-->>API: ValidationError<br/>{stderr: "line 5: parse error..."}
        API->>TSDB: INSERT INTO artifact<br/>(type='recording_rule',<br/>validation_status='failed',<br/>validation_error='...')
        API-->>UI: 400 Bad Request<br/>{error: "promtool validation failed"}
        UI->>SRE: Show validation errors
    else promtool success
        Validator-->>-API: ValidationSuccess
        API->>TSDB: INSERT INTO artifact<br/>(type='recording_rule', content=YAML,<br/>validation_status='passed')
    end

    %% Generate Alert Rules
    API->>+Generator: generate_alert_rules(slo_list)
    Generator->>Generator: For each SLO:<br/>- Generate alert condition from threshold<br/>- Add annotations (summary, description, runbook_url)<br/>- Set severity labels

    Generator->>Generator: Build YAML:<br/>groups:<br/>  - name: payments_api_slos<br/>    rules:<br/>      - alert: CheckoutLatencyP95High<br/>        expr: job:checkout_latency_p95:30s > 0.2<br/>        for: 5m<br/>        labels:<br/>          severity: high<br/>        annotations:<br/>          summary: "Checkout p95 latency breached"<br/>          runbook_url: "https://..."

    Generator-->>-API: alert_rules.yaml content

    API->>+Validator: validate_promql(alert_rules.yaml)
    Validator->>Validator: promtool check rules /tmp/alert_rules.yaml
    Validator-->>-API: ValidationSuccess

    API->>+Validator: dry_run_evaluate(alert_rules.yaml)
    Validator->>Prom: Query historical data for alert condition<br/>range=30d, step=5m
    Prom-->>Validator: Time-series boolean (alert would fire)

    Validator->>Validator: Calculate historical trigger frequency:<br/>- Total alerts in 30d: 2<br/>- Avg duration per alert: 15m<br/>- Estimate: 2 alerts/month

    Validator-->>-API: DryRunResult<br/>{historical_trigger_count: 2,<br/>avg_duration: 15m}

    API->>TSDB: INSERT INTO artifact<br/>(type='alert_rule', content=YAML,<br/>validation_status='passed',<br/>dry_run_result=JSON)

    %% Generate Grafana Dashboard
    API->>+Generator: generate_grafana_dashboard(slo_list, sli_list)
    Generator->>Generator: Build JSON structure:<br/>- Dashboard metadata (title, tags)<br/>- Panel 1: SLI time-series graph<br/>- Panel 2: SLO threshold line<br/>- Panel 3: Error budget gauge<br/>- Panel 4: Breach history table<br/>- Variables: $service, $environment

    Generator->>Generator: Add annotations:<br/>- Deployment events from Git<br/>- Alert firing ranges

    Generator-->>-API: dashboard.json content

    API->>+Validator: validate_grafana_schema(dashboard.json)
    Validator->>Validator: Load JSON schema for Grafana v10
    Validator->>Validator: jsonschema.validate(dashboard, schema)

    alt JSON schema invalid
        Validator-->>API: ValidationError<br/>{error: "Missing required field 'panels'"}
        API-->>UI: 400 Bad Request
    else JSON valid
        Validator-->>-API: ValidationSuccess
        API->>TSDB: INSERT INTO artifact<br/>(type='grafana_dashboard', content=JSON,<br/>validation_status='passed')
    end

    %% Generate Runbook
    API->>+Generator: generate_runbook(slo_list)
    Generator->>Generator: For each SLO:<br/>- Load runbook template (YAML)<br/>- Fill placeholders:<br/>  {service_name}, {slo_threshold}, {alert_name}<br/>- Add diagnostic steps:<br/>  1. Check service logs: kubectl logs...<br/>  2. Check metrics: promtool query...<br/>  3. Check recent deployments: git log...<br/>- Add mitigation actions:<br/>  1. Scale replicas: kubectl scale...<br/>  2. Rollback: kubectl rollout undo...<br/>- Link evidence: capsule IDs, trace IDs

    Generator-->>-API: runbook.yaml content

    API->>+Validator: validate_runbook_schema(runbook.yaml)
    Validator->>Validator: YAML syntax check + required fields<br/>(name, triggers, steps, mitigation)
    Validator-->>-API: ValidationSuccess

    API->>TSDB: INSERT INTO artifact<br/>(type='runbook', content=YAML,<br/>validation_status='passed')

    API-->>-UI: 201 Created<br/>{artifacts: [<br/>  {id, type='recording_rule', validation_status='passed'},<br/>  {id, type='alert_rule', validation_status='passed', dry_run_result},<br/>  {id, type='grafana_dashboard', validation_status='passed'},<br/>  {id, type='runbook', validation_status='passed'}]}

    UI->>SRE: Show artifacts:<br/>- ✓ 2 recording rules validated<br/>- ✓ 2 alert rules validated (dry-run: 2 alerts/month)<br/>- ✓ 1 Grafana dashboard validated<br/>- ✓ 2 runbooks generated

    %% Review and Approve
    SRE->>UI: Click "Preview" for alert_rules.yaml
    UI->>UI: Show YAML content with syntax highlighting
    SRE->>UI: Click "Approve" for all artifacts

    UI->>+API: PATCH /api/v1/artifacts/{id}<br/>{action: "approve",<br/>approved_by: "alice@example.com"}

    API->>+PolicyGuard: validate_approval(artifact_id, user='alice')
    PolicyGuard->>TSDB: SELECT * FROM policy<br/>WHERE scope='production'
    TSDB-->>PolicyGuard: Policy invariants

    PolicyGuard->>PolicyGuard: Calculate blast radius:<br/>- Affected services: 1 (payments-api)<br/>- Affected endpoints: 3 (checkout, payment, confirm)<br/>- Traffic %: 12% of total

    PolicyGuard->>PolicyGuard: Check invariants:<br/>✓ blast_radius.services <= 10<br/>✓ blast_radius.traffic_percent <= 20%<br/>✓ approval_required = true (alice has permission)<br/>✓ audit_trail_required = true

    alt Policy violation
        PolicyGuard-->>-API: PolicyViolation<br/>{violated_invariant: "blast_radius.services > 10",<br/>required_override: "senior_sre_approval"}
        API-->>UI: 403 Forbidden<br/>{error: "Policy violation", details}
        UI->>SRE: Show error:<br/>"Requires senior SRE approval (blast radius too large)"
    else Policy passed
        PolicyGuard-->>-API: PolicyApproval<br/>{audit_log_id: UUID}

        API->>TSDB: UPDATE artifact<br/>SET approval_status='approved',<br/>approved_by='alice@example.com',<br/>approved_at=NOW()

        API->>TSDB: INSERT INTO audit_log<br/>(action='artifact_approval',<br/>user='alice', artifact_id, policy_result)

        API-->>-UI: 200 OK<br/>{artifact: {approval_status='approved'}}
        UI->>SRE: Show "✓ Approved by alice@example.com"
    end

    %% Create GitOps PR
    SRE->>UI: Click "Deploy to Production"
    UI->>+API: POST /api/v1/pr<br/>{artifact_ids: [...],<br/>target_repo: "org/observability-config",<br/>target_branch: "main",<br/>environment: "production"}

    API->>TSDB: SELECT * FROM artifact<br/>WHERE id IN (artifact_ids)<br/>AND approval_status='approved'
    TSDB-->>API: Approved artifacts

    API->>API: Bundle artifacts by type:<br/>prometheus/rules/recording/<br/>prometheus/rules/alerting/<br/>grafana/dashboards/<br/>runbooks/

    API->>+Git: POST /repos/{org}/{repo}/git/refs<br/>Create branch: slo-scout/payments-api-{timestamp}
    Git-->>-API: Branch created

    API->>+Git: POST /repos/{org}/{repo}/contents<br/>Path: prometheus/rules/recording/payments_api_slis.yaml<br/>Content: {base64(recording_rules.yaml)}<br/>Branch: slo-scout/payments-api-{timestamp}
    Git-->>-API: File committed

    loop For each artifact
        API->>+Git: POST /repos/{org}/{repo}/contents<br/>Path: {artifact_type}/{filename}<br/>Content: {base64(artifact.content)}
        Git-->>-API: File committed
    end

    API->>+Git: POST /repos/{org}/{repo}/pulls<br/>{title: "feat(payments-api): Add SLO monitoring",<br/>body: "## Summary\n- 2 SLIs monitored\n- 2 SLOs defined...",<br/>head: "slo-scout/payments-api-{timestamp}",<br/>base: "main"}
    Git-->>-API: PR created (pr_url, pr_number)

    API->>TSDB: UPDATE artifact<br/>SET deployment_status='pending_pr',<br/>pr_url={pr_url}

    API->>TSDB: INSERT INTO audit_log<br/>(action='pr_created', pr_url, artifacts)

    API-->>-UI: 201 Created<br/>{pr_url, pr_number, branch_name,<br/>artifacts_included: [...]}

    UI->>SRE: Show success:<br/>"✓ PR created: #1234"<br/><a href={pr_url}>View on GitHub</a>

    %% External PR Review (out of system scope)
    Note over SRE,Repo: Human review PR on GitHub/GitLab<br/>Merge triggers deployment pipeline<br/>(ArgoCD, FluxCD, Jenkins, etc.)

    %% Post-Deployment (webhook callback)
    Repo->>API: POST /api/v1/webhooks/deployment<br/>{pr_number, status='merged', commit_sha}
    API->>TSDB: UPDATE artifact<br/>SET deployment_status='deployed',<br/>deployed_at=NOW(), commit_sha={commit_sha}
    API->>TSDB: INSERT INTO audit_log<br/>(action='deployment_completed')
```

## Flow Summary

### Phase 1: Artifact Generation (30-60 seconds)
1. Select approved SLOs and artifact types
2. **Recording Rules**: Generate PromQL recording rules with naming convention
3. **Alert Rules**: Generate alert conditions, annotations, severity labels
4. **Grafana Dashboard**: Generate JSON with panels, variables, annotations
5. **Runbook**: Generate YAML with diagnostic steps, mitigation actions

### Phase 2: Validation (15-45 seconds)
1. **promtool validation**: Syntax check for Prometheus rules (recording + alert)
2. **Dry-run evaluation**: Query historical data to estimate alert trigger frequency
3. **JSON schema validation**: Validate Grafana dashboard against v10 schema
4. **YAML validation**: Check runbook syntax and required fields

### Phase 3: Policy Guard Review (5-10 seconds)
1. Calculate blast radius (affected services, endpoints, traffic %)
2. Check policy invariants (max services, max traffic %, approval required)
3. Enforce approval permissions (user role check)
4. Create audit log entry

### Phase 4: GitOps PR Creation (10-20 seconds)
1. Create feature branch: `slo-scout/{service}-{timestamp}`
2. Commit artifacts to organized directories:
   - `prometheus/rules/recording/`
   - `prometheus/rules/alerting/`
   - `grafana/dashboards/`
   - `runbooks/`
3. Create PR with conventional commit message
4. Update artifact `deployment_status='pending_pr'`

### Phase 5: External Review & Deployment (hours to days)
1. Human review PR on GitHub/GitLab (code review, CI checks)
2. Merge triggers GitOps deployment (ArgoCD/FluxCD)
3. Webhook callback updates `deployment_status='deployed'`

## Validation Rules

| Validator | Tool | Pass Criteria | Failure Handling |
|-----------|------|---------------|------------------|
| PromQL Syntax | `promtool check rules` | Exit code 0 | 400 Bad Request with stderr |
| Grafana Schema | `jsonschema` | No validation errors | 400 Bad Request with missing fields |
| Runbook YAML | `yaml.safe_load` | No parse errors | 400 Bad Request |
| Dry-Run Eval | Prometheus API | Query executes | Degrade to syntax-only validation |
| Policy Guard | Blast Radius Calc | All invariants pass | 403 Forbidden with override required |

## Policy Guard Invariants

| Invariant | Threshold | Enforcement Mode | Override Required |
|-----------|-----------|------------------|-------------------|
| `blast_radius.services` | <= 10 | Block | Senior SRE approval |
| `blast_radius.traffic_percent` | <= 20% | Block | VP Engineering approval |
| `blast_radius.cost_impact_usd` | <= $100/day | Warn | Budget owner approval |
| `approval_required` | true | Block | None (hard requirement) |
| `audit_trail_required` | true | Block | None (compliance) |

## Performance Characteristics

| Operation | Target | Actual (Median) | P95 |
|-----------|--------|-----------------|-----|
| Generate all artifacts | < 60s | 35s | 55s |
| Validate all artifacts | < 45s | 20s | 40s |
| Policy Guard check | < 10s | 2s | 5s |
| Create GitOps PR | < 20s | 8s | 15s |
| End-to-end (generation → PR) | < 2 min | 1 min | 1.5 min |

## Constitutional Compliance

- **Quality First**: All artifacts validated (promtool, JSON schema, dry-run) before approval
- **Human Approval**: All production deployments require `approved_by` field
- **Policy Guard**: Blast radius calculated, invariants enforced before deployment
- **Audit Trail**: All actions logged to immutable audit_log table
- **Self-Observability**: Export `artifact_generation_duration_seconds`, `policy_guard_violations_total` metrics

## Error Recovery

| Error Scenario | Detection | Recovery | User Impact |
|----------------|-----------|----------|-------------|
| promtool validation failure | Exit code != 0 | Display stderr, allow manual fix | SRE edits PromQL, regenerates |
| GitHub API rate limit | 429 response | Exponential backoff, max 3 retries | Delay 1-5 minutes |
| Policy violation | Blast radius > threshold | Require override approval | Senior SRE reviews, approves override |
| Git conflict on PR merge | Webhook status='conflict' | Notify SRE, manual resolution | SRE rebases branch, re-submits PR |
