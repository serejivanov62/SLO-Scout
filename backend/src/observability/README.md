# SLO-Scout Self-Observability

Implementation of SLO-Scout's own observability metrics, SLOs, and monitoring dashboards (Sprint 4.2, Tasks T142-T145).

## Overview

Per spec.md FR-024, FR-025, FR-026, SLO-Scout monitors its own performance using the same artifact generation pipeline it provides to users. This demonstrates "dogfooding" and ensures the platform meets its own quality standards.

## Components

### 1. Prometheus Metrics Exporter (`metrics.py`)
**Task**: T142

Exports comprehensive metrics for all SLO-Scout components:

#### Core Metrics (FR-024)
- `slo_scout_ingest_lag_seconds` - Time delay between event timestamp and ingestion
- `slo_scout_embedding_queue_length` - Capsules waiting for embedding generation
- `slo_scout_vector_query_latency_seconds` - Vector similarity search latency
- `slo_scout_llm_calls_per_min` - LLM API call rate
- `slo_scout_daily_llm_spend_usd` - Estimated daily LLM cost

#### Supporting Metrics
- Analysis job duration and status
- SLI recommendation counts and confidence scores
- Artifact generation and validation metrics
- Database query performance
- Kafka consumer lag
- HTTP API request metrics

### 2. SLO Definitions (`/infrastructure/prometheus/slo-scout-slos.yaml`)
**Task**: T143

Recording rules that define SLO-Scout's own SLOs per FR-025:

- **99% ingest freshness < 60s** - Telemetry must be processed within 60 seconds
- **95% query latency < 2s** - Vector searches complete within 2 seconds
- **95% summarization < 5m** - Analysis jobs complete within 5 minutes

Additional recording rules calculate:
- Error budget remaining (%)
- Multi-window SLI tracking (1h, 6h, 24h, 30d)
- Supporting metrics (LLM latency, API success rate, etc.)

### 3. Grafana Dashboard (`/infrastructure/grafana/slo-scout-dashboard.json`)
**Task**: T144

Self-observability dashboard with panels per FR-026:

#### SLO Status Overview
- Real-time SLO compliance indicators
- Red/Green status for each SLO

#### Ingest Pipeline
- Ingest lag P99 vs. 60s threshold
- Error budget gauge
- Event ingestion rate by telemetry type

#### Embedding Pipeline
- Queue length monitoring
- Generation duration P95
- Batch processing metrics

#### Vector Search
- Query latency P95 vs. 2s threshold
- Error budget gauge
- Query result distribution

#### Analysis Engine
- Job duration P95 vs. 5m threshold
- Error budget gauge
- SLI recommendation quality metrics

#### Supporting Panels
- LLM request latency and cost
- Kafka consumer lag
- Database query performance
- HTTP API metrics

### 4. Alert Rules (`/infrastructure/prometheus/slo-scout-alerts.yaml`)
**Task**: T145

Alert rules per research.md appendix B.1:

#### Critical SLO Breach Alerts
- `SLOScoutIngestLagHigh` - Ingest lag > 60s for 5m
- `SLOScoutIngestFreshnessSLOBreach` - SLO compliance < 99%
- `SLOScoutVectorQueryLatencyHigh` - Query latency > 2s for 5m
- `SLOScoutVectorQuerySLOBreach` - SLO compliance < 95%
- `SLOScoutAnalysisDurationHigh` - Analysis > 5m for 5m
- `SLOScoutAnalysisSLOBreach` - SLO compliance < 95%

#### Component Health Alerts
- `SLOScoutEmbeddingQueueBacklog` - Queue > 1000 capsules
- `SLOScoutEmbeddingQueueCritical` - Queue > 5000 capsules
- `SLOScoutLLMLatencyHigh` - LLM latency > 30s
- `SLOScoutLLMErrorRateHigh` - LLM error rate > 10%
- `SLOScoutDailyLLMSpendHigh` - Daily spend > $100

#### Error Budget Burn Rate Alerts
- `SLOScoutIngestErrorBudgetBurnRateFast` - 14.4x burn rate
- `SLOScoutVectorQueryErrorBudgetBurnRateFast` - 6x burn rate

#### Infrastructure Alerts
- Kafka consumer lag and stall detection
- Database connection pool exhaustion
- Database query latency degradation
- API latency and error rate

## Usage

### Initialize Metrics

```python
from backend.src.observability.metrics import init_metrics

# Initialize on application startup
metrics = init_metrics(
    version="1.0.0",
    environment="production",
    deployment_id="prod-us-east-1",
    embedding_model="all-MiniLM-L6-v2"
)
```

### Record Metrics

```python
from backend.src.observability.metrics import get_metrics

metrics = get_metrics()

# Record ingest lag
metrics.record_ingest_lag(
    lag_seconds=15.5,
    service="payment-api",
    environment="prod",
    telemetry_type="logs"
)

# Record vector query
metrics.observe_vector_query(
    duration_seconds=0.125,
    operation="search",
    collection="capsules",
    num_results=20
)

# Record LLM request
metrics.observe_llm_request(
    duration_seconds=2.5,
    model="gpt-4",
    operation="recommend_sli",
    status="success",
    input_tokens=1500,
    output_tokens=500
)

# Update LLM spend
metrics.update_daily_llm_spend(
    spend_usd=45.67,
    model="gpt-4"
)
```

### Expose Metrics Endpoint

```python
# In FastAPI app (already integrated in src/api/metrics.py)
from fastapi import FastAPI
from backend.src.api.metrics import router as metrics_router

app = FastAPI()
app.include_router(metrics_router)

# Metrics available at: GET /metrics
```

### Deploy Prometheus Configuration

```bash
# Deploy SLO definitions
kubectl apply -f infrastructure/prometheus/slo-scout-slos.yaml

# Deploy alert rules
kubectl apply -f infrastructure/prometheus/slo-scout-alerts.yaml

# Verify rules are loaded
promtool check rules infrastructure/prometheus/slo-scout-slos.yaml
promtool check rules infrastructure/prometheus/slo-scout-alerts.yaml
```

### Deploy Grafana Dashboard

```bash
# Import dashboard via Grafana API
curl -X POST http://grafana:3000/api/dashboards/db \
  -H "Content-Type: application/json" \
  -d @infrastructure/grafana/slo-scout-dashboard.json

# Or manually import via Grafana UI:
# Dashboard > Import > Upload JSON file
```

## SLO Targets

| SLO | Target | Measurement Window | Error Budget |
|-----|--------|-------------------|--------------|
| Ingest Freshness | 99% < 60s | 30 days | 1% (43.2 minutes/month) |
| Query Latency | 95% < 2s | 30 days | 5% (36 hours/month) |
| Summarization Duration | 95% < 5m | 30 days | 5% (36 hours/month) |

## Alert Severity Levels

- **Critical**: Immediate action required, user-facing impact
  - SLO breaches
  - Component failures
  - Error budget burn rate > 10x

- **Major**: Investigation needed soon, potential user impact
  - Performance degradation
  - Queue backlog
  - Elevated error rates

- **Warning**: Monitor closely, no immediate action
  - Approaching thresholds
  - Capacity warnings

## Testing

```bash
# Run unit tests
cd backend
poetry run pytest tests/unit/test_metrics_exporter.py -v

# Expected: 95%+ coverage of metrics.py

# Test metrics endpoint
curl http://localhost:8000/metrics

# Verify Prometheus format
curl -s http://localhost:8000/metrics | grep slo_scout_ingest_lag_seconds
```

## Monitoring Best Practices

1. **Alert Fatigue Prevention**
   - Alerts tied to SLO breaches, not arbitrary thresholds
   - Multi-window burn rate alerts reduce false positives
   - Annotations include runbook links

2. **Error Budget Tracking**
   - Dashboard shows real-time budget consumption
   - Multi-window views (1h, 6h, 24h, 30d) detect trends
   - Alerts fire on fast burn rates (14.4x, 6x)

3. **Cost Control**
   - Daily LLM spend tracking
   - Alerts on budget overruns
   - Token consumption by operation

4. **Capacity Planning**
   - Embedding queue saturation tracking
   - Database connection pool monitoring
   - Kafka consumer lag trending

## Integration with Main Pipeline

SLO-Scout uses its own artifact generators to create these observability artifacts:

```python
from backend.src.generators.alert_rule_generator import AlertRuleGenerator
from backend.src.generators.grafana_generator import GrafanaDashboardGenerator

# Example: Generate alert for own metrics
generator = AlertRuleGenerator()
alert_yaml = generator.generate(
    slo_id="slo-scout-ingest-freshness",
    sli_name="ingest_lag_p99",
    metric_definition="slo_scout:ingest_lag:p99",
    threshold_value=60,
    comparison_operator="gt",
    time_window=timedelta(hours=1),
    service_name="slo-scout",
    environment="prod",
    severity="critical"
)
```

This ensures SLO-Scout's own monitoring is generated using the same validated pipeline provided to users.

## References

- **Spec**: `/specs/001-ingest-spec-txt/spec.md` (FR-024, FR-025, FR-026)
- **Research**: `/specs/001-ingest-spec-txt/research.md` (Appendix B.1)
- **Tasks**: `/specs/001-ingest-spec-txt/tasks.md` (T142-T145)
- **Generators**: `/backend/src/generators/`
