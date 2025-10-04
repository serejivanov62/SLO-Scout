-- V003: Create compression policies per research.md retention decisions

-- Compress capsule data after 7 days
-- Per FR-030: Raw telemetry 7 days, capsule summaries 90 days
ALTER TABLE capsule SET (
  timescaledb.compress,
  timescaledb.compress_orderby = 'time_bucket DESC',
  timescaledb.compress_segmentby = 'service_id'
);

SELECT add_compression_policy('capsule', INTERVAL '7 days');

-- Compress SLO data after 30 days
ALTER TABLE slo SET (
  timescaledb.compress,
  timescaledb.compress_orderby = 'created_at DESC',
  timescaledb.compress_segmentby = 'sli_id'
);

SELECT add_compression_policy('slo', INTERVAL '30 days');

-- Retention policies per FR-030
-- Drop capsule chunks older than 90 days
SELECT add_retention_policy('capsule', INTERVAL '90 days');

-- Drop SLO chunks older than 1 year
SELECT add_retention_policy('slo', INTERVAL '1 year');

-- Continuous aggregates for SLO metrics (optional optimization)
CREATE MATERIALIZED VIEW IF NOT EXISTS slo_breach_summary
WITH (timescaledb.continuous) AS
SELECT
  sli_id,
  time_bucket('1 day', created_at) AS bucket,
  COUNT(*) AS slo_count,
  AVG(error_budget_remaining) AS avg_budget_remaining
FROM slo
WHERE deployed_at IS NOT NULL
GROUP BY sli_id, bucket;

-- Refresh policy for continuous aggregate
SELECT add_continuous_aggregate_policy('slo_breach_summary',
  start_offset => INTERVAL '3 days',
  end_offset => INTERVAL '1 hour',
  schedule_interval => INTERVAL '1 hour');
