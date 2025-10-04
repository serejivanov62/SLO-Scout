# Performance Tests

Performance tests for SLO-Scout validating spec.md FR-025 performance goals:

- **Ingest throughput**: 100k logs/min (Enterprise tier)
- **Ingest lag**: 99% < 60s (p95 target)
- **Query latency**: 95% < 2s (p95 target)

## Prerequisites

### Infrastructure Running

```bash
# Verify all services are running
kubectl get pods -n slo-scout

# Required services:
# - Kafka (for event ingestion)
# - TimescaleDB (for data storage)
# - Milvus (for vector search)
# - Backend API (for queries)
```

### Port Forwarding

```bash
# API endpoint
kubectl port-forward -n slo-scout svc/slo-scout-api 8000:8000

# Kafka (for direct producer tests)
kubectl port-forward -n slo-scout svc/kafka 9092:9092

# Prometheus metrics
# (included in API endpoint at /metrics)
```

### Python Dependencies

```bash
cd backend
poetry install

# Additional performance test dependencies
poetry add pytest-benchmark locust kafka-python
```

## Running Tests

### Run All Performance Tests

```bash
# From backend directory
poetry run pytest tests/performance/ -v -m performance --tb=short

# With detailed output
poetry run pytest tests/performance/ -v -m performance -s
```

### Individual Tests

#### Ingest Throughput Test (T146)

Tests: 100k logs/min for 5 minutes, validates ingest lag < 60s

```bash
poetry run pytest tests/performance/test_ingest_throughput.py::test_ingest_throughput_100k_per_minute -v -s

# Expected output:
# - Events sent: ~500,000 (100k/min × 5 min)
# - p95 ingest lag: < 60s ✓
# - Processing rate: 1,667+ events/sec
```

#### Query Latency Test (T147)

Tests: 100 concurrent SLI queries, validates p95 < 2s

```bash
poetry run pytest tests/performance/test_query_latency.py::test_sli_query_latency_p95_under_2s -v -s

# Expected output:
# - Concurrent queries: 100
# - p95 latency: < 2000ms ✓
# - p50 latency: < 500ms (typical)
```

### Stress Testing

```bash
# Burst load test (2x normal throughput)
poetry run pytest tests/performance/test_ingest_throughput.py::test_ingest_throughput_burst_load -v -s

# High concurrency test (200 concurrent queries)
poetry run pytest tests/performance/test_query_latency.py::test_query_latency_under_stress -v -s
```

## Performance Baseline Metrics

### Ingest Performance (T146)

| Metric | Target | Typical |
|--------|--------|---------|
| Throughput | 100k logs/min | 100-120k logs/min |
| Ingest lag p50 | < 30s | 10-20s |
| Ingest lag p95 | < 60s | 30-45s |
| Ingest lag p99 | < 90s | 50-70s |

### Query Performance (T147)

| Metric | Target | Typical |
|--------|--------|---------|
| SLI query p50 | < 500ms | 200-400ms |
| SLI query p95 | < 2000ms | 800-1500ms |
| SLI query p99 | < 3000ms | 1500-2500ms |
| Journeys query p95 | < 2000ms | 500-1000ms |

### Vector Search Performance

| Metric | Target | Typical |
|--------|--------|---------|
| Vector search overhead | < 1000ms | 300-600ms |
| With evidence p95 | < 2000ms | 1000-1800ms |
| Without evidence p95 | < 1000ms | 400-800ms |

## Troubleshooting

### High Ingest Lag

**Symptom**: Ingest lag p95 > 60s

**Possible Causes**:
- Kafka consumer group lag building up
- Flink job backpressure
- TimescaleDB write contention
- Insufficient resources (CPU/memory)

**Investigation**:
```bash
# Check Kafka consumer lag
kubectl exec -n slo-scout kafka-0 -- kafka-consumer-groups.sh \
  --bootstrap-server localhost:9092 \
  --describe --group capsule-ingest-consumer

# Check Flink backpressure
kubectl port-forward -n slo-scout svc/flink-jobmanager 8081:8081
# Visit: http://localhost:8081 → Jobs → Backpressure

# Check metrics
curl http://localhost:8000/metrics | grep ingest_lag
```

### High Query Latency

**Symptom**: Query p95 > 2000ms

**Possible Causes**:
- Vector search slow (Milvus index issues)
- Database query inefficiency
- Connection pool exhaustion
- Network latency

**Investigation**:
```bash
# Check vector search metrics
curl http://localhost:8000/metrics | grep vector_query_latency

# Check DB connection pool
curl http://localhost:8000/metrics | grep db_pool

# Enable query logging
export LOG_LEVEL=DEBUG
# Check logs for slow queries
```

### Test Failures

**Kafka Connection Refused**:
```bash
# Verify port-forward is active
kubectl port-forward -n slo-scout svc/kafka 9092:9092

# Check Kafka is ready
kubectl get pod -n slo-scout -l app=kafka
```

**Metrics Endpoint Unavailable**:
```bash
# Verify API is running
kubectl get pod -n slo-scout -l app=slo-scout-api

# Check metrics endpoint
curl http://localhost:8000/metrics
```

**Out of Memory During Burst Test**:
```bash
# Increase Kafka producer buffer
# In test, set: buffer_memory=134217728  # 128MB

# Increase Python heap
export PYTHONMALLOC=malloc
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Nightly at 2 AM
  workflow_dispatch:

jobs:
  performance:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Setup Infrastructure
        run: |
          kind create cluster
          kubectl apply -f infrastructure/kubernetes/

      - name: Run Performance Tests
        run: |
          cd backend
          poetry install
          poetry run pytest tests/performance/ -v --tb=short

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: performance-results
          path: backend/htmlcov/
```

### Performance Budgets

Fail CI if performance degrades:

```python
# In pytest configuration
@pytest.fixture(autouse=True)
def performance_budget():
    """Enforce performance budgets per spec.md FR-025"""
    yield

    # Check metrics after test
    metrics = get_metrics()

    assert metrics['ingest_lag_p95'] < 60, "Ingest lag budget exceeded"
    assert metrics['query_latency_p95'] < 2000, "Query latency budget exceeded"
```

## Monitoring During Tests

### Real-time Metrics

```bash
# Watch ingest lag
watch -n 1 'curl -s http://localhost:8000/metrics | grep ingest_lag_seconds'

# Watch query latency
watch -n 1 'curl -s http://localhost:8000/metrics | grep vector_query_latency'
```

### Grafana Dashboards

```bash
# Port-forward Grafana
kubectl port-forward -n slo-scout svc/grafana 3000:3000

# Open dashboard
open http://localhost:3000/d/slo-scout-performance
```

### Prometheus Queries

```promql
# Ingest lag trend
rate(ingest_lag_seconds_sum[5m]) / rate(ingest_lag_seconds_count[5m])

# Query latency p95
histogram_quantile(0.95, rate(vector_query_latency_bucket[5m]))

# Throughput
rate(events_ingested_total[1m]) * 60  # events per minute
```

## Performance Tuning

### Ingest Optimization

```yaml
# kafka-topics.yaml
- name: raw-telemetry
  partitions: 10  # Increase for higher throughput
  replication-factor: 3
  config:
    compression.type: gzip
    min.insync.replicas: 2
```

### Query Optimization

```python
# Vector search tuning
milvus_collection.create_index(
    field_name="embedding",
    index_params={
        "index_type": "HNSW",
        "metric_type": "L2",
        "params": {
            "M": 16,        # Connections per layer (default: 16)
            "efConstruction": 200  # Build-time search quality
        }
    }
)

# Query-time tuning
search_params = {
    "metric_type": "L2",
    "params": {
        "ef": 64  # Lower = faster, higher = more accurate
    }
}
```

### Database Optimization

```sql
-- TimescaleDB compression
ALTER TABLE capsule SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'service_id',
  timescaledb.compress_orderby = 'timestamp DESC'
);

-- Add compression policy
SELECT add_compression_policy('capsule', INTERVAL '7 days');

-- Continuous aggregates for common queries
CREATE MATERIALIZED VIEW capsule_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', timestamp) AS bucket,
       service_id,
       count(*) as event_count
FROM capsule
GROUP BY bucket, service_id;
```

## Related Documentation

- [spec.md FR-025](/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/specs/001-ingest-spec-txt/spec.md) - Performance requirements
- [research.md](/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/specs/001-ingest-spec-txt/research.md) - Scaling tiers and benchmarks
- [Chaos Tests](/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/scripts/chaos-tests/README.md) - Resilience testing
