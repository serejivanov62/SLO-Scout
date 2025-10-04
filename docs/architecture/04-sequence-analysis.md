# Sequence Diagram: Analysis Workflow

## Overview
This diagram shows the step-by-step flow when an SRE triggers an analysis of a production service.

## Diagram

```mermaid
sequenceDiagram
    actor SRE as SRE Team Member
    participant UI as Web UI
    participant API as FastAPI Backend
    participant Worker as Celery Worker
    participant TSDB as TimescaleDB
    participant Prom as Prometheus
    participant Milvus as Milvus Vector DB
    participant S3 as S3/MinIO
    participant LLM as LLM Service

    %% Analysis Initiation
    SRE->>UI: Navigate to "Analyze Service"
    UI->>SRE: Display form (service name, environment, time range)
    SRE->>UI: Submit: service="payments-api", env="prod", days=30

    UI->>+API: POST /api/v1/analyze<br/>{service, environment, time_range}
    API->>API: Validate request schema
    API->>TSDB: Check if service exists
    TSDB-->>API: Service record found

    API->>API: Create AnalysisJob entity<br/>status="pending", job_id=UUID
    API->>TSDB: INSERT INTO analysis_job
    API->>Worker: Enqueue task(job_id, service, time_range)
    API-->>-UI: 202 Accepted<br/>{job_id, status, polling_url}

    UI->>SRE: Display "Analysis started"<br/>Show progress bar

    %% Background Processing
    Note over Worker,LLM: Async Processing (5-10 minutes)

    Worker->>+TSDB: UPDATE analysis_job<br/>status="running", progress=10%
    Worker->>Prom: Query metrics for payments-api<br/>time_range=30d
    Prom-->>Worker: Time-series data (latency, errors, requests)
    Worker->>TSDB: UPDATE progress=30%

    Worker->>Prom: Query traces for payments-api<br/>Extract service graph
    Prom-->>Worker: Trace data (span relationships, durations)
    Worker->>Worker: Build dependency graph<br/>Identify user journeys
    Worker->>TSDB: INSERT INTO user_journey<br/>(checkout, search, login)
    Worker->>TSDB: UPDATE progress=50%

    %% RAG Retrieval
    Worker->>Worker: For each journey, generate query embedding
    Worker->>Milvus: search(embedding, filter={service, timerange}, top_k=20)
    Milvus-->>Worker: Top 20 relevant capsules<br/>(fingerprints + metadata)

    Worker->>TSDB: SELECT capsule metadata<br/>WHERE capsule_id IN (...)
    TSDB-->>Worker: Capsule templates + counts

    Worker->>S3: GET sample events for capsules
    S3-->>Worker: JSONL.gz samples (raw logs/traces)
    Worker->>TSDB: UPDATE progress=70%

    %% LLM Recommendation
    Worker->>Worker: Build RAG context:<br/>- Journey traces<br/>- Capsule templates<br/>- Aggregated metrics

    Worker->>+LLM: POST /v1/chat/completions<br/>system: "You are an SRE expert..."<br/>user: "Recommend SLIs for checkout journey"<br/>context: {traces, capsules}
    LLM-->>-Worker: JSON response:<br/>{sli_recommendations: [<br/>  {name: "checkout_latency_p95",<br/>   metric: "histogram_quantile(0.95, ...)",<br/>   confidence: 92,<br/>   evidence: [capsule_123, trace_456]},<br/>  ...]}

    Worker->>Worker: Validate LLM response schema<br/>Check for hallucinations
    Worker->>TSDB: INSERT INTO sli<br/>(journey_id, metric, confidence)
    Worker->>TSDB: INSERT INTO evidence_pointer<br/>(sli_id, capsule_id, contribution)
    Worker->>TSDB: UPDATE progress=90%

    %% Generate SLO Variants
    Worker->>Prom: Query historical values for each SLI<br/>Calculate p95, p99, p99.9
    Prom-->>Worker: Historical distribution

    Worker->>Worker: Generate 3 SLO variants:<br/>- Conservative (p99.9 threshold)<br/>- Balanced (p99 threshold)<br/>- Aggressive (p95 threshold)

    Worker->>Worker: Run Monte Carlo simulation<br/>Estimate breach frequency
    Worker->>TSDB: INSERT INTO slo<br/>(sli_id, threshold, variant, breach_estimate)

    Worker->>TSDB: UPDATE analysis_job<br/>status="complete", progress=100%,<br/>result_url="/api/v1/journeys?service=payments-api"
    Worker->>-TSDB: Commit transaction

    %% Polling and Results
    loop Every 5 seconds
        UI->>+API: GET /api/v1/analyze/{job_id}
        API->>TSDB: SELECT status, progress FROM analysis_job
        TSDB-->>API: {status, progress}
        API-->>-UI: {status="running", progress=70%}
        UI->>UI: Update progress bar
    end

    UI->>+API: GET /api/v1/analyze/{job_id}
    API->>TSDB: SELECT status, result_url
    TSDB-->>API: {status="complete", result_url}
    API-->>-UI: 200 OK {status="complete", result_url}

    UI->>UI: Redirect to result_url
    UI->>+API: GET /api/v1/journeys?service=payments-api
    API->>TSDB: SELECT * FROM user_journey<br/>JOIN sli ON journey_id<br/>WHERE service="payments-api"
    TSDB-->>API: Journey + SLI data
    API-->>-UI: 200 OK {journeys: [...]}

    UI->>SRE: Display results:<br/>- 3 journeys discovered<br/>- 15 SLI recommendations<br/>- Confidence scores<br/>- Evidence links

    %% Data Quality Check
    alt Low Confidence (< 70%)
        UI->>SRE: Show warning: "Low data quality"<br/>Display instrumentation recommendations
        SRE->>UI: Click "View Recommendations"
        UI->>+API: GET /api/v1/instrumentation?service=payments-api
        API->>TSDB: SELECT * FROM instrumentation_recommendation
        TSDB-->>API: Recommendations data
        API-->>-UI: {recommendations: [<br/>  {type: "enable_rum", expected_uplift: 25%},<br/>  {type: "add_request_id", code_snippet: "..."}]}
        UI->>SRE: Show actionable steps with code snippets
    end
```

## Flow Summary

### Phase 1: Request Submission (< 1s)
1. SRE submits analysis request via UI
2. API validates request and creates `AnalysisJob` record
3. Worker task enqueued for async processing
4. API returns `job_id` and `polling_url` with 202 Accepted

### Phase 2: Journey Discovery (2-3 min)
1. Worker queries Prometheus for metrics and traces (30-day window)
2. Builds service dependency graph from trace spans
3. Identifies critical user journeys (entry → exit paths)
4. Persists `UserJourney` records to TimescaleDB

### Phase 3: RAG Retrieval (1-2 min)
1. For each journey, generate embedding query
2. Milvus vector search returns top-K relevant capsules
3. Fetch capsule metadata from TimescaleDB
4. Fetch raw samples from S3 for evidence

### Phase 4: LLM Recommendation (3-4 min)
1. Build RAG context (traces + capsules + aggregated metrics)
2. Call LLM with few-shot prompt for SLI recommendations
3. Validate LLM response schema (detect hallucinations)
4. Persist `SLI` records with `evidence_pointers`

### Phase 5: SLO Variant Generation (1 min)
1. Query historical SLI values from Prometheus
2. Calculate percentile thresholds (p95, p99, p99.9)
3. Run Monte Carlo simulation for breach frequency
4. Persist `SLO` records with 3 variants per SLI

### Phase 6: Results Retrieval (< 1s)
1. UI polls `/analyze/{job_id}` every 5 seconds
2. When `status=complete`, redirect to `result_url`
3. Fetch journeys, SLIs, SLOs with confidence scores
4. Display evidence links (capsule IDs, trace IDs)

## Error Handling

| Error Scenario | HTTP Code | Response | Retry Strategy |
|----------------|-----------|----------|----------------|
| Service not found | 404 | `{error: "Service 'xyz' not found"}` | None (user error) |
| Insufficient data (< 24h) | 400 | `{error: "Need >= 24h telemetry"}` | Wait for data |
| LLM API timeout | 500 | `{error: "LLM unavailable"}` | Exponential backoff, max 3 retries |
| Milvus unavailable | 503 | `{error: "Vector search degraded"}` | Fallback to rule-based SLI (no RAG) |
| Prometheus query timeout | 504 | `{error: "Metrics query timeout"}` | Reduce time range, split queries |

## Performance Characteristics

| Metric | Target | Actual (Median) | P95 |
|--------|--------|-----------------|-----|
| Total analysis time | < 10 min | 6 min | 9 min |
| Journey discovery | < 3 min | 2 min | 4 min |
| RAG retrieval | < 2 min | 1.5 min | 3 min |
| LLM recommendation | < 5 min | 3 min | 6 min |
| API response time | < 500ms | 120ms | 300ms |
| Poll interval | 5s | 5s | 5s |

## Constitutional Compliance

- **Quality First**: LLM responses validated against JSON schema before persistence
- **PII Redaction**: All capsule samples redacted before display
- **Human Approval**: SLIs marked `approved_by=null` until human review
- **Self-Observability**: Worker exports `analysis_duration_seconds` metric
