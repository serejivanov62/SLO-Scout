export interface Service {
  id: string;
  name: string;
  environment: 'development' | 'staging' | 'production';
  owner_team: string;
  telemetry_endpoints: Record<string, string>;
  created_at: string;
  updated_at: string;
  status: 'active' | 'inactive' | 'archived';
}

export interface UserJourney {
  id: string;
  service_id: string;
  name: string;
  entry_point: string;
  exit_point: string;
  step_sequence: Array<{
    order: number;
    span_name: string;
    service: string;
  }>;
  confidence_score: number;
  sample_trace_ids: string[];
  created_at: string;
}

export interface SLI {
  id: string;
  journey_id: string;
  name: string;
  metric_type: 'latency' | 'availability' | 'error_rate' | 'throughput' | 'saturation';
  metric_definition: string; // PromQL
  confidence_score: number;
  evidence_pointers: Array<{
    type: string;
    reference: string;
  }>;
  current_value: number | null;
  unit: string;
  approved_by: string | null;
  created_at: string;
}

export interface SLO {
  id: string;
  sli_id: string;
  threshold_value: number;
  comparison_operator: 'lt' | 'lte' | 'gt' | 'gte' | 'eq';
  time_window: string; // e.g., "30d", "7d"
  target_percentage: number;
  severity: 'critical' | 'high' | 'medium' | 'low';
  variant: 'proposal' | 'approved' | 'deployed' | 'retired';
  error_budget_remaining: number;
  created_at: string;
}

export interface Artifact {
  id: string;
  slo_id: string;
  artifact_type: 'prometheus_rule' | 'grafana_dashboard' | 'runbook' | 'alert_definition';
  content: string;
  validation_status: 'pending' | 'passed' | 'failed';
  approval_status: 'pending' | 'approved' | 'rejected';
  deployment_status: 'not_deployed' | 'deploying' | 'deployed' | 'failed';
  version: number;
  created_at: string;
}

export interface Capsule {
  id: string;
  fingerprint_hash: string;
  template: string;
  count: number;
  severity_distribution: Record<string, number>;
  sample_array: Array<Record<string, any>>;
  embedding_vector_id: string | null;
  service_id: string;
  redaction_applied: boolean;
  created_at: string;
}

export interface AnalysisJob {
  job_id: string;
  service_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress_percentage: number;
  created_at: string;
  completed_at: string | null;
  error_message: string | null;
}

export interface ConfidenceScore {
  overall: number;
  breakdown: {
    telemetry_coverage: number;
    pattern_strength: number;
    historical_data: number;
    manual_validation: number;
  };
}
