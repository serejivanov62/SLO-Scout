# SLO-Scout Helm Chart

Automated SLI/SLO discovery and operational artifact generation platform for Kubernetes.

## Overview

SLO-Scout analyzes telemetry data (metrics, traces, logs) from production services to automatically discover critical user journeys, recommend Service Level Indicators (SLIs), and generate production-ready observability artifacts including Prometheus alert rules, Grafana dashboards, and operational runbooks.

## Architecture Components

This Helm chart deploys the following components:

### Core Components

- **Collectors** (Go): Telemetry collection agents
  - Prometheus collector (remote_read)
  - OTLP collector (traces/metrics via gRPC)
  - Log collector (FluentBit-compatible)

- **Streaming Jobs** (Apache Flink): Real-time data processing
  - Fingerprinting job: Pattern extraction and PII redaction
  - Embedding pipeline: Vector generation for semantic search

- **Backend** (Python FastAPI): Control plane and API
  - REST API for analysis, SLI/SLO management
  - RAG-based recommendation engine
  - Artifact generators (Prometheus, Grafana, runbooks)
  - Policy Guard for deployment governance

### Infrastructure Dependencies

- **Apache Kafka**: Message streaming backbone
- **TimescaleDB**: Time-series and relational data storage
- **MinIO**: S3-compatible object storage for raw telemetry
- **Milvus**: Vector database for semantic search
- **Prometheus**: Metrics storage and querying
- **Grafana**: Dashboards and visualization

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure
- At least 16 CPU cores and 32GB RAM for production deployment
- (Optional) cert-manager for TLS certificate management
- (Optional) Prometheus Operator for ServiceMonitor support

## Installation

### Quick Start (Development)

```bash
# Add Helm dependencies
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

# Install with default values (development configuration)
helm install slo-scout ./slo-scout \
  --namespace slo-scout \
  --create-namespace \
  --set global.environment=dev
```

### Production Installation

```bash
# Create namespace
kubectl create namespace slo-scout

# Create secrets (use external-secrets or sealed-secrets in production)
kubectl create secret generic slo-scout-db-credentials \
  --from-literal=password='<strong-password>' \
  -n slo-scout

kubectl create secret generic slo-scout-minio-credentials \
  --from-literal=accessKey='<access-key>' \
  --from-literal=secretKey='<secret-key>' \
  -n slo-scout

kubectl create secret generic slo-scout-jwt-secret \
  --from-literal=secretKey='<jwt-secret>' \
  -n slo-scout

# Install with production values
helm install slo-scout ./slo-scout \
  --namespace slo-scout \
  --values values-production.yaml \
  --set backend.ingress.hosts[0].host=api.slo-scout.example.com \
  --set grafana.ingress.hosts[0]=grafana.slo-scout.example.com
```

### Staging Installation

```bash
helm install slo-scout ./slo-scout \
  --namespace slo-scout-staging \
  --create-namespace \
  --values values-staging.yaml
```

## Configuration

### Key Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `global.environment` | Environment name (dev/staging/production) | `production` |
| `global.imageRegistry` | Docker registry for images | `docker.io` |
| `namespaceOverride` | Override namespace | `slo-scout` |

### Collectors Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `collectors.prometheus.enabled` | Enable Prometheus collector | `true` |
| `collectors.prometheus.replicaCount` | Number of replicas | `2` |
| `collectors.prometheus.config.prometheusUrl` | Prometheus endpoint | `http://prometheus:9090` |
| `collectors.otlp.enabled` | Enable OTLP collector | `true` |
| `collectors.otlp.replicaCount` | Number of replicas | `3` |
| `collectors.otlp.autoscaling.enabled` | Enable HPA | `true` |
| `collectors.log.enabled` | Enable log collector (DaemonSet) | `true` |

### Flink Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `flink.jobmanager.enabled` | Enable Flink JobManager | `true` |
| `flink.taskmanager.replicaCount` | Number of TaskManagers | `3` |
| `flink.jobs.fingerprinting.enabled` | Enable fingerprinting job | `true` |
| `flink.jobs.fingerprinting.config.parallelism` | Job parallelism | `10` |
| `flink.jobs.embedding.enabled` | Enable embedding pipeline | `true` |

### Backend Configuration

| Parameter | Description | Default |
|-----------|-------------|---------|
| `backend.enabled` | Enable backend API | `true` |
| `backend.replicaCount` | Number of replicas | `3` |
| `backend.ingress.enabled` | Enable ingress | `true` |
| `backend.ingress.className` | Ingress class | `nginx` |
| `backend.llm.provider` | LLM provider (local/openai) | `local` |
| `backend.llm.model` | Embedding model | `all-MiniLM-L6-v2` |
| `backend.autoscaling.enabled` | Enable HPA | `true` |

### Infrastructure Dependencies

| Parameter | Description | Default |
|-----------|-------------|---------|
| `kafka.enabled` | Deploy Kafka | `true` |
| `kafka.replicaCount` | Kafka brokers | `3` |
| `timescaledb.enabled` | Deploy TimescaleDB | `true` |
| `timescaledb.readReplicas.replicaCount` | Read replicas | `2` |
| `minio.enabled` | Deploy MinIO | `true` |
| `minio.mode` | MinIO mode (standalone/distributed) | `distributed` |
| `milvus.enabled` | Deploy Milvus | `true` |
| `prometheus.enabled` | Deploy Prometheus | `true` |
| `grafana.enabled` | Deploy Grafana | `true` |

## Scaling Configuration

### Development Environment

Minimal resources for local testing:

```yaml
# values-dev.yaml
global:
  environment: dev

collectors:
  prometheus:
    replicaCount: 1
  otlp:
    replicaCount: 1
    autoscaling:
      enabled: false

backend:
  replicaCount: 1
  autoscaling:
    enabled: false

kafka:
  replicaCount: 1
timescaledb:
  readReplicas:
    replicaCount: 0
minio:
  mode: standalone
  replicas: 1
```

### Staging Environment

```yaml
# values-staging.yaml
global:
  environment: staging

kafka:
  replicaCount: 2
backend:
  replicaCount: 2
```

### Production Environment

Default `values.yaml` is configured for production with:
- High availability (multiple replicas)
- Autoscaling enabled
- Resource limits configured
- Network policies enabled
- Pod disruption budgets

## External Dependencies

To use external (existing) infrastructure components instead of deploying them:

```yaml
# Disable built-in Kafka, use external
kafka:
  enabled: false

externalKafka:
  bootstrapServers: "kafka-broker-1:9092,kafka-broker-2:9092"

# Disable built-in TimescaleDB, use external
timescaledb:
  enabled: false

externalDatabase:
  host: "postgres.example.com"
  port: 5432
  database: "slo_scout"
  username: "slo_scout"
  # Password from secret

# Disable built-in MinIO, use S3
minio:
  enabled: false

externalS3:
  endpoint: "s3.amazonaws.com"
  region: "us-west-2"
  bucket: "slo-scout-telemetry"
```

## Secrets Management

### Using Kubernetes Secrets (Development)

Secrets are auto-generated from `values.yaml` (not recommended for production).

### Using external-secrets (Recommended for Production)

```yaml
externalSecrets:
  enabled: true
  backend: aws-secretsmanager  # or vault, gcpsm, etc.
  secretStore: slo-scout-secrets
```

### Using sealed-secrets

```bash
# Create sealed secret
kubectl create secret generic slo-scout-db-credentials \
  --from-literal=password='strong-password' \
  --dry-run=client -o yaml | \
  kubeseal -o yaml > sealed-secret.yaml

kubectl apply -f sealed-secret.yaml
```

## Monitoring and Observability

### Self-Observability

SLO-Scout monitors its own performance using:

- **Prometheus metrics**: Ingest lag, query latency, embedding queue length
- **ServiceMonitor**: Auto-discovered by Prometheus Operator
- **Grafana dashboards**: Pre-configured dashboards in `infrastructure/grafana/`
- **Alert rules**: SLO breach alerts for SLO-Scout itself

Enable ServiceMonitor:

```yaml
serviceMonitor:
  enabled: true
  labels:
    release: prometheus-operator
```

### Accessing Metrics

```bash
# Port-forward to backend
kubectl port-forward -n slo-scout svc/slo-scout-backend 8000:8000

# Access metrics endpoint
curl http://localhost:8000/metrics
```

### Grafana Dashboards

Access Grafana:

```bash
kubectl port-forward -n slo-scout svc/slo-scout-grafana 3000:80

# Default credentials (change in production!)
# Username: admin
# Password: (from secret)
```

## Network Policies

Network policies are enabled by default in production. Customize:

```yaml
networkPolicy:
  enabled: true
  policyTypes:
    - Ingress
    - Egress

  # Allow specific namespaces
  ingress:
    - from:
      - namespaceSelector:
          matchLabels:
            name: ingress-nginx
```

## Upgrading

### Upgrade to Latest Version

```bash
# Fetch latest charts
helm repo update

# Upgrade with same values
helm upgrade slo-scout ./slo-scout \
  --namespace slo-scout \
  --values values-production.yaml \
  --reuse-values
```

### Database Migrations

Database migrations run automatically via init container in backend deployment. To run manually:

```bash
kubectl exec -it -n slo-scout deployment/slo-scout-backend -- \
  python -m alembic upgrade head
```

## Troubleshooting

### Check Component Status

```bash
# Overall status
kubectl get pods -n slo-scout

# Check logs for backend
kubectl logs -n slo-scout -l app.kubernetes.io/component=backend --tail=100

# Check Flink jobs
kubectl port-forward -n slo-scout svc/slo-scout-flink-jobmanager 8081:8081
# Open http://localhost:8081
```

### Common Issues

#### Backend pods not starting

Check database connection:

```bash
kubectl logs -n slo-scout -l app.kubernetes.io/component=backend -c db-migrate
```

#### Collectors not publishing to Kafka

Check Kafka connectivity:

```bash
kubectl exec -it -n slo-scout deployment/slo-scout-prometheus-collector -- \
  sh -c 'nc -zv kafka 9092'
```

#### Flink jobs failing

Check JobManager logs:

```bash
kubectl logs -n slo-scout -l app.kubernetes.io/component=flink-jobmanager
```

### Debug Mode

Enable debug logging:

```yaml
backend:
  config:
    logLevel: debug

collectors:
  prometheus:
    env:
      - name: LOG_LEVEL
        value: debug
```

## Uninstalling

```bash
# Uninstall release
helm uninstall slo-scout -n slo-scout

# Delete PVCs (if needed)
kubectl delete pvc -n slo-scout --all

# Delete namespace
kubectl delete namespace slo-scout
```

## Resource Requirements

### Minimum Resources (Development)

- 4 CPU cores
- 8 GB RAM
- 50 GB storage

### Recommended Resources (Production)

- 16+ CPU cores
- 32+ GB RAM
- 500 GB storage (varies by retention policy)

### Resource Breakdown (Production)

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|------------|-----------|----------------|--------------|
| Backend (3 replicas) | 750m | 3000m | 1.5Gi | 6Gi |
| Flink TaskManagers (3) | 3000m | 6000m | 6Gi | 12Gi |
| Kafka (3 brokers) | 3000m | 6000m | 6Gi | 12Gi |
| TimescaleDB | 1000m | 2000m | 2Gi | 4Gi |
| Collectors | 600m | 2100m | 1Gi | 4Gi |
| **Total** | ~8.4 cores | ~19 cores | ~17Gi | ~38Gi |

## Performance Tuning

### High Throughput (100k+ logs/min)

```yaml
collectors:
  otlp:
    replicaCount: 10
    autoscaling:
      maxReplicas: 50

flink:
  taskmanager:
    replicaCount: 10
    autoscaling:
      maxReplicas: 50

kafka:
  replicaCount: 5
  logRetentionBytes: 2147483648  # 2GB per partition
```

### Low Latency Queries

```yaml
timescaledb:
  primary:
    resources:
      requests:
        memory: 8Gi
      limits:
        memory: 16Gi
  readReplicas:
    replicaCount: 5

milvus:
  resources:
    requests:
      memory: 8Gi
      cpu: 4000m
```

## Security Best Practices

1. **Use external secrets management** (external-secrets, Vault)
2. **Enable TLS for all components**
3. **Restrict network policies**
4. **Use private image registry**
5. **Enable RBAC with least privilege**
6. **Rotate credentials regularly**
7. **Enable audit logging**
8. **Use Pod Security Standards**

## Contributing

See the main [SLO-Scout repository](https://github.com/slo-scout/slo-scout) for contribution guidelines.

## License

Apache 2.0

## Support

- Documentation: https://docs.slo-scout.io
- Issues: https://github.com/slo-scout/slo-scout/issues
- Slack: https://slo-scout.slack.com
