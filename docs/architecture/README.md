# SLO-Scout Architecture Documentation

This directory contains comprehensive architecture diagrams for the SLO-Scout system using Mermaid syntax.

## Table of Contents

1. [Data Flow Diagram](#1-data-flow-diagram)
2. [Component Diagram](#2-component-diagram)
3. [Deployment Topology](#3-deployment-topology)
4. [Sequence Diagrams](#4-sequence-diagrams)
   - [Analysis Workflow](#41-analysis-workflow)
   - [SLO Creation & Simulation](#42-slo-creation--simulation)
   - [Artifact Deployment](#43-artifact-deployment)

---

## Overview

SLO-Scout is a distributed microservices system that automates SLI/SLO discovery and operational artifact generation for production services. The architecture follows a stream-processing pipeline:

```
Telemetry Sources → Collectors → Kafka → Flink → Storage → RAG → LLM → Artifacts → GitOps
```

**Key Technologies:**
- **Collectors**: Go 1.21+ (Prometheus, OTLP, Log collectors)
- **Streaming**: Apache Flink 1.18+, Kafka 3.5+, Avro schemas
- **Storage**: TimescaleDB (TSDB), S3/MinIO (blobs), Milvus (vectors)
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, sentence-transformers
- **Deployment**: Kubernetes, Helm, GitOps (ArgoCD/FluxCD)

---

## 1. Data Flow Diagram

**File**: [01-data-flow.md](./01-data-flow.md)

**Purpose**: Shows the end-to-end data flow through the system, from telemetry collection to artifact deployment.

**Key Flows**:
- **Phase 1**: Telemetry Sources → Collectors → Kafka (raw-telemetry topic)
- **Phase 2**: Kafka → Flink Fingerprinting Job → Capsule Events
- **Phase 3**: Flink Embedding Job → TimescaleDB + Milvus + S3
- **Phase 4**: API → RAG Builder → LLM → SLI/SLO Recommendations
- **Phase 5**: Artifact Generators → Validators → GitOps PR

**Diagram Type**: `graph TB` (top-to-bottom flowchart)

**Use Cases**:
- Understand data lineage and transformations
- Identify bottlenecks in the pipeline
- Plan data retention and storage strategies
- Debug data quality issues

**Performance Targets**:
- Ingest Throughput: 100k logs/min
- Ingest Lag: p95 < 60s
- Query Latency: p95 < 2s
- Retention: 7d raw, 90d capsules, 1y aggregates

---

## 2. Component Diagram

**File**: [02-component-diagram.md](./02-component-diagram.md)

**Purpose**: Shows all system components, their internal structure, and relationships.

**Component Layers**:
1. **Collector Layer** (Go): Prometheus, OTLP, Log collectors + Kafka producer
2. **Streaming Layer** (Java/Flink): Fingerprinting, Aggregation, Embedding jobs
3. **Backend Layer** (Python): API, Services, Generators, Validators, Integrations
4. **Storage Layer**: Kafka, TimescaleDB, S3/MinIO, Milvus

**Diagram Type**: `graph TB` with nested subgraphs

**Use Cases**:
- Onboard new developers (component ownership)
- Plan inter-component API contracts
- Identify code boundaries for refactoring
- Design testing strategies (unit, integration, contract)

**Inter-Component Contracts**:
- Collectors → Kafka: `TelemetryEvent.avsc` (Avro)
- Flink → Kafka: `CapsuleEvent.avsc` (Avro)
- API → Backend: Pydantic models (Python types)
- Backend → LLM: OpenAI-compatible HTTP API

---

## 3. Deployment Topology

**File**: [03-deployment-topology.md](./03-deployment-topology.md)

**Purpose**: Shows the Kubernetes deployment architecture, including namespaces, services, persistent storage, and networking.

**Namespace Organization**:
- `slo-scout-collectors`: Telemetry collection agents
- `slo-scout-streaming`: Kafka, Flink, Schema Registry
- `slo-scout-data`: TimescaleDB, Milvus, MinIO, Redis
- `slo-scout-backend`: API, Workers, Embedding service
- `slo-scout-frontend`: React UI
- `slo-scout-monitoring`: Prometheus, Grafana, Alertmanager

**Diagram Type**: `graph TB` with subgraphs for namespaces

**Use Cases**:
- Plan Kubernetes deployments (Helm charts)
- Design scaling strategies (HPA, VPA)
- Configure network policies and service mesh
- Estimate resource requirements and costs

**Scaling Tiers**:
- **Starter**: 50 cores, 100Gi RAM, 2Ti storage ($500-2k/month)
- **Pro**: 150 cores, 300Gi RAM, 10Ti storage ($1.5k-6k/month)
- **Enterprise**: 300+ cores, 600Gi+ RAM, 50Ti+ storage (custom)

---

## 4. Sequence Diagrams

### 4.1 Analysis Workflow

**File**: [04-sequence-analysis.md](./04-sequence-analysis.md)

**Purpose**: Step-by-step flow when an SRE triggers an analysis of a production service.

**Key Phases**:
1. **Request Submission** (< 1s): SRE → API → Worker (async task)
2. **Journey Discovery** (2-3 min): Analyze traces → Identify user journeys
3. **RAG Retrieval** (1-2 min): Vector search → Fetch capsules
4. **LLM Recommendation** (3-4 min): RAG context → LLM → SLI recommendations
5. **SLO Variant Generation** (1 min): Calculate thresholds (p95, p99, p99.9)
6. **Results Retrieval** (< 1s): Poll status → Display recommendations

**Diagram Type**: `sequenceDiagram`

**Use Cases**:
- Understand API contracts (request/response schemas)
- Estimate latency budgets for analysis
- Design error handling and retry strategies
- Plan instrumentation for low-confidence scenarios

**Performance**:
- Total analysis time: 6 min (median), 9 min (p95)
- API response time: 120ms (median), 300ms (p95)

---

### 4.2 SLO Creation & Simulation

**File**: [05-sequence-slo-creation.md](./05-sequence-slo-creation.md)

**Purpose**: Workflow for reviewing SLI recommendations, creating SLOs, and running backtest simulations.

**Key Phases**:
1. **SLI Review** (30s - 2 min): View recommendations with evidence links
2. **SLI Approval/Modification** (1-5 min): Approve as-is or modify PromQL
3. **SLO Creation** (1-2 min): Configure threshold, time window, target %
4. **Backtest Simulation** (30-120s): Monte Carlo simulation with historical data
5. **What-If Scenarios** (30-120s): Adjust traffic/replicas, re-simulate
6. **SLO Approval**: Review results, approve for artifact generation

**Diagram Type**: `sequenceDiagram`

**Use Cases**:
- Understand human-in-the-loop approval gates
- Design backtest simulation algorithms
- Plan what-if scenario parameter space
- Validate confidence score calculations

**Performance**:
- Backtest simulation: 45s (median), 90s (p95)
- What-if simulation: 60s (median), 110s (p95)

---

### 4.3 Artifact Deployment

**File**: [06-sequence-artifact-deployment.md](./06-sequence-artifact-deployment.md)

**Purpose**: Complete workflow for generating validated artifacts and deploying them via GitOps.

**Key Phases**:
1. **Artifact Generation** (30-60s): Prometheus rules, Grafana dashboards, runbooks
2. **Validation** (15-45s): promtool, JSON schema, dry-run evaluation
3. **Policy Guard Review** (5-10s): Blast radius calculation, approval checks
4. **GitOps PR Creation** (10-20s): Create branch, commit artifacts, open PR
5. **External Review & Deployment** (hours to days): Human review, CI/CD pipeline

**Diagram Type**: `sequenceDiagram`

**Use Cases**:
- Understand artifact validation gates (promtool, schema)
- Design Policy Guard invariants (blast radius)
- Plan GitOps repository structure
- Design audit trail and compliance logging

**Performance**:
- End-to-end (generation → PR): 1 min (median), 1.5 min (p95)

**Validators**:
- **promtool**: Validates Prometheus rules syntax
- **JSON schema**: Validates Grafana dashboard structure
- **YAML parser**: Validates runbook syntax
- **Dry-run evaluator**: Estimates alert trigger frequency with historical data

---

## Diagram Rendering

### Viewing in GitHub/GitLab
All diagrams use Mermaid syntax and render natively in GitHub/GitLab markdown viewers.

### Viewing Locally
1. **VS Code**: Install "Markdown Preview Mermaid Support" extension
2. **Obsidian**: Mermaid diagrams render by default
3. **mermaid-cli**: Generate PNG/SVG exports
   ```bash
   npm install -g @mermaid-js/mermaid-cli
   mmdc -i 01-data-flow.md -o 01-data-flow.png
   ```

### Embedding in Documentation
Copy the Mermaid code blocks into your documentation (Confluence, Notion, etc.) or export as images.

---

## Architecture Principles

### Constitutional Compliance

All diagrams reflect these constitutional principles:

1. **Purpose-Driven SLI/SLO Discovery**: Core data flow shows automated discovery from telemetry
2. **Quality First**: Validation gates (promtool, schema) shown in artifact deployment
3. **PII Redaction is Mandatory**: Redaction operator in fingerprinting job
4. **Human Approval for Production**: Approval gates in SLO creation and artifact deployment
5. **Self-Observability**: Monitoring namespace in deployment topology
6. **Privacy by Default**: On-prem embedding service in component diagram
7. **Iterate with Small Increments**: Incremental approval gates in sequences

### Design Patterns

- **Event-Driven Architecture**: Kafka as event backbone (data flow)
- **CQRS**: Separate read/write paths (component diagram)
- **RAG Pattern**: Vector search + LLM context (analysis workflow)
- **GitOps**: PR-based deployment (artifact deployment)
- **Policy Guard**: Pre-deployment blast radius checks (artifact deployment)

---

## Diagram Maintenance

### When to Update

| Trigger | Diagrams to Update |
|---------|-------------------|
| New telemetry source added | Data Flow, Component |
| New Flink job created | Data Flow, Component, Deployment |
| New API endpoint added | Component, Sequence (if workflow changed) |
| Storage technology changed | Data Flow, Component, Deployment |
| New validation step added | Artifact Deployment sequence |
| Scaling tier modified | Deployment Topology |

### Update Process

1. Edit Mermaid code in relevant `.md` file
2. Test rendering in VS Code or GitHub preview
3. Update this README if new diagram added
4. Commit changes with conventional commit message:
   ```
   docs(architecture): update data flow for new RUM collector
   ```

### Style Guide

- **Colors**: Use `classDef` for consistent theming
- **Labels**: Include technology names and versions
- **Annotations**: Use `Note over` for important clarifications
- **Subgraphs**: Group related components by layer/namespace
- **Arrows**: Use solid (`→`) for data flow, dashed (`-.->`) for control flow

---

## Related Documentation

- [Implementation Plan](../../specs/001-ingest-spec-txt/plan.md): Technical context and decisions
- [Data Model](../../specs/001-ingest-spec-kit/data-model.md): Entity schemas and relationships
- [API Contracts](../../specs/001-ingest-spec-txt/contracts/): OpenAPI and Avro schemas
- [Quickstart Guide](../../specs/001-ingest-spec-txt/quickstart.md): End-to-end validation walkthrough
- [Deployment Guide](../deployment.md): Installation and configuration

---

## Feedback & Contributions

- **Issues**: Report diagram errors or suggest improvements via GitHub Issues
- **Pull Requests**: Submit diagram updates following the style guide
- **Questions**: Ask in `#slo-scout-dev` Slack channel

---

**Last Updated**: 2025-10-04
**Version**: 1.0.0
**Maintainer**: SLO-Scout Architecture Team
