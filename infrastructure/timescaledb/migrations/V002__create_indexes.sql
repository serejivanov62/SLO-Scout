-- V002: Create performance indexes per data-model.md

-- Service lookups
CREATE INDEX IF NOT EXISTS idx_service_org_env ON service(organization_id, environment);
CREATE INDEX IF NOT EXISTS idx_service_status ON service(status) WHERE status = 'active';

-- Time-series queries on capsule
CREATE INDEX IF NOT EXISTS idx_capsule_time_service ON capsule(service_id, time_bucket DESC);
CREATE INDEX IF NOT EXISTS idx_capsule_fingerprint ON capsule(fingerprint_hash, service_id);
CREATE INDEX IF NOT EXISTS idx_capsule_redacted ON capsule(redaction_applied) WHERE redaction_applied = TRUE;

-- SLI/SLO hierarchy
CREATE INDEX IF NOT EXISTS idx_journey_service ON user_journey(service_id);
CREATE INDEX IF NOT EXISTS idx_journey_confidence ON user_journey(confidence_score) WHERE confidence_score >= 70;
CREATE INDEX IF NOT EXISTS idx_sli_journey ON sli(journey_id);
CREATE INDEX IF NOT EXISTS idx_sli_approved ON sli(approved_at) WHERE approved_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_slo_sli ON slo(sli_id);
CREATE INDEX IF NOT EXISTS idx_slo_deployed ON slo(deployed_at) WHERE deployed_at IS NOT NULL;

-- Artifact management
CREATE INDEX IF NOT EXISTS idx_artifact_slo ON artifact(slo_id, artifact_type);
CREATE INDEX IF NOT EXISTS idx_artifact_approval ON artifact(approval_status, deployment_status);

-- Evidence retrieval
CREATE INDEX IF NOT EXISTS idx_evidence_sli ON evidence_pointer(sli_id);
CREATE INDEX IF NOT EXISTS idx_evidence_capsule ON evidence_pointer(capsule_id);

-- Policy lookups
CREATE INDEX IF NOT EXISTS idx_policy_scope ON policy(scope, scope_id);

-- Instrumentation recommendations
CREATE INDEX IF NOT EXISTS idx_instrumentation_service ON instrumentation_recommendation(service_id);
CREATE INDEX IF NOT EXISTS idx_instrumentation_status ON instrumentation_recommendation(status) WHERE status = 'pending';
