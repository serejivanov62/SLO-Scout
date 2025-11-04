# SLO-Scout End-to-End Flow Documentation

This document describes the complete data flow through the SLO-Scout platform, from telemetry ingestion to SLO artifact generation.

---

## 🔄 Complete Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                    SLO-Scout Data Flow                            │
└──────────────────────────────────────────────────────────────────┘

 1. TELEMETRY SOURCES                     (Your Applications)
    │
    ├─ Prometheus Metrics  ──────┐
    ├─ OTLP Traces (OpenTelemetry)──┤
    └─ Structured Logs  ──────────┘
                │
                ▼
 2. COLLECTORS                            (Go Services)
    │
    ├─ prometheus-collector  :8080
    ├─ otlp-collector       :4317/4318
    └─ log-collector        :8082
                │
                │ (Avro serialization)
                ▼
 3. MESSAGE QUEUE                         (Apache Kafka)
    │
    ├─ Topic: raw-telemetry       (10 partitions)
    ├─ Topic: capsule-events      (10 partitions)
    └─ Topic: capsule-embeddings  (10 partitions)
                │
                ▼
 4. STREAM PROCESSING                     (Apache Flink)
    │
    ├─ Fingerprinting Job
    │  ├─ Parse telemetry
    │  ├─ Extract journey patterns
    │  ├─ Aggregate by endpoint/operation
    │  └─ Create capsules (fingerprints)
    │
    └─ Embedding Pipeline Job
       ├─ Generate semantic embeddings
       ├─ Store in Milvus (vector DB)
       └─ Enable similarity search
                │
                ▼
 5. STORAGE LAYER
    │
    ├─ PostgreSQL + TimescaleDB
    │  └─ Capsules (aggregated telemetry)
    │
    └─ Milvus (Vector DB)
       └─ Journey embeddings
                │
                ▼
 6. BACKEND API                           (FastAPI)
    │
    ├─ POST /api/v1/analyze
    │  └─ Trigger analysis job
    │
    ├─ Trace Graph Analysis
    │  ├─ Build service dependency graph
    │  ├─ Identify critical paths
    │  └─ Detect user journeys
    │
    ├─ SLI Generator
    │  ├─ Latency SLIs (p50/p95/p99)
    │  ├─ Error Rate SLIs
    │  └─ Availability SLIs
    │
    └─ LLM Recommender
       ├─ Context-aware analysis
       ├─ Historical pattern matching
       └─ SLO recommendations
                │
                ▼
 7. ARTIFACT GENERATION
    │
    ├─ Prometheus Alert Rules  (.yaml)
    ├─ Grafana Dashboards      (.json)
    ├─ SLO Definitions        (.yaml)
    └─ Runbooks               (.md)
                │
                ▼
 8. GITOPS OUTPUT
    │
    └─ Pull Request to monitoring repo
       ├─ monitoring/alerts/
       ├─ monitoring/dashboards/
       └─ slos/
```

---

## 📋 Step-by-Step Flow

### Step 1: Telemetry Ingestion

**Sources:**
- **Prometheus Metrics** - Counter, Gauge, Histogram
- **OTLP Traces** - Distributed tracing (OpenTelemetry)
- **Structured Logs** - JSON logs with structured fields

**Example Trace (OTLP):**
```json
{
  "resourceSpans": [{
    "resource": {
      "attributes": [
        {"key": "service.name", "value": {"stringValue": "api-gateway"}},
        {"key": "service.namespace", "value": {"stringValue": "production"}}
      ]
    },
    "scopeSpans": [{
      "spans": [{
        "traceId": "abc123...",
        "spanId": "def456...",
        "name": "/api/users",
        "startTimeUnixNano": 1699123456000000000,
        "endTimeUnixNano": 1699123456150000000,
        "attributes": [
          {"key": "http.method", "value": {"stringValue": "GET"}},
          {"key": "http.status_code", "value": {"intValue": 200}},
          {"key": "http.route", "value": {"stringValue": "/api/users"}}
        ]
      }]
    }]
  }]
}
```

### Step 2: Collectors Process Data

**Go Collectors** handle high-throughput telemetry:

```go
// Pseudo-code for OTLP Collector
func (c *OTLPCollector) ProcessTrace(trace *otlp.Trace) error {
    // 1. Validate trace
    if err := c.validator.Validate(trace); err != nil {
        return err
    }

    // 2. Enrich with metadata
    enriched := c.enricher.Enrich(trace)

    // 3. Serialize to Avro
    avroBytes, err := c.serializer.Serialize(enriched)
    if err != nil {
        return err
    }

    // 4. Publish to Kafka
    return c.kafkaProducer.Publish("raw-telemetry", avroBytes)
}
```

**Health Check:**
```bash
curl http://localhost:4318/health
# → {"status":"healthy","collector":"otlp","version":"1.0.0"}
```

### Step 3: Kafka Topics

**Topic Structure:**
```yaml
raw-telemetry:          # All incoming telemetry
  partitions: 10
  retention: 7 days
  compression: snappy

capsule-events:         # Fingerprinted capsules
  partitions: 10
  retention: 90 days

capsule-embeddings:     # Semantic embeddings
  partitions: 10
  retention: 90 days

raw-telemetry-dlq:      # Dead letter queue
  partitions: 3
  retention: 30 days
```

### Step 4: Flink Stream Processing

**Fingerprinting Job:**
```java
// Pseudo-code for Fingerprinting Job
DataStream<RawTelemetry> rawStream = env
    .addSource(new FlinkKafkaConsumer<>("raw-telemetry", ...))
    .keyBy(telemetry -> telemetry.getServiceName())
    .window(TumblingEventTimeWindows.of(Time.minutes(5)))
    .process(new FingerprintOperator());

// FingerprintOperator creates capsules:
// - Aggregates spans by (service, endpoint, http_method)
// - Calculates p50, p95, p99 latencies
// - Counts errors vs successes
// - Extracts journey patterns (span parent-child relationships)

rawStream
    .addSink(new FlinkKafkaProducer<>("capsule-events", ...));
```

**Capsule Example:**
```json
{
  "capsule_id": "svc:api-gateway|endpoint:/api/users|method:GET",
  "service_name": "api-gateway",
  "endpoint": "/api/users",
  "http_method": "GET",
  "window_start": "2025-11-04T17:00:00Z",
  "window_end": "2025-11-04T17:05:00Z",
  "metrics": {
    "request_count": 1250,
    "error_count": 15,
    "latency_p50": 120,
    "latency_p95": 380,
    "latency_p99": 850
  },
  "sample_traces": ["trace_id_1", "trace_id_2", ...]
}
```

### Step 5: Storage

**PostgreSQL Schema:**
```sql
CREATE TABLE capsules (
    capsule_id VARCHAR(255) PRIMARY KEY,
    service_name VARCHAR(100),
    endpoint VARCHAR(255),
    http_method VARCHAR(10),
    window_start TIMESTAMPTZ,
    window_end TIMESTAMPTZ,
    request_count BIGINT,
    error_count BIGINT,
    latency_p50 FLOAT,
    latency_p95 FLOAT,
    latency_p99 FLOAT,
    sample_traces JSONB
);

-- TimescaleDB hypertable for time-series optimization
SELECT create_hypertable('capsules', 'window_start');
```

**Milvus Collections:**
```python
# Journey embeddings collection
collection = Collection("journey_embeddings")
collection.create_index(
    field_name="embedding",
    index_params={
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 1024}
    }
)
```

### Step 6: Backend Analysis

**Analysis Trigger:**
```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "api-gateway",
    "namespace": "production",
    "lookback_hours": 24
  }'

# Response:
{
  "job_id": "job-api-gateway-abc123",
  "status": "accepted",
  "message": "Analysis started for api-gateway in production"
}
```

**Backend Processing:**
1. **Trace Graph Analysis** - Build service call graph
2. **Journey Discovery** - Identify user flows
3. **SLI Candidate Generation** - Recommend metrics
4. **LLM-Powered Recommendations** - Context-aware SLOs
5. **Artifact Generation** - Prometheus/Grafana configs

**Check Status:**
```bash
curl http://localhost:8000/api/v1/analyze/job-api-gateway-abc123

# Response:
{
  "job_id": "job-api-gateway-abc123",
  "status": "completed",
  "slis_found": 5,
  "slos_generated": 3,
  "journeys_discovered": 2
}
```

### Step 7: SLI/SLO Generation

**Generated SLIs:**
```yaml
# Latency SLI
- name: api_gateway_latency_p95
  metric: histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket[5m]))
  labels:
    service: api-gateway
    endpoint: /api/users

# Error Rate SLI
- name: api_gateway_error_rate
  metric: rate(http_requests_total{status=~"5.."}[5m]) /
          rate(http_requests_total[5m])
  labels:
    service: api-gateway

# Availability SLI
- name: api_gateway_availability
  metric: up{job="api-gateway"}
```

**Generated SLOs:**
```yaml
apiVersion: slo.slo-scout.io/v1alpha1
kind: ServiceLevelObjective
metadata:
  name: api-gateway-latency-slo
spec:
  service: api-gateway
  sli: api_gateway_latency_p95
  objective:
    target: 95.0  # 95% of requests < 500ms
    window: 30d
  budgetAlertThresholds:
    - threshold: 90  # Alert at 10% budget consumed
      severity: warning
    - threshold: 95  # Alert at 5% budget remaining
      severity: critical
```

### Step 8: Artifact Generation

**Prometheus Alert Rule:**
```yaml
groups:
  - name: api-gateway-slo-alerts
    rules:
      - alert: APIGatewayLatencySLOBreach
        expr: |
          (
            sum(rate(http_request_duration_seconds_bucket{
              service="api-gateway",
              le="0.5"
            }[5m]))
            /
            sum(rate(http_request_duration_seconds_count{
              service="api-gateway"
            }[5m]))
          ) < 0.95
        for: 5m
        labels:
          severity: critical
          service: api-gateway
        annotations:
          summary: "API Gateway latency SLO breach"
          description: "p95 latency exceeds 500ms for >5% of requests"
```

**Grafana Dashboard:**
```json
{
  "dashboard": {
    "title": "API Gateway SLO Dashboard",
    "panels": [
      {
        "title": "Request Latency (p95)",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service=\"api-gateway\"}[5m]))"
        }],
        "thresholds": [
          {"value": 500, "color": "red"}
        ]
      },
      {
        "title": "Error Rate",
        "targets": [{
          "expr": "rate(http_requests_total{service=\"api-gateway\",status=~\"5..\"}[5m])"
        }]
      }
    ]
  }
}
```

**Runbook:**
```markdown
# API Gateway Latency SLO Runbook

## Alert: APIGatewayLatencySLOBreach

### Severity: Critical
### SLO: 95% of requests < 500ms

## Investigation Steps

1. Check current latency:
   ```
   histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="api-gateway"}[5m]))
   ```

2. Identify slow endpoints:
   ```
   topk(5, histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{service="api-gateway"}[5m])) by (endpoint))
   ```

3. Check database query times
4. Review recent deployments
5. Scale API Gateway pods if needed

## Escalation
- Slack: #api-gateway-oncall
- PagerDuty: api-gateway-team
```

### Step 9: GitOps Integration

**Create Pull Request:**
```bash
# Backend creates PR automatically
POST /api/v1/pr/create
{
  "service": "api-gateway",
  "artifacts": {
    "prometheus_rules": "path/to/alerts.yaml",
    "grafana_dashboard": "path/to/dashboard.json",
    "slo_definition": "path/to/slo.yaml",
    "runbook": "path/to/runbook.md"
  },
  "repo": "company/monitoring-config",
  "branch": "slo-scout/api-gateway-slo"
}
```

---

## 🧪 Testing the Flow

### 1. Run E2E Test

```bash
# Start backend
cd backend
poetry run uvicorn src.main_demo:app --reload

# Run E2E test
python tests/e2e_flow_test.py --backend http://localhost:8000
```

**Expected Output:**
```
======================================================================
SLO-Scout End-to-End Flow Test
======================================================================

[STEP] Testing Backend Health
✓ Backend healthy: {'status': 'healthy', 'version': '1.0.0'}

[STEP] Sending Test Traces
ℹ Simulating trace ingestion (would send to OTLP collector at :4318)
ℹ Generated 3 test spans
✓ Test traces prepared

[STEP] Triggering Analysis Job
✓ Analysis job created: job-e2e-test-service-123
ℹ Status: accepted

[STEP] Checking Analysis Status
✓ Analysis status retrieved
ℹ Status: completed
ℹ SLIs found: 3
ℹ SLOs generated: 2

[STEP] Verifying SLI Generation
✓ SLI generation would analyze:
ℹ   - Request latencies (150ms, 450ms, 850ms)
ℹ   - Error rates (33% error rate detected)

[STEP] Verifying SLO Generation
✓ Expected SLO recommendations:
ℹ   - Latency SLO: p95 < 500ms
ℹ   - Error Rate SLO: < 1% errors

[STEP] Verifying Artifact Generation
✓ Expected artifacts:
ℹ   ✓ Prometheus AlertRule
ℹ   ✓ Grafana Dashboard JSON

Results: 7/7 tests passed
✓ All tests passed!
```

### 2. Deploy with Docker Compose

```bash
# Build and start all services
docker-compose up -d

# Check health
docker-compose ps

# View logs
docker-compose logs -f backend

# Send test telemetry
python tests/send_test_traces.py --otlp-endpoint http://localhost:4318

# Trigger analysis
curl -X POST http://localhost:8000/api/v1/analyze \
  -d '{"service_name":"test-service","namespace":"default"}'
```

### 3. Deploy to Kubernetes

```bash
# Create namespace
kubectl create namespace slo-scout

# Deploy with Helm
helm install slo-scout ./infrastructure/helm/slo-scout \
  --namespace slo-scout \
  --values infrastructure/helm/slo-scout/values-dev.yaml

# Port-forward to access services
kubectl port-forward -n slo-scout svc/backend 8000:8000
kubectl port-forward -n slo-scout svc/otlp-collector 4318:4318

# Check status
kubectl get pods -n slo-scout
```

---

## 📊 Key Metrics

| Component | Metric | Target |
|-----------|--------|--------|
| Collectors | Throughput | 10K+ events/sec |
| Kafka | Lag | < 1000 messages |
| Flink | Checkpoint Duration | < 10s |
| Backend | API Latency (p95) | < 500ms |
| E2E Latency | Ingestion → SLO | < 5 minutes |

---

## 🔧 Troubleshooting

### Issue: No traces appearing in backend

**Check:**
1. Collectors are running: `curl http://localhost:4318/health`
2. Kafka topics created: `kafka-topics --list --bootstrap-server localhost:9092`
3. Flink jobs running: Check Flink UI at http://localhost:8083
4. PostgreSQL connection: `psql -h localhost -U postgres -d slo_scout`

### Issue: SLI generation fails

**Check:**
1. Capsules in database: `SELECT COUNT(*) FROM capsules;`
2. Backend logs: `docker-compose logs backend`
3. Sufficient data (need >100 traces for meaningful SLIs)

---

## 🚀 Next Steps

1. **Configure your applications** to send telemetry to collectors
2. **Deploy SLO-Scout** using docker-compose or Kubernetes
3. **Run analysis** for your services
4. **Review recommendations** and adjust thresholds
5. **Integrate with GitOps** to automate SLO deployment

---

## 📚 Additional Resources

- [Architecture Guide](docs/architecture/README.md)
- [API Reference](docs/api/README.md)
- [Build Guide](BUILD.md)
- [Test Report](TEST_REPORT.md)

---

**Generated by SLO-Scout Team**
For issues: https://github.com/nordby/SLO-Scout/issues
