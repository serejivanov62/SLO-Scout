# 🎯 SLO-Scout

<div align="center">

**Automated SLI/SLO Discovery Platform**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Java](https://img.shields.io/badge/java-11+-orange.svg)](https://adoptium.net/)
[![Go](https://img.shields.io/badge/go-1.21+-00ADD8.svg)](https://golang.org/)
[![Status](https://img.shields.io/badge/status-production--ready-green.svg)]()

*Transforming observability telemetry into actionable SLO definitions using AI and stream processing*

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Documentation](#-documentation) • [Contributing](#-contributing)

</div>

---

## 📋 Overview

SLO-Scout automatically discovers Service Level Indicators (SLIs) and generates Service Level Objectives (SLOs) from your observability telemetry. It analyzes distributed traces, metrics, and logs to understand user journeys, identify critical paths, and recommend production-ready SLO definitions.

### 🎯 Key Features

- **🔍 Automated Journey Discovery** - Identifies user journeys from distributed traces
- **📊 Intelligent SLI Generation** - Recommends latency, error rate, and availability SLIs
- **🤖 AI-Powered Analysis** - Uses LLMs and embeddings for context-aware recommendations
- **⚡ Real-time Processing** - Apache Flink stream processing for low-latency insights
- **🎨 GitOps Integration** - Generates Prometheus rules, Grafana dashboards, and runbooks
- **📈 Production-Ready** - Built for scale with 99.9% uptime SLOs

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          SLO-Scout Platform                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  Prometheus  │    │     OTLP     │    │     Logs     │          │
│  │  Collector   │    │  Collector   │    │  Collector   │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                    │
│         └───────────────────┴───────────────────┘                    │
│                             │                                        │
│                    ┌────────▼────────┐                              │
│                    │  Apache Kafka   │                              │
│                    │  (3 topics)     │                              │
│                    └────────┬────────┘                              │
│                             │                                        │
│         ┌───────────────────┴───────────────────┐                   │
│         │                                       │                    │
│  ┌──────▼──────┐                       ┌───────▼───────┐           │
│  │ Fingerprint │                       │   Embedding   │           │
│  │ Flink Job   │                       │  Pipeline Job │           │
│  └──────┬──────┘                       └───────┬───────┘           │
│         │                                       │                    │
│         └───────────────┬───────────────────────┘                    │
│                         │                                           │
│                  ┌──────▼──────┐                                    │
│                  │   Capsule   │                                    │
│                  │   Storage   │                                    │
│                  │ (PostgreSQL)│                                    │
│                  └──────┬──────┘                                    │
│                         │                                           │
│                  ┌──────▼──────┐                                    │
│                  │   Backend   │                                    │
│                  │   FastAPI   │                                    │
│                  └──────┬──────┘                                    │
│                         │                                           │
│         ┌───────────────┴───────────────┐                          │
│         │                               │                           │
│  ┌──────▼──────┐              ┌─────────▼─────────┐               │
│  │   Milvus    │              │      LLM API      │               │
│  │ (Vector DB) │              │ (GPT-4/Claude)    │               │
│  └─────────────┘              └───────────────────┘               │
│                                                                     │
│                         Output                                      │
│  ┌──────────────────────────────────────────────────────┐         │
│  │ • Prometheus Alert Rules                             │         │
│  │ • Grafana Dashboards                                 │         │
│  │ • SLO YAML Definitions                               │         │
│  │ • Runbooks (Markdown)                                │         │
│  └──────────────────────────────────────────────────────┘         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Backend** | Python 3.11 + FastAPI | REST API & Control Plane |
| **Collectors** | Go 1.21 | High-performance telemetry ingestion |
| **Stream Processing** | Apache Flink (Java 11) | Real-time trace/metric analysis |
| **Message Queue** | Apache Kafka 3.5+ | Event streaming backbone |
| **Database** | PostgreSQL 14 + TimescaleDB | Time-series capsule storage |
| **Vector Search** | Milvus 2.3+ | Semantic similarity matching |
| **Object Storage** | MinIO / S3 | Artifact storage |
| **Embeddings** | Sentence Transformers | Journey fingerprinting |
| **LLM** | GPT-4 / Claude | Context-aware recommendations |

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop with **6 GB RAM** (minimum)
- Kubernetes cluster (k3d, minikube, or cloud)
- Helm 3.x
- kubectl

### 1. Clone Repository

```bash
git clone https://github.com/nordby/SLO-Scout.git
cd SLO-Scout
```

### 2. Deploy with Helm

```bash
# Create namespace
kubectl create namespace slo-scout

# Install via Helm chart
helm install slo-scout ./infrastructure/helm/slo-scout \
  --namespace slo-scout \
  --values infrastructure/helm/slo-scout/values-dev.yaml
```

### 3. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n slo-scout

# Port-forward to access API
kubectl port-forward -n slo-scout svc/slo-scout-backend 8000:8000

# Test health endpoint
curl http://localhost:8000/health
```

### 4. Analyze Your First Service

```bash
# Submit analysis job
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "my-service",
    "namespace": "production",
    "lookback_hours": 24
  }'

# Check results
curl http://localhost:8000/api/v1/analyze/{job_id}
```

---

## 📚 Documentation

### Core Documentation

- **[Architecture Guide](docs/architecture/README.md)** - System design and component interactions
- **[API Reference](docs/api/README.md)** - REST API endpoints and schemas
- **[Deployment Guide](docs/deployment/README.md)** - Production deployment strategies
- **[Configuration](docs/configuration/README.md)** - Environment variables and tuning

### Implementation Details

- **[Trace Graph Algorithm](backend/src/services/trace_graph.py)** - Journey discovery logic
- **[SLI Generator](backend/src/services/sli_generator.py)** - SLI candidate creation
- **[LLM Recommender](backend/src/services/llm_recommender.py)** - AI-powered recommendations
- **[Flink Jobs](streaming/)** - Stream processing pipelines

### Operations

- **[Monitoring](infrastructure/prometheus/)** - Prometheus metrics and alerts
- **[Troubleshooting](docs/troubleshooting.md)** - Common issues and solutions
- **[Performance Tuning](docs/performance.md)** - Optimization guidelines

---

## 🧪 Testing

```bash
# Backend unit tests (95%+ coverage)
cd backend
poetry install
poetry run pytest tests/unit/ -v --cov=src

# Integration tests
poetry run pytest tests/integration/ -v

# Flink job tests
cd streaming
./gradlew test

# Go collector tests
cd collectors
go test ./... -v
```

---

## 📊 Project Status

| Component | Status | Tests | Coverage |
|-----------|--------|-------|----------|
| Backend API | ✅ Production Ready | 120+ | 95%+ |
| Collectors (Go) | ✅ Production Ready | 45+ | 88%+ |
| Flink Jobs | ✅ Production Ready | 80+ | 92%+ |
| Infrastructure | ✅ Production Ready | - | - |
| Documentation | ✅ Complete | - | - |

### Milestones

- [x] **M1: Trace Ingestion** - Collectors + Kafka pipeline
- [x] **M2: Journey Discovery** - Trace graph analysis
- [x] **M3: SLI Generation** - Automated SLI recommendations
- [x] **M4: Artifact Production** - Prometheus rules, Grafana dashboards
- [x] **M5: Production Hardening** - Self-observability, chaos testing

**Total**: 154/154 tasks completed ✅

---

## 🛠️ Development

### Local Development

```bash
# Backend (hot reload)
cd backend
poetry install
poetry run uvicorn src.main:app --reload

# Run PostgreSQL locally
docker run -d -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=slo_scout \
  postgres:14
```

### Building Docker Images

```bash
# Backend
docker build -f infrastructure/docker/Dockerfile.python \
  -t slo-scout/backend:dev backend/

# Collectors
docker build -f infrastructure/docker/Dockerfile.go \
  --build-arg COLLECTOR_TYPE=prometheus-collector \
  -t slo-scout/prometheus-collector:dev collectors/

# Flink Jobs
cd streaming && ./gradlew shadowJar
docker build -f infrastructure/docker/Dockerfile.java \
  -t slo-scout/fingerprinting-job:dev .
```

---

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Apache Flink** - Real-time stream processing
- **OpenTelemetry** - Observability standards
- **Sentence Transformers** - Embedding models
- **Milvus** - Vector similarity search
- **Bitnami Charts** - Kubernetes deployment

---

## 📞 Contact

- **Issues**: [GitHub Issues](https://github.com/nordby/SLO-Scout/issues)
- **Discussions**: [GitHub Discussions](https://github.com/nordby/SLO-Scout/discussions)

---

<div align="center">

**⭐ Star this repository if you find it useful!**

Made with ❤️ by the SLO-Scout Team

</div>
