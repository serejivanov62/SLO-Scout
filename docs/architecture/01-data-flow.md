# SLO-Scout Data Flow Diagram

## Overview
This diagram shows the end-to-end data flow through the SLO-Scout system, from telemetry collection through to artifact deployment.

## Diagram

```mermaid
graph TB
    subgraph Sources["Telemetry Sources"]
        PROM["Prometheus<br/>(Metrics)"]
        OTLP["OpenTelemetry<br/>(Traces)"]
        LOGS["Loki/ELK<br/>(Logs)"]
        RUM["RUM SDK<br/>(User Sessions)"]
    end

    subgraph Collectors["Collection Layer (Go)"]
        PC["Prometheus<br/>Collector"]
        OC["OTLP<br/>Collector"]
        LC["Log<br/>Collector"]
        RC["RUM<br/>Collector"]
    end

    subgraph Streaming["Stream Processing Layer"]
        KAFKA["Apache Kafka<br/>Topics:<br/>• raw-telemetry<br/>• capsule-events<br/>• capsule-embeddings"]

        subgraph FlinkJobs["Flink Jobs (Java)"]
            FP["Fingerprinting Job<br/>• Normalize templates<br/>• PII redaction<br/>• SHA256 hashing"]
            AGG["Aggregation Job<br/>• Tumbling windows (1h)<br/>• Severity distribution<br/>• Reservoir sampling"]
            EMB["Embedding Job<br/>• Batch capsules<br/>• Generate vectors<br/>• Index in Milvus"]
        end
    end

    subgraph Storage["Storage Layer"]
        S3["S3/MinIO<br/>(Raw Samples)"]
        TSDB["TimescaleDB<br/>(Metadata + Time-series)"]
        MILVUS["Milvus<br/>(Vector Search)"]
    end

    subgraph Backend["Control Plane (Python)"]
        API["FastAPI<br/>REST API"]

        subgraph Services["Core Services"]
            JOURNEY["Journey<br/>Discovery"]
            SLIGEN["SLI<br/>Generator"]
            RAG["RAG Context<br/>Builder"]
            LLM["LLM<br/>Recommender"]
            ARTGEN["Artifact<br/>Generators"]
            POLICY["Policy<br/>Guard"]
        end
    end

    subgraph Validation["Validation & Deployment"]
        PROM_VAL["promtool<br/>Validator"]
        GRAF_VAL["Grafana<br/>Schema Validator"]
        GIT["GitHub/GitLab<br/>PR Creation"]
    end

    subgraph Output["Artifacts"]
        PROM_RULES["Prometheus<br/>Recording/Alert Rules"]
        DASHBOARDS["Grafana<br/>Dashboards"]
        RUNBOOKS["Runbook<br/>Templates"]
    end

    %% Data Flow Connections
    PROM -->|remote_read| PC
    OTLP -->|gRPC/HTTP| OC
    LOGS -->|HTTP| LC
    RUM -->|HTTP| RC

    PC -->|TelemetryEvent| KAFKA
    OC -->|TelemetryEvent| KAFKA
    LC -->|TelemetryEvent| KAFKA
    RC -->|TelemetryEvent| KAFKA

    KAFKA -->|raw-telemetry| FP
    FP -->|CapsuleEvent| KAFKA
    KAFKA -->|capsule-events| AGG
    AGG -->|aggregated| KAFKA
    KAFKA -->|capsule-events| EMB

    EMB -->|samples| S3
    EMB -->|metadata| TSDB
    EMB -->|vectors| MILVUS

    API -->|query| JOURNEY
    JOURNEY -->|traces| TSDB
    JOURNEY -->|metrics| PROM

    API -->|request| SLIGEN
    SLIGEN -->|evidence| RAG
    RAG -->|similarity| MILVUS
    RAG -->|metadata| TSDB
    RAG -->|samples| S3
    RAG -->|context| LLM

    LLM -->|recommendations| ARTGEN
    ARTGEN -->|validate| PROM_VAL
    ARTGEN -->|validate| GRAF_VAL
    ARTGEN -->|check policy| POLICY

    POLICY -->|approved| GIT
    GIT -->|commit| PROM_RULES
    GIT -->|commit| DASHBOARDS
    GIT -->|commit| RUNBOOKS

    %% Styling
    classDef source fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef collector fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef stream fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef storage fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef service fill:#fff9c4,stroke:#f57f17,stroke-width:2px
    classDef validation fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef output fill:#e0f2f1,stroke:#004d40,stroke-width:2px

    class PROM,OTLP,LOGS,RUM source
    class PC,OC,LC,RC collector
    class KAFKA,FP,AGG,EMB stream
    class S3,TSDB,MILVUS storage
    class API,JOURNEY,SLIGEN,RAG,LLM,ARTGEN,POLICY service
    class PROM_VAL,GRAF_VAL,GIT validation
    class PROM_RULES,DASHBOARDS,RUNBOOKS output
```

## Flow Description

### Phase 1: Collection (Telemetry Sources → Collectors → Kafka)
1. **Collectors** consume telemetry from multiple sources using native protocols
2. Each collector normalizes data to `TelemetryEvent` Avro schema
3. Events published to Kafka `raw-telemetry` topic with compression and batching

### Phase 2: Stream Processing (Kafka → Flink Jobs)
1. **Fingerprinting Job**:
   - Normalizes log/trace templates (masks variable tokens)
   - Redacts PII (email, IP, auth tokens)
   - Generates SHA256 fingerprint hash
2. **Aggregation Job**:
   - Windows events into 1-hour tumbling windows
   - Maintains severity distribution and counts
   - Keeps reservoir sample (max 10 events per fingerprint)
3. **Embedding Job**:
   - Batches capsules for efficiency
   - Calls embedding service (MiniLM or OpenAI)
   - Writes vectors to Milvus with metadata filters

### Phase 3: Storage (Flink → Storage Layer)
1. **TimescaleDB**: Stores capsule metadata, SLI/SLO definitions, audit trail
2. **S3/MinIO**: Stores raw telemetry samples (JSONL.gz) with lifecycle policies
3. **Milvus**: Indexes 384-dim vectors with HNSW for fast similarity search

### Phase 4: Analysis (API → Services → RAG → LLM)
1. **Journey Discovery**: Analyzes traces to identify critical user paths
2. **SLI Generator**: Proposes latency/error/availability metrics per journey
3. **RAG Builder**: Vector search retrieves relevant capsules as evidence
4. **LLM Recommender**: Generates SLO recommendations with confidence scores

### Phase 5: Artifact Generation (Services → Validators → GitOps)
1. **Artifact Generators**: Create Prometheus rules, Grafana dashboards, runbooks
2. **Validators**: `promtool` validates rules, schema validators check JSON
3. **Policy Guard**: Validates blast radius and approval requirements
4. **PR Creation**: Commits approved artifacts to GitHub/GitLab via PR

## Data Quality Requirements

| Stage | Requirement | Validation |
|-------|-------------|------------|
| Collection | Exactly-once delivery | Kafka idempotency keys |
| Fingerprinting | PII redacted before embedding | `redaction_applied=true` flag |
| Aggregation | Fingerprint uniqueness | Primary key on `fingerprint_hash + service + time_bucket` |
| Embedding | Vector dimensionality | 384-dim for MiniLM, 1536-dim for OpenAI |
| Artifact Generation | promtool validation | Exit code 0 required |

## Performance Characteristics

- **Ingest Throughput**: 100k logs/min (Enterprise tier)
- **Ingest Lag**: p95 < 60s (SLO target: 99%)
- **Query Latency**: p95 < 2s (SLO target: 95%)
- **Embedding Batch Size**: 100 capsules per API call
- **Retention**: 7d raw, 90d capsules, 1y aggregates
