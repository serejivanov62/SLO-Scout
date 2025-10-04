-- SLO-Scout TimescaleDB Initialization
-- Create hypertables for time-series data per data-model.md

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create database user
CREATE USER sloscout WITH PASSWORD 'changeme';
GRANT ALL PRIVILEGES ON DATABASE sloscout TO sloscout;

-- Service entity
CREATE TABLE service (
    service_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    environment VARCHAR(20) NOT NULL CHECK (environment IN ('prod', 'staging', 'dev')),
    owner_team VARCHAR(255) NOT NULL,
    telemetry_endpoints JSONB NOT NULL,
    retention_policy_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
    organization_id UUID NOT NULL,
    UNIQUE (organization_id, name, environment)
);

CREATE INDEX idx_service_org_env ON service(organization_id, environment);
CREATE INDEX idx_service_status ON service(status) WHERE status = 'active';

-- UserJourney entity
CREATE TABLE user_journey (
    journey_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id UUID NOT NULL REFERENCES service(service_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    entry_point VARCHAR(500) NOT NULL,
    exit_point VARCHAR(500) NOT NULL,
    step_sequence JSONB NOT NULL,
    traffic_volume_per_day INTEGER NOT NULL,
    confidence_score NUMERIC(5,2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    sample_trace_ids TEXT[] NOT NULL,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_journey_service ON user_journey(service_id);
CREATE INDEX idx_journey_confidence ON user_journey(confidence_score) WHERE confidence_score >= 70;

-- SLI entity
CREATE TABLE sli (
    sli_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    journey_id UUID NOT NULL REFERENCES user_journey(journey_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    metric_type VARCHAR(50) NOT NULL CHECK (metric_type IN ('latency', 'availability', 'error_rate', 'custom')),
    metric_definition TEXT NOT NULL, -- PromQL
    measurement_window INTERVAL NOT NULL,
    data_sources JSONB NOT NULL,
    confidence_score NUMERIC(5,2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    evidence_pointers JSONB NOT NULL,
    current_value NUMERIC,
    unit VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ
);

CREATE INDEX idx_sli_journey ON sli(journey_id);
CREATE INDEX idx_sli_approved ON sli(approved_at) WHERE approved_at IS NOT NULL;

-- SLO entity (time-series)
CREATE TABLE slo (
    slo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sli_id UUID NOT NULL REFERENCES sli(sli_id) ON DELETE CASCADE,
    threshold_value NUMERIC NOT NULL,
    comparison_operator VARCHAR(10) NOT NULL CHECK (comparison_operator IN ('lt', 'lte', 'gt', 'gte', 'eq')),
    time_window INTERVAL NOT NULL,
    target_percentage NUMERIC(5,2) NOT NULL CHECK (target_percentage >= 0 AND target_percentage <= 100),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('critical', 'major', 'minor')),
    breach_policy VARCHAR(255),
    historical_breach_frequency NUMERIC,
    variant VARCHAR(20) NOT NULL CHECK (variant IN ('conservative', 'balanced', 'aggressive')),
    error_budget_remaining NUMERIC(5,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    deployed_at TIMESTAMPTZ
);

-- Convert to hypertable (partitioned by created_at)
SELECT create_hypertable('slo', 'created_at', if_not_exists => TRUE);

CREATE INDEX idx_slo_sli ON slo(sli_id);
CREATE INDEX idx_slo_deployed ON slo(deployed_at) WHERE deployed_at IS NOT NULL;

-- Capsule entity (time-series)
CREATE TABLE capsule (
    capsule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint_hash VARCHAR(64) NOT NULL, -- SHA256
    template TEXT NOT NULL,
    count BIGINT NOT NULL,
    severity_distribution JSONB NOT NULL,
    sample_array JSONB NOT NULL, -- Max 10 samples
    embedding_vector_id VARCHAR(255), -- Milvus ID
    service_id UUID NOT NULL REFERENCES service(service_id) ON DELETE CASCADE,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    time_bucket TIMESTAMPTZ NOT NULL, -- Aggregation window start
    redaction_applied BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (fingerprint_hash, service_id, time_bucket)
);

-- Convert to hypertable (partitioned by time_bucket)
SELECT create_hypertable('capsule', 'time_bucket', if_not_exists => TRUE);

CREATE INDEX idx_capsule_time_service ON capsule(service_id, time_bucket DESC);
CREATE INDEX idx_capsule_fingerprint ON capsule(fingerprint_hash, service_id);
CREATE INDEX idx_capsule_redacted ON capsule(redaction_applied) WHERE redaction_applied = TRUE;

-- Artifact entity
CREATE TABLE artifact (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slo_id UUID NOT NULL REFERENCES slo(slo_id) ON DELETE CASCADE,
    artifact_type VARCHAR(50) NOT NULL CHECK (artifact_type IN ('prometheus_recording', 'prometheus_alert', 'grafana_dashboard', 'runbook')),
    content TEXT NOT NULL,
    validation_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (validation_status IN ('pending', 'passed', 'failed')),
    validation_errors JSONB,
    approval_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (approval_status IN ('pending', 'approved', 'rejected')),
    approved_by VARCHAR(255),
    approved_at TIMESTAMPTZ,
    deployment_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (deployment_status IN ('pending', 'deployed', 'rollback')),
    deployment_pr_url VARCHAR(500),
    deployed_at TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_artifact_slo ON artifact(slo_id, artifact_type);
CREATE INDEX idx_artifact_approval ON artifact(approval_status, deployment_status);

-- Policy entity
CREATE TABLE policy (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    scope VARCHAR(20) NOT NULL CHECK (scope IN ('global', 'organization', 'service')),
    scope_id UUID, -- FK to organization or service
    invariants JSONB NOT NULL,
    allowed_actions JSONB NOT NULL,
    enforcement_mode VARCHAR(20) NOT NULL CHECK (enforcement_mode IN ('block', 'warn', 'audit')),
    audit_required BOOLEAN NOT NULL DEFAULT TRUE,
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_policy_scope ON policy(scope, scope_id);

-- EvidencePointer entity
CREATE TABLE evidence_pointer (
    evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sli_id UUID NOT NULL REFERENCES sli(sli_id) ON DELETE CASCADE,
    capsule_id UUID REFERENCES capsule(capsule_id) ON DELETE SET NULL,
    trace_id VARCHAR(255),
    log_sample TEXT,
    timestamp TIMESTAMPTZ NOT NULL,
    confidence_contribution NUMERIC(5,2) NOT NULL CHECK (confidence_contribution >= 0 AND confidence_contribution <= 100),
    redaction_status VARCHAR(20) NOT NULL CHECK (redaction_status IN ('redacted', 'safe', 'pending')),
    CONSTRAINT at_least_one_source CHECK (
        capsule_id IS NOT NULL OR trace_id IS NOT NULL OR log_sample IS NOT NULL
    )
);

CREATE INDEX idx_evidence_sli ON evidence_pointer(sli_id);
CREATE INDEX idx_evidence_capsule ON evidence_pointer(capsule_id);

-- InstrumentationRecommendation entity
CREATE TABLE instrumentation_recommendation (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id UUID NOT NULL REFERENCES service(service_id) ON DELETE CASCADE,
    recommendation_type VARCHAR(50) NOT NULL CHECK (recommendation_type IN ('enable_rum', 'add_tracing', 'fix_cardinality', 'add_request_id')),
    description TEXT NOT NULL,
    code_snippet TEXT,
    expected_confidence_uplift NUMERIC(5,2) NOT NULL CHECK (expected_confidence_uplift >= 0 AND expected_confidence_uplift <= 100),
    implementation_cost VARCHAR(20) NOT NULL CHECK (implementation_cost IN ('low', 'medium', 'high')),
    priority VARCHAR(20) NOT NULL CHECK (priority IN ('critical', 'important', 'nice_to_have')),
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'implemented')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX idx_instrumentation_service ON instrumentation_recommendation(service_id);
CREATE INDEX idx_instrumentation_status ON instrumentation_recommendation(status) WHERE status = 'pending';

-- Grant permissions
GRANT ALL ON ALL TABLES IN SCHEMA public TO sloscout;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO sloscout;
