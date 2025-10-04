# SLO-Scout Deployment Guide

**Version**: 1.0.0
**Last Updated**: 2025-10-04
**Audience**: Platform Engineers, SREs, DevOps Teams

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Deployment Tiers](#deployment-tiers)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Verification](#verification)
7. [Upgrade Procedures](#upgrade-procedures)
8. [Backup and Disaster Recovery](#backup-and-disaster-recovery)
9. [Security Hardening](#security-hardening)
10. [Troubleshooting](#troubleshooting)
11. [Monitoring and Self-Observability](#monitoring-and-self-observability)

---

## Overview

SLO-Scout is a distributed observability platform that automates SLI/SLO discovery and operational artifact generation for production services. The system consists of:

- **Collectors**: Telemetry ingestion agents (Prometheus, OTLP, Logs)
- **Streaming Pipeline**: Apache Flink jobs for data processing and capsule generation
- **Backend API**: FastAPI-based control plane for SLO engine and artifact generation
- **Storage Layer**: Kafka, TimescaleDB, Milvus/pgvector, S3/MinIO
- **Optional UI**: React dashboard for visualization and approval workflows

This guide covers deployment for both **on-premises** and **cloud** environments across three scaling tiers.

---

## Prerequisites

### Kubernetes Cluster Requirements

| Tier | Kubernetes Version | Node Count | Total CPU | Total Memory | Storage |
|------|-------------------|------------|-----------|--------------|---------|
| **Starter** | 1.24+ | 3+ nodes | 8 cores | 16 GB | 100 GB |
| **Professional** | 1.24+ | 5+ nodes | 24 cores | 48 GB | 500 GB |
| **Enterprise** | 1.25+ | 10+ nodes | 64+ cores | 128+ GB | 2+ TB |

**Supported Platforms**:
- On-premises: Rancher, OpenShift, VMware Tanzu, bare-metal Kubernetes
- Cloud: GKE, EKS, AKS, DigitalOcean Kubernetes

### Required Tools

Install the following tools on your deployment machine:

```bash
# Kubernetes CLI
kubectl version --client  # Required: v1.24+

# Helm package manager
helm version  # Required: v3.8+

# Docker (for building custom images)
docker version  # Required: 20.10+

# Git (for GitOps integration)
git version  # Required: 2.30+

# Optional: Prometheus validation tool
promtool version  # Recommended for artifact validation
```

### Infrastructure Dependencies

SLO-Scout requires the following infrastructure components:

1. **Apache Kafka** 3.5+ (KRaft mode preferred)
2. **TimescaleDB** 2.11+ (PostgreSQL 14+ with TimescaleDB extension)
3. **Milvus** 2.3+ OR **pgvector** 0.5+ (for vector storage)
4. **S3-compatible storage** (AWS S3, MinIO, GCS with S3 API)
5. **Prometheus** 2.30+ (optional, for self-monitoring)

**Note**: All infrastructure dependencies can be deployed via Helm charts included in this distribution.

### Network Requirements

- Outbound HTTPS (443) for Helm chart repositories and container images
- Inbound access to Kubernetes API server (6443)
- Internal cluster networking between pods (CNI plugin required)
- Optional: External load balancer for UI/API ingress

### Resource Planning

Estimate resource requirements based on telemetry ingestion rate:

| Metric | Starter | Professional | Enterprise |
|--------|---------|--------------|------------|
| Logs/min | 10,000 | 50,000 | 100,000+ |
| Spans/day | 100,000 | 500,000 | 1,000,000+ |
| Metrics series | 10,000 | 50,000 | 100,000+ |
| Services monitored | 1-10 | 10-100 | 100-1000 |
| Retention (raw) | 7 days | 7 days | 7 days |
| Retention (capsules) | 90 days | 90 days | 90 days |

---

## Deployment Tiers

SLO-Scout offers three pre-configured deployment tiers optimized for different scale and cost requirements.

### Starter Tier

**Use Case**: Small teams, pilot deployments, development/staging environments

**Capacity**:
- 10,000 logs/min
- 100,000 spans/day
- 1-10 services

**Infrastructure**:
- Kafka: 1 partition, 1 replica
- Flink: 2 TaskManagers, 1 slot each
- TimescaleDB: Single instance, 20 GB storage
- Milvus: Standalone mode OR pgvector
- MinIO: Single node, 50 GB storage

**Estimated Monthly Cost** (cloud):
- AWS: ~$250/month (EKS + EC2 t3.medium nodes)
- GCP: ~$230/month (GKE + n1-standard-2 nodes)
- On-prem: ~$500 one-time (hardware amortized)

### Professional Tier

**Use Case**: Production deployments, medium-scale organizations

**Capacity**:
- 50,000 logs/min
- 500,000 spans/day
- 10-100 services

**Infrastructure**:
- Kafka: 3 partitions, 2 replicas, 3 brokers
- Flink: 5 TaskManagers, 2 slots each
- TimescaleDB: Primary + replica, 100 GB storage
- Milvus: Distributed mode (3 query nodes)
- MinIO: 3-node distributed cluster, 250 GB storage

**Estimated Monthly Cost** (cloud):
- AWS: ~$1,200/month (EKS + EC2 m5.xlarge nodes)
- GCP: ~$1,100/month (GKE + n1-standard-4 nodes)
- On-prem: ~$5,000 one-time

### Enterprise Tier

**Use Case**: Large-scale production, multi-tenant SaaS, mission-critical services

**Capacity**:
- 100,000+ logs/min
- 1,000,000+ spans/day
- 100-1000 services

**Infrastructure**:
- Kafka: 10+ partitions, 3 replicas, 5+ brokers
- Flink: Auto-scaling TaskManagers (10-50)
- TimescaleDB: Multi-node with Patroni HA, 1 TB+ storage
- Milvus: Distributed cluster with dedicated query/data nodes
- MinIO: Multi-zone distributed cluster, 2+ TB storage

**Estimated Monthly Cost** (cloud):
- AWS: ~$5,000+/month (EKS + EC2 r5.2xlarge nodes)
- GCP: ~$4,500+/month (GKE + n1-highmem-8 nodes)
- On-prem: ~$30,000+ one-time

**Additional Features**:
- Auto-scaling based on ingestion lag
- Multi-region disaster recovery
- Advanced security (RBAC, audit logs, encryption at rest)
- Dedicated support SLA

---

## Installation

### Step 1: Prepare Kubernetes Cluster

#### Option A: Create Local Cluster (Development)

```bash
# Using kind (Kubernetes in Docker)
cat <<EOF | kind create cluster --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
name: slo-scout
nodes:
- role: control-plane
- role: worker
- role: worker
- role: worker
EOF

kubectl cluster-info --context kind-slo-scout
```

#### Option B: Use Existing Cloud Cluster

```bash
# AWS EKS
eksctl create cluster \
  --name slo-scout-prod \
  --region us-west-2 \
  --nodegroup-name workers \
  --node-type m5.xlarge \
  --nodes 5 \
  --nodes-min 3 \
  --nodes-max 10

# GCP GKE
gcloud container clusters create slo-scout-prod \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --num-nodes 5 \
  --enable-autoscaling \
  --min-nodes 3 \
  --max-nodes 10

# Azure AKS
az aks create \
  --resource-group slo-scout-rg \
  --name slo-scout-prod \
  --node-count 5 \
  --node-vm-size Standard_D4s_v3 \
  --enable-cluster-autoscaler \
  --min-count 3 \
  --max-count 10
```

### Step 2: Create Namespace and Secrets

```bash
# Create dedicated namespace
kubectl create namespace slo-scout

# Set as default namespace (optional)
kubectl config set-context --current --namespace=slo-scout

# Create secrets for external integrations
kubectl create secret generic slo-scout-secrets \
  --from-literal=github-token=ghp_xxxxxxxxxxxxxxxxxxxx \
  --from-literal=gitlab-token=glpat-xxxxxxxxxxxxxxxxxxxx \
  --from-literal=openai-api-key=sk-xxxxxxxxxxxxxxxxxxxx \
  --namespace=slo-scout

# Create S3 credentials (if using AWS S3 or MinIO)
kubectl create secret generic s3-credentials \
  --from-literal=access-key-id=AKIAIOSFODNN7EXAMPLE \
  --from-literal=secret-access-key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  --namespace=slo-scout

# Create database credentials
kubectl create secret generic db-credentials \
  --from-literal=postgres-password=$(openssl rand -base64 32) \
  --namespace=slo-scout
```

### Step 3: Add Helm Repositories

```bash
# Add Bitnami charts (Kafka, PostgreSQL)
helm repo add bitnami https://charts.bitnami.com/bitnami

# Add TimescaleDB chart
helm repo add timescale https://charts.timescale.com

# Add Milvus chart
helm repo add milvus https://milvus-io.github.io/milvus-helm/

# Add SLO-Scout chart repository (replace with actual repo)
helm repo add slo-scout https://slo-scout.github.io/helm-charts

# Update repositories
helm repo update
```

### Step 4: Deploy Infrastructure Dependencies

#### Deploy Kafka

```bash
# Starter/Professional tier
helm install kafka bitnami/kafka \
  --namespace slo-scout \
  --set replicaCount=3 \
  --set persistence.size=50Gi \
  --set logRetentionHours=168 \
  --set autoCreateTopicsEnable=false \
  --set deleteTopicEnable=true \
  --set numPartitions=3 \
  --set defaultReplicationFactor=2 \
  --set offsetsTopicReplicationFactor=2 \
  --set transactionStateLogReplicationFactor=2 \
  --set zookeeper.enabled=true \
  --version 26.8.3

# Enterprise tier (KRaft mode, no ZooKeeper)
helm install kafka bitnami/kafka \
  --namespace slo-scout \
  --set replicaCount=5 \
  --set persistence.size=200Gi \
  --set kraft.enabled=true \
  --set numPartitions=10 \
  --set defaultReplicationFactor=3 \
  --set metrics.kafka.enabled=true \
  --set metrics.jmx.enabled=true \
  --version 26.8.3

# Verify Kafka deployment
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=kafka -n slo-scout --timeout=300s
```

#### Deploy TimescaleDB

```bash
# Starter tier (single instance)
helm install timescaledb timescale/timescaledb-single \
  --namespace slo-scout \
  --set persistentVolumes.data.size=50Gi \
  --set resources.requests.memory=4Gi \
  --set resources.requests.cpu=2000m \
  --set secretNames.credentials=db-credentials \
  --version 0.32.0

# Professional/Enterprise tier (HA with replicas)
helm install timescaledb timescale/timescaledb-single \
  --namespace slo-scout \
  --set replicaCount=2 \
  --set persistentVolumes.data.size=200Gi \
  --set resources.requests.memory=16Gi \
  --set resources.requests.cpu=4000m \
  --set backup.enabled=true \
  --set backup.schedule="0 2 * * *" \
  --set secretNames.credentials=db-credentials \
  --version 0.32.0

# Verify TimescaleDB deployment
kubectl wait --for=condition=ready pod -l app=timescaledb -n slo-scout --timeout=300s

# Initialize database schema
kubectl exec -it timescaledb-0 -n slo-scout -- psql -U postgres -c "CREATE DATABASE slo_scout;"
kubectl exec -it timescaledb-0 -n slo-scout -- psql -U postgres -d slo_scout -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
kubectl exec -it timescaledb-0 -n slo-scout -- psql -U postgres -d slo_scout -c "CREATE EXTENSION IF NOT EXISTS pgvector;"
```

#### Deploy Vector Database (Milvus or pgvector)

**Option A: Milvus (Professional/Enterprise tier, >1M vectors)**

```bash
# Milvus standalone mode (Professional tier)
helm install milvus milvus/milvus \
  --namespace slo-scout \
  --set cluster.enabled=false \
  --set standalone.disk.enabled=true \
  --set standalone.disk.size=100Gi \
  --set standalone.resources.requests.memory=8Gi \
  --set standalone.resources.requests.cpu=2000m \
  --version 4.1.11

# Milvus distributed cluster (Enterprise tier)
helm install milvus milvus/milvus \
  --namespace slo-scout \
  --set cluster.enabled=true \
  --set queryNode.replicas=3 \
  --set dataNode.replicas=2 \
  --set indexNode.replicas=1 \
  --set proxy.replicas=2 \
  --set minio.mode=distributed \
  --set minio.statefulset.replicaCount=4 \
  --set etcd.replicaCount=3 \
  --version 4.1.11

# Verify Milvus deployment
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=milvus -n slo-scout --timeout=600s
```

**Option B: pgvector (Starter tier, <1M vectors)**

Already installed via TimescaleDB extension. No additional deployment needed.

#### Deploy MinIO (S3-compatible storage)

```bash
# Starter tier (single instance)
helm install minio bitnami/minio \
  --namespace slo-scout \
  --set mode=standalone \
  --set persistence.size=100Gi \
  --set auth.rootUser=admin \
  --set auth.rootPassword=$(openssl rand -base64 32) \
  --version 12.12.3

# Professional/Enterprise tier (distributed cluster)
helm install minio bitnami/minio \
  --namespace slo-scout \
  --set mode=distributed \
  --set statefulset.replicaCount=4 \
  --set persistence.size=500Gi \
  --set auth.rootUser=admin \
  --set auth.rootPassword=$(openssl rand -base64 32) \
  --version 12.12.3

# Verify MinIO deployment
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=minio -n slo-scout --timeout=300s

# Create buckets for SLO-Scout
kubectl run minio-client --rm -it --image=minio/mc --restart=Never -n slo-scout -- bash -c "
  mc alias set myminio http://minio:9000 admin <password>
  mc mb myminio/raw-telemetry-blobs
  mc mb myminio/capsule-samples
  mc policy set download myminio/capsule-samples
"
```

### Step 5: Deploy SLO-Scout Components

#### Create Configuration

```bash
# Create ConfigMap with deployment-specific settings
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: slo-scout-config
  namespace: slo-scout
data:
  KAFKA_BOOTSTRAP_SERVERS: "kafka:9092"
  TIMESCALEDB_HOST: "timescaledb"
  TIMESCALEDB_PORT: "5432"
  TIMESCALEDB_DATABASE: "slo_scout"
  MILVUS_HOST: "milvus"
  MILVUS_PORT: "19530"
  MINIO_ENDPOINT: "minio:9000"
  MINIO_BUCKET_TELEMETRY: "raw-telemetry-blobs"
  MINIO_BUCKET_CAPSULES: "capsule-samples"
  EMBEDDING_MODEL: "all-MiniLM-L6-v2"
  DEPLOYMENT_TIER: "professional"
  LOG_LEVEL: "info"
  PROMETHEUS_URL: "http://prometheus:9090"
EOF
```

#### Install SLO-Scout Helm Chart

```bash
# Starter tier
helm install slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --set tier=starter \
  --set collectors.prometheus.enabled=true \
  --set collectors.otlp.enabled=true \
  --set collectors.logs.enabled=true \
  --set flink.taskmanagers.replicas=2 \
  --set backend.replicas=2 \
  --set ui.enabled=true \
  --set ingress.enabled=true \
  --set ingress.hostname=slo-scout.example.com \
  --values values-starter.yaml

# Professional tier
helm install slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --set tier=professional \
  --set collectors.prometheus.replicas=3 \
  --set collectors.otlp.replicas=3 \
  --set flink.taskmanagers.replicas=5 \
  --set backend.replicas=3 \
  --set backend.autoscaling.enabled=true \
  --set backend.autoscaling.minReplicas=3 \
  --set backend.autoscaling.maxReplicas=10 \
  --values values-professional.yaml

# Enterprise tier
helm install slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --set tier=enterprise \
  --set collectors.prometheus.replicas=5 \
  --set flink.taskmanagers.replicas=10 \
  --set flink.autoscaling.enabled=true \
  --set backend.replicas=5 \
  --set backend.autoscaling.enabled=true \
  --set backend.autoscaling.minReplicas=5 \
  --set backend.autoscaling.maxReplicas=50 \
  --set ui.replicas=3 \
  --set multiRegion.enabled=true \
  --values values-enterprise.yaml
```

#### Alternative: Install from Local Charts

If developing or customizing the Helm chart:

```bash
# Clone repository
git clone https://github.com/slo-scout/slo-scout.git
cd slo-scout/infrastructure/helm/slo-scout

# Install from local directory
helm install slo-scout . \
  --namespace slo-scout \
  --values values-professional.yaml \
  --debug

# Or package and install
helm package .
helm install slo-scout ./slo-scout-1.0.0.tgz --namespace slo-scout
```

---

## Configuration

### Helm Chart Values Reference

The SLO-Scout Helm chart supports extensive customization via `values.yaml`. Key configuration sections:

#### Global Settings

```yaml
global:
  tier: professional  # starter | professional | enterprise
  environment: production  # development | staging | production
  namespace: slo-scout
  storageClass: standard  # gp2, standard-rwo, etc.
  imagePullSecrets: []
  imageRegistry: docker.io/slo-scout
  imageTag: "1.0.0"
```

#### Collectors Configuration

```yaml
collectors:
  prometheus:
    enabled: true
    replicas: 3
    image: prometheus-collector
    imageTag: "1.0.0"
    resources:
      requests:
        memory: 256Mi
        cpu: 200m
      limits:
        memory: 512Mi
        cpu: 500m
    scrapeInterval: 30s
    remoteReadUrl: "http://prometheus:9090"

  otlp:
    enabled: true
    replicas: 3
    image: otlp-collector
    grpcPort: 4317
    httpPort: 4318
    resources:
      requests:
        memory: 512Mi
        cpu: 500m
      limits:
        memory: 1Gi
        cpu: 1000m

  logs:
    enabled: true
    replicas: 3
    image: log-collector
    daemonset: false  # Set true for per-node collection
    fluentbitPort: 24224
    resources:
      requests:
        memory: 256Mi
        cpu: 200m
```

#### Flink Jobs Configuration

```yaml
flink:
  jobmanager:
    replicas: 1
    resources:
      requests:
        memory: 2Gi
        cpu: 1000m
      limits:
        memory: 4Gi
        cpu: 2000m
    heap: 1.5G

  taskmanagers:
    replicas: 5
    slots: 2
    resources:
      requests:
        memory: 4Gi
        cpu: 2000m
      limits:
        memory: 8Gi
        cpu: 4000m
    heap: 3G

  autoscaling:
    enabled: true  # Enterprise tier only
    minReplicas: 5
    maxReplicas: 50
    targetCPUUtilizationPercentage: 70

  checkpointing:
    interval: 300s  # 5 minutes
    backend: rocksdb  # rocksdb | filesystem
    stateBackend: s3  # s3 | gcs | local
    incrementalCheckpoints: true

  jobs:
    fingerprinting:
      parallelism: 10
      windowSize: 1h
      allowedLateness: 10m
    embedding:
      parallelism: 5
      batchSize: 100
```

#### Backend API Configuration

```yaml
backend:
  replicas: 3
  image: backend-api
  imageTag: "1.0.0"

  resources:
    requests:
      memory: 1Gi
      cpu: 500m
    limits:
      memory: 2Gi
      cpu: 1000m

  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70

  config:
    logLevel: info
    workers: 4
    maxConnections: 100
    requestTimeout: 60s

  embeddings:
    provider: local  # local | openai | custom
    model: all-MiniLM-L6-v2
    dimensions: 384
    batchSize: 32

  llm:
    provider: openai  # openai | anthropic | local
    model: gpt-4
    maxTokens: 4096
    temperature: 0.2

  policyGuard:
    enabled: true
    blastRadiusThreshold:
      servicesPercentage: 10
      servicesAbsolute: 5
      estimatedCost: 100

  gitops:
    provider: github  # github | gitlab
    defaultBranch: main
    commitMessageFormat: "feat(slo): {message}"
```

#### UI Configuration

```yaml
ui:
  enabled: true
  replicas: 2
  image: ui-dashboard
  imageTag: "1.0.0"

  resources:
    requests:
      memory: 256Mi
      cpu: 100m
    limits:
      memory: 512Mi
      cpu: 500m

  config:
    apiBaseUrl: http://backend-api:8000
    auth:
      enabled: true
      provider: oidc  # oidc | oauth2 | basic
      issuer: https://auth.example.com
      clientId: slo-scout
```

#### Ingress Configuration

```yaml
ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
  hosts:
    - host: slo-scout.example.com
      paths:
        - path: /
          pathType: Prefix
          service: ui
        - path: /api
          pathType: Prefix
          service: backend-api
  tls:
    - secretName: slo-scout-tls
      hosts:
        - slo-scout.example.com
```

#### Persistence Configuration

```yaml
persistence:
  kafka:
    storageClass: standard
    size: 50Gi
  timescaledb:
    storageClass: standard
    size: 200Gi
  milvus:
    storageClass: standard
    size: 100Gi
  minio:
    storageClass: standard
    size: 500Gi
  flink:
    checkpoints:
      storageClass: standard
      size: 50Gi
```

### Environment Variables

Key environment variables configurable via ConfigMap or secrets:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka broker addresses | `kafka:9092` | Yes |
| `TIMESCALEDB_HOST` | TimescaleDB hostname | `timescaledb` | Yes |
| `TIMESCALEDB_PORT` | TimescaleDB port | `5432` | Yes |
| `TIMESCALEDB_USER` | Database username | `postgres` | Yes |
| `TIMESCALEDB_PASSWORD` | Database password (from secret) | - | Yes |
| `TIMESCALEDB_DATABASE` | Database name | `slo_scout` | Yes |
| `MILVUS_HOST` | Milvus hostname | `milvus` | Yes (if using Milvus) |
| `MILVUS_PORT` | Milvus gRPC port | `19530` | Yes (if using Milvus) |
| `MINIO_ENDPOINT` | MinIO/S3 endpoint | `minio:9000` | Yes |
| `MINIO_ACCESS_KEY` | S3 access key (from secret) | - | Yes |
| `MINIO_SECRET_KEY` | S3 secret key (from secret) | - | Yes |
| `EMBEDDING_MODEL` | Embedding model name | `all-MiniLM-L6-v2` | No |
| `LLM_PROVIDER` | LLM provider | `openai` | No |
| `OPENAI_API_KEY` | OpenAI API key (from secret) | - | No |
| `GITHUB_TOKEN` | GitHub token for PRs (from secret) | - | No |
| `GITLAB_TOKEN` | GitLab token for MRs (from secret) | - | No |
| `LOG_LEVEL` | Logging level | `info` | No |
| `DEPLOYMENT_TIER` | Deployment tier | `professional` | No |

### Secrets Management

#### Using Kubernetes Secrets (Default)

```bash
# Create secrets manually
kubectl create secret generic slo-scout-secrets \
  --from-literal=timescaledb-password=$(openssl rand -base64 32) \
  --from-literal=minio-access-key=AKIAIOSFODNN7EXAMPLE \
  --from-literal=minio-secret-key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY \
  --from-literal=github-token=ghp_xxxxxxxxxxxxxxxxxxxx \
  --from-literal=openai-api-key=sk-xxxxxxxxxxxxxxxxxxxx \
  --namespace=slo-scout
```

#### Using External Secrets Operator

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: slo-scout-secrets
  namespace: slo-scout
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: SecretStore
  target:
    name: slo-scout-secrets
    creationPolicy: Owner
  data:
    - secretKey: timescaledb-password
      remoteRef:
        key: slo-scout/timescaledb
        property: password
    - secretKey: github-token
      remoteRef:
        key: slo-scout/github
        property: token
```

#### Using HashiCorp Vault

```yaml
apiVersion: secrets.hashicorp.com/v1beta1
kind: VaultStaticSecret
metadata:
  name: slo-scout-secrets
  namespace: slo-scout
spec:
  type: kv-v2
  mount: slo-scout
  path: credentials
  destination:
    name: slo-scout-secrets
    create: true
  refreshAfter: 1h
```

### Scaling Configuration

#### Horizontal Pod Autoscaling (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-api-hpa
  namespace: slo-scout
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "1000"
```

#### Flink Auto-Scaling (Enterprise Tier)

```yaml
apiVersion: flink.apache.org/v1beta1
kind: FlinkDeployment
metadata:
  name: fingerprinting-job
  namespace: slo-scout
spec:
  flinkVersion: v1_18
  mode: native
  job:
    jarURI: s3://slo-scout/jobs/fingerprinting-job.jar
    parallelism: 10
    upgradeMode: savepoint
  taskManager:
    replicas: 5
  podTemplate:
    spec:
      containers:
        - name: flink-main-container
          resources:
            requests:
              memory: "4096Mi"
              cpu: 2
            limits:
              memory: "8192Mi"
              cpu: 4
```

---

## Verification

### Post-Installation Checks

After deploying SLO-Scout, verify all components are healthy:

#### 1. Check Pod Status

```bash
# All pods should be Running
kubectl get pods -n slo-scout

# Expected output (Professional tier):
# NAME                                   READY   STATUS    RESTARTS   AGE
# kafka-0                                1/1     Running   0          5m
# kafka-1                                1/1     Running   0          5m
# kafka-2                                1/1     Running   0          5m
# timescaledb-0                          1/1     Running   0          5m
# milvus-standalone-0                    1/1     Running   0          4m
# minio-0                                1/1     Running   0          4m
# prometheus-collector-7d8f9b4c8-abc12  1/1     Running   0          3m
# prometheus-collector-7d8f9b4c8-def34  1/1     Running   0          3m
# prometheus-collector-7d8f9b4c8-ghi56  1/1     Running   0          3m
# otlp-collector-6c5d8a3b7-jkl78        1/1     Running   0          3m
# flink-jobmanager-5f7c9d2e4-mno90      1/1     Running   0          3m
# flink-taskmanager-8a6b5c3d9-pqr12     1/1     Running   0          3m
# flink-taskmanager-8a6b5c3d9-stu34     1/1     Running   0          3m
# backend-api-9e8d7c6b5-vwx56           1/1     Running   0          2m
# backend-api-9e8d7c6b5-yz012           1/1     Running   0          2m
# ui-dashboard-4c3b2a1d0-abc78          1/1     Running   0          2m
```

#### 2. Verify Services

```bash
# Check service endpoints
kubectl get svc -n slo-scout

# Test internal connectivity
kubectl run curl-test --rm -it --image=curlimages/curl --restart=Never -n slo-scout -- \
  curl -s http://backend-api:8000/health

# Expected: {"status":"healthy","version":"1.0.0"}
```

#### 3. Check Kafka Topics

```bash
# List created topics
kubectl exec -it kafka-0 -n slo-scout -- \
  kafka-topics.sh --bootstrap-server localhost:9092 --list

# Expected topics:
# raw-telemetry
# capsule-events
# capsule-embeddings
# raw-telemetry-dlq
```

#### 4. Verify Database Initialization

```bash
# Check TimescaleDB tables
kubectl exec -it timescaledb-0 -n slo-scout -- \
  psql -U postgres -d slo_scout -c "\dt"

# Expected tables:
# service
# user_journey
# sli
# slo
# capsule
# artifact
# policy
# evidence_pointer
# instrumentation_recommendation

# Verify TimescaleDB extension
kubectl exec -it timescaledb-0 -n slo-scout -- \
  psql -U postgres -d slo_scout -c "SELECT extname, extversion FROM pg_extension;"

# Expected: timescaledb, pgvector
```

#### 5. Test Milvus Connection

```bash
# Port-forward Milvus service
kubectl port-forward svc/milvus 19530:19530 -n slo-scout &

# Test connection (requires pymilvus)
python3 <<EOF
from pymilvus import connections, utility
connections.connect(host='localhost', port='19530')
print(f"Milvus version: {utility.get_server_version()}")
connections.disconnect()
EOF

# Expected: Milvus version: v2.3.x
```

#### 6. Verify MinIO Buckets

```bash
# Port-forward MinIO console
kubectl port-forward svc/minio 9001:9001 -n slo-scout &

# Access console at http://localhost:9001
# Or use CLI:
kubectl run minio-client --rm -it --image=minio/mc --restart=Never -n slo-scout -- bash -c "
  mc alias set myminio http://minio:9000 admin <password>
  mc ls myminio
"

# Expected buckets:
# raw-telemetry-blobs
# capsule-samples
```

#### 7. Test Flink Job Submission

```bash
# Check Flink JobManager UI
kubectl port-forward svc/flink-jobmanager 8081:8081 -n slo-scout &

# Access UI at http://localhost:8081
# Or use CLI:
kubectl exec -it flink-jobmanager-xxxxx -n slo-scout -- \
  flink list

# Expected: fingerprinting-job (RUNNING), embedding-pipeline-job (RUNNING)
```

#### 8. End-to-End Smoke Test

```bash
# Send test telemetry event
kubectl run test-producer --rm -it --image=curlimages/curl --restart=Never -n slo-scout -- \
  curl -X POST http://prometheus-collector:8080/ingest/logs \
    -H "Content-Type: application/json" \
    -d '{
      "service": "test-service",
      "message": "User 12345 logged in successfully",
      "severity": "INFO",
      "timestamp": "2025-10-04T12:00:00Z"
    }'

# Wait 30 seconds for processing

# Query backend API
kubectl run api-test --rm -it --image=curlimages/curl --restart=Never -n slo-scout -- \
  curl -s http://backend-api:8000/api/v1/services

# Expected: JSON response with services list
```

#### 9. Check Self-Observability Metrics

```bash
# Access Prometheus metrics endpoint
kubectl port-forward svc/backend-api 8000:8000 -n slo-scout &
curl http://localhost:8000/metrics

# Expected metrics:
# slo_scout_ingest_lag_seconds
# slo_scout_embedding_queue_length
# slo_scout_vector_query_latency_seconds
# slo_scout_llm_calls_total
```

#### 10. Verify Ingress (if enabled)

```bash
# Check ingress status
kubectl get ingress -n slo-scout

# Test external access
curl -k https://slo-scout.example.com/api/v1/health

# Expected: {"status":"healthy"}
```

### Health Check Dashboard

Create a monitoring dashboard to track SLO-Scout health:

```bash
# Apply Grafana dashboard
kubectl apply -f infrastructure/grafana/slo-scout-dashboard.json

# Access Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring &

# Login and navigate to "SLO-Scout Health" dashboard
```

---

## Upgrade Procedures

### Pre-Upgrade Checklist

Before upgrading SLO-Scout:

1. **Backup all data** (see Backup section below)
2. **Review release notes** for breaking changes
3. **Test upgrade in staging environment**
4. **Schedule maintenance window** (recommended: 1-2 hours)
5. **Notify users** of potential downtime

### Rolling Upgrade (Zero-Downtime)

For Professional and Enterprise tiers:

```bash
# 1. Update Helm repository
helm repo update slo-scout

# 2. Review changes
helm diff upgrade slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --values values-professional.yaml

# 3. Perform rolling upgrade
helm upgrade slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --values values-professional.yaml \
  --version 1.1.0 \
  --wait \
  --timeout 600s

# 4. Monitor rollout
kubectl rollout status deployment/backend-api -n slo-scout
kubectl rollout status deployment/prometheus-collector -n slo-scout

# 5. Verify health
kubectl run api-test --rm -it --image=curlimages/curl --restart=Never -n slo-scout -- \
  curl -s http://backend-api:8000/health
```

### Database Schema Migrations

SLO-Scout uses Flyway for database migrations:

```bash
# Migrations are applied automatically during backend startup
# To run migrations manually:

kubectl exec -it backend-api-xxxxx -n slo-scout -- \
  python -m backend.migrations.migrate

# Check migration status
kubectl exec -it timescaledb-0 -n slo-scout -- \
  psql -U postgres -d slo_scout -c "SELECT * FROM flyway_schema_history ORDER BY installed_rank DESC LIMIT 5;"
```

### Flink Job Upgrades

Flink jobs require savepoint-based upgrades to preserve state:

```bash
# 1. Trigger savepoint
kubectl exec -it flink-jobmanager-xxxxx -n slo-scout -- \
  flink savepoint <job-id> s3://slo-scout/savepoints/

# 2. Cancel existing job
kubectl exec -it flink-jobmanager-xxxxx -n slo-scout -- \
  flink cancel <job-id>

# 3. Deploy new job version
helm upgrade slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --set flink.jobs.fingerprinting.restoreFromSavepoint=s3://slo-scout/savepoints/savepoint-xxxxx

# 4. Verify job restored from savepoint
kubectl logs -n slo-scout flink-jobmanager-xxxxx | grep "restored from savepoint"
```

### Rollback Procedure

If upgrade fails:

```bash
# 1. Rollback Helm release
helm rollback slo-scout 0 --namespace slo-scout --wait

# 2. Verify rollback
helm history slo-scout --namespace slo-scout

# 3. Check pod status
kubectl get pods -n slo-scout

# 4. Restore database backup (if schema migration failed)
# See "Restore from Backup" section below
```

### Version Compatibility Matrix

| SLO-Scout Version | Kubernetes | Kafka | TimescaleDB | Milvus | Flink |
|-------------------|------------|-------|-------------|--------|-------|
| 1.0.x | 1.24-1.28 | 3.5-3.6 | 2.11+ | 2.3+ | 1.18 |
| 1.1.x | 1.25-1.29 | 3.6-3.7 | 2.12+ | 2.4+ | 1.18-1.19 |
| 1.2.x | 1.26-1.30 | 3.7+ | 2.13+ | 2.4+ | 1.19 |

---

## Backup and Disaster Recovery

### Backup Strategy

SLO-Scout requires backing up multiple data stores:

#### 1. TimescaleDB Backups

**Automated Backups** (via Helm chart):

```yaml
# values.yaml
timescaledb:
  backup:
    enabled: true
    schedule: "0 2 * * *"  # Daily at 2 AM
    retention: 7  # Keep 7 daily backups
    storageClass: standard
    size: 100Gi
```

**Manual Backups**:

```bash
# Full database dump
kubectl exec -it timescaledb-0 -n slo-scout -- \
  pg_dump -U postgres -d slo_scout -F c -f /tmp/backup-$(date +%Y%m%d).dump

# Copy backup to local machine
kubectl cp slo-scout/timescaledb-0:/tmp/backup-20251004.dump ./backup-20251004.dump

# Upload to S3 for long-term storage
aws s3 cp ./backup-20251004.dump s3://slo-scout-backups/timescaledb/
```

**Point-in-Time Recovery (PITR)** (Enterprise tier):

```yaml
# Enable WAL archiving
timescaledb:
  replication:
    enabled: true
    archiveMode: on
    archiveCommand: "test ! -f /wal_archive/%f && cp %p /wal_archive/%f"
  backup:
    pitr:
      enabled: true
      walStorage: s3://slo-scout-backups/wal-archive/
```

#### 2. Kafka Backups

**Mirror Maker 2** (for disaster recovery):

```bash
# Deploy MirrorMaker 2 to replicate topics to backup cluster
helm install kafka-mirror bitnami/kafka \
  --set mirrorMaker.enabled=true \
  --set mirrorMaker.source.bootstrapServers="kafka:9092" \
  --set mirrorMaker.target.bootstrapServers="kafka-backup:9092" \
  --namespace slo-scout
```

**Topic Snapshots** (manual):

```bash
# Export topic data
kubectl exec -it kafka-0 -n slo-scout -- \
  kafka-console-consumer.sh \
    --bootstrap-server localhost:9092 \
    --topic capsule-events \
    --from-beginning \
    --max-messages 1000000 > capsule-events-snapshot.json
```

#### 3. Milvus Backups

```bash
# Milvus backup using built-in backup API
kubectl exec -it milvus-standalone-0 -n slo-scout -- \
  /opt/milvus/bin/milvus-backup create \
    --collection capsules \
    --backup-name backup-20251004

# Export backup to S3
kubectl exec -it milvus-standalone-0 -n slo-scout -- \
  aws s3 sync /milvus/backup/ s3://slo-scout-backups/milvus/
```

#### 4. MinIO Backups

MinIO supports object replication:

```bash
# Configure bucket replication to backup bucket
mc admin bucket remote add myminio/capsule-samples \
  https://backup-minio.example.com/capsule-samples-backup \
  --service replication \
  --region us-west-2

mc replicate add myminio/capsule-samples \
  --remote-bucket capsule-samples-backup \
  --replicate "delete,delete-marker,existing-objects"
```

### Disaster Recovery Procedures

#### Scenario 1: Database Corruption

```bash
# 1. Stop backend services to prevent writes
kubectl scale deployment backend-api --replicas=0 -n slo-scout

# 2. Restore from latest backup
kubectl exec -it timescaledb-0 -n slo-scout -- bash -c "
  dropdb -U postgres slo_scout
  createdb -U postgres slo_scout
  pg_restore -U postgres -d slo_scout /backups/backup-20251004.dump
"

# 3. Verify restoration
kubectl exec -it timescaledb-0 -n slo-scout -- \
  psql -U postgres -d slo_scout -c "SELECT COUNT(*) FROM sli;"

# 4. Restart backend services
kubectl scale deployment backend-api --replicas=3 -n slo-scout
```

#### Scenario 2: Complete Cluster Failure

**Prerequisites**: Backups stored in external S3 bucket, disaster recovery cluster ready

```bash
# 1. Deploy SLO-Scout to DR cluster
helm install slo-scout slo-scout/slo-scout \
  --namespace slo-scout \
  --values values-professional.yaml \
  --set recovery.enabled=true \
  --set recovery.backupBucket=s3://slo-scout-backups/

# 2. Restore databases (automated by init containers)
# TimescaleDB init container downloads latest backup from S3

# 3. Restore Kafka topics from MirrorMaker target

# 4. Update DNS to point to DR cluster

# 5. Verify all services healthy
kubectl get pods -n slo-scout
```

#### Scenario 3: Data Loss in Specific Service

```bash
# Restore specific service data from backup
kubectl exec -it timescaledb-0 -n slo-scout -- \
  psql -U postgres -d slo_scout -c "
    DELETE FROM sli WHERE service_id IN (SELECT id FROM service WHERE name = 'payments-api');
    DELETE FROM slo WHERE sli_id NOT IN (SELECT id FROM sli);
  "

# Re-run analysis for that service
curl -X POST http://backend-api:8000/api/v1/analyze \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"service_name": "payments-api", "environment": "prod"}'
```

### Backup Retention Policy

Recommended retention schedules:

| Backup Type | Frequency | Retention | Storage Tier |
|-------------|-----------|-----------|--------------|
| TimescaleDB daily | Daily 2 AM | 30 days | S3 Standard |
| TimescaleDB weekly | Sunday 2 AM | 12 weeks | S3 Standard-IA |
| TimescaleDB monthly | 1st of month | 12 months | S3 Glacier |
| Kafka snapshots | Daily | 7 days | S3 Standard |
| Milvus backups | Weekly | 4 weeks | S3 Standard |
| MinIO replication | Real-time | Indefinite | S3 Standard |
| Configuration YAML | On change | Version control | Git |

### Backup Testing

Schedule quarterly disaster recovery drills:

```bash
# Automated DR test script
cat <<'EOF' > test-dr.sh
#!/bin/bash
set -e

echo "Starting DR test..."

# 1. Create test namespace
kubectl create namespace slo-scout-dr-test

# 2. Deploy from backup
helm install slo-scout-test slo-scout/slo-scout \
  --namespace slo-scout-dr-test \
  --set recovery.enabled=true \
  --set recovery.backupBucket=s3://slo-scout-backups/

# 3. Wait for all pods ready
kubectl wait --for=condition=ready pod --all -n slo-scout-dr-test --timeout=600s

# 4. Run smoke tests
kubectl run api-test --rm -it --image=curlimages/curl --restart=Never -n slo-scout-dr-test -- \
  curl -s http://backend-api:8000/health

# 5. Verify data restored
EXPECTED_SLI_COUNT=100  # Adjust based on your environment
ACTUAL_SLI_COUNT=$(kubectl exec -it timescaledb-0 -n slo-scout-dr-test -- \
  psql -U postgres -d slo_scout -t -c "SELECT COUNT(*) FROM sli;")

if [ "$ACTUAL_SLI_COUNT" -ge "$EXPECTED_SLI_COUNT" ]; then
  echo "DR test PASSED"
else
  echo "DR test FAILED: Expected >=$EXPECTED_SLI_COUNT SLIs, got $ACTUAL_SLI_COUNT"
  exit 1
fi

# 6. Cleanup
kubectl delete namespace slo-scout-dr-test

echo "DR test completed successfully"
EOF

chmod +x test-dr.sh
./test-dr.sh
```

---

## Security Hardening

### Network Policies

Implement least-privilege network access:

```yaml
# Deny all traffic by default
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: slo-scout
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress

---
# Allow backend to access databases
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: backend-to-databases
  namespace: slo-scout
spec:
  podSelector:
    matchLabels:
      app: backend-api
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: timescaledb
      ports:
        - protocol: TCP
          port: 5432
    - to:
        - podSelector:
            matchLabels:
              app: milvus
      ports:
        - protocol: TCP
          port: 19530
    - to:
        - podSelector:
            matchLabels:
              app: kafka
      ports:
        - protocol: TCP
          port: 9092

---
# Allow collectors to send to Kafka
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: collectors-to-kafka
  namespace: slo-scout
spec:
  podSelector:
    matchLabels:
      component: collector
  policyTypes:
    - Egress
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: kafka
      ports:
        - protocol: TCP
          port: 9092

---
# Allow ingress to UI from external
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: external-to-ui
  namespace: slo-scout
spec:
  podSelector:
    matchLabels:
      app: ui-dashboard
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 3000
```

### Pod Security Standards

Apply Pod Security Standards (PSS):

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: slo-scout
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/audit: restricted
    pod-security.kubernetes.io/warn: restricted
```

Update pod security contexts:

```yaml
# values.yaml
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1000
  fsGroup: 1000
  seccompProfile:
    type: RuntimeDefault

containerSecurityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  runAsNonRoot: true
  runAsUser: 1000
  capabilities:
    drop:
      - ALL
```

### RBAC Configuration

Create minimal RBAC permissions:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: slo-scout-backend
  namespace: slo-scout

---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: slo-scout-backend-role
  namespace: slo-scout
rules:
  - apiGroups: [""]
    resources: ["configmaps", "secrets"]
    verbs: ["get", "list"]
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["get", "list"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: slo-scout-backend-binding
  namespace: slo-scout
subjects:
  - kind: ServiceAccount
    name: slo-scout-backend
    namespace: slo-scout
roleRef:
  kind: Role
  name: slo-scout-backend-role
  apiGroup: rbac.authorization.k8s.io
```

### TLS/mTLS Configuration

Enable TLS for all inter-service communication:

```yaml
# values.yaml
tls:
  enabled: true
  certManager:
    enabled: true
    issuer: letsencrypt-prod
  kafka:
    enabled: true
    protocol: SSL
  timescaledb:
    sslMode: require
  milvus:
    tls: true
```

Generate certificates using cert-manager:

```yaml
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: slo-scout-tls
  namespace: slo-scout
spec:
  secretName: slo-scout-tls
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - slo-scout.example.com
    - "*.slo-scout.svc.cluster.local"
```

### Secrets Encryption at Rest

Enable etcd encryption (cluster-level):

```yaml
apiVersion: apiserver.config.k8s.io/v1
kind: EncryptionConfiguration
resources:
  - resources:
      - secrets
    providers:
      - aescbc:
          keys:
            - name: key1
              secret: <base64-encoded-32-byte-key>
      - identity: {}
```

### Image Security

Scan container images for vulnerabilities:

```bash
# Add to CI/CD pipeline
trivy image slo-scout/backend-api:1.0.0 --severity HIGH,CRITICAL

# Use signed images
cosign verify --key cosign.pub slo-scout/backend-api:1.0.0
```

### Audit Logging

Enable Kubernetes audit logs:

```yaml
# values.yaml
auditLog:
  enabled: true
  logLevel: RequestResponse
  backend: webhook
  webhookConfig:
    url: https://audit-collector.example.com/logs
```

Application-level audit logging:

```yaml
backend:
  config:
    auditLog:
      enabled: true
      events:
        - sli_approval
        - slo_creation
        - artifact_deployment
        - policy_violation
      destinations:
        - type: elasticsearch
          url: https://elasticsearch:9200
          index: slo-scout-audit
```

### Data Encryption

Encrypt sensitive data in TimescaleDB:

```sql
-- Enable pgcrypto extension
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Encrypt sensitive columns
ALTER TABLE artifact ADD COLUMN content_encrypted BYTEA;
UPDATE artifact SET content_encrypted = pgp_sym_encrypt(content, current_setting('app.encryption_key'));
ALTER TABLE artifact DROP COLUMN content;
```

### PII Redaction Validation

Verify PII redaction is working:

```bash
# Run automated PII detection tests
kubectl exec -it backend-api-xxxxx -n slo-scout -- \
  python -m backend.tests.security.test_pii_redaction

# Expected: All tests pass, no PII in output
```

---

## Troubleshooting

### Common Issues and Solutions

#### Issue 1: Pods in CrashLoopBackOff

**Symptoms**:
```bash
kubectl get pods -n slo-scout
# NAME                        READY   STATUS             RESTARTS
# backend-api-xxxxx           0/1     CrashLoopBackOff   5
```

**Diagnosis**:
```bash
# Check pod logs
kubectl logs backend-api-xxxxx -n slo-scout --previous

# Common errors:
# - "Connection refused" to database/Kafka
# - "Secret not found"
# - "Out of memory"
```

**Solutions**:

**Connection Issues**:
```bash
# Verify service DNS resolution
kubectl run dns-test --rm -it --image=busybox --restart=Never -n slo-scout -- \
  nslookup timescaledb.slo-scout.svc.cluster.local

# Check service endpoints
kubectl get endpoints timescaledb -n slo-scout

# Verify network policies allow traffic
kubectl describe networkpolicy -n slo-scout
```

**Missing Secrets**:
```bash
# Verify secrets exist
kubectl get secrets -n slo-scout | grep slo-scout-secrets

# Recreate secret if missing
kubectl create secret generic slo-scout-secrets \
  --from-literal=timescaledb-password=<password> \
  --namespace=slo-scout
```

**Out of Memory**:
```bash
# Increase memory limits
helm upgrade slo-scout slo-scout/slo-scout \
  --set backend.resources.limits.memory=2Gi \
  --namespace=slo-scout
```

#### Issue 2: High Kafka Consumer Lag

**Symptoms**:
```bash
# Lag increasing over time
kubectl exec -it kafka-0 -n slo-scout -- \
  kafka-consumer-groups.sh \
    --bootstrap-server localhost:9092 \
    --group fingerprinting-consumer \
    --describe

# TOPIC           PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG
# raw-telemetry   0          1000000         1500000         500000
```

**Diagnosis**:
```bash
# Check Flink job parallelism
kubectl logs flink-jobmanager-xxxxx -n slo-scout | grep parallelism

# Check TaskManager resource utilization
kubectl top pods -n slo-scout -l component=flink-taskmanager
```

**Solutions**:

**Increase Parallelism**:
```bash
helm upgrade slo-scout slo-scout/slo-scout \
  --set flink.jobs.fingerprinting.parallelism=20 \
  --set flink.taskmanagers.replicas=10 \
  --namespace=slo-scout
```

**Add More Kafka Partitions**:
```bash
kubectl exec -it kafka-0 -n slo-scout -- \
  kafka-topics.sh \
    --bootstrap-server localhost:9092 \
    --alter \
    --topic raw-telemetry \
    --partitions 10
```

#### Issue 3: Milvus Query Timeout

**Symptoms**:
```bash
# Backend logs show:
# ERROR: Milvus query timeout after 30s
```

**Diagnosis**:
```bash
# Check Milvus collection size
kubectl exec -it milvus-standalone-0 -n slo-scout -- \
  /opt/milvus/bin/milvus-cli show collection -c capsules

# Check Milvus resource usage
kubectl top pod milvus-standalone-0 -n slo-scout
```

**Solutions**:

**Increase Query Timeout**:
```bash
helm upgrade slo-scout slo-scout/slo-scout \
  --set backend.config.milvus.queryTimeout=60s \
  --namespace=slo-scout
```

**Optimize Index Parameters**:
```bash
# Rebuild HNSW index with better parameters
kubectl exec -it milvus-standalone-0 -n slo-scout -- \
  /opt/milvus/bin/milvus-cli alter index \
    -c capsules \
    -n embedding_vector \
    -t HNSW \
    -p '{"M": 16, "efConstruction": 200}'
```

**Scale Milvus (Enterprise tier)**:
```bash
helm upgrade slo-scout slo-scout/slo-scout \
  --set milvus.queryNode.replicas=5 \
  --namespace=slo-scout
```

#### Issue 4: Promtool Validation Failures

**Symptoms**:
```bash
# Backend logs show:
# ERROR: Generated Prometheus rule failed validation:
# rule validation error: invalid PromQL expression
```

**Diagnosis**:
```bash
# Download generated rule
kubectl exec -it backend-api-xxxxx -n slo-scout -- \
  cat /tmp/generated-rule.yaml > /tmp/debug-rule.yaml

# Validate locally
promtool check rules /tmp/debug-rule.yaml
```

**Solutions**:

**Fix PromQL Syntax**:
```bash
# Common issues:
# - Missing quotes around label values
# - Invalid aggregation operators
# - Incorrect metric names

# Test PromQL in Prometheus UI before deploying
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &
# Navigate to http://localhost:9090 and test query
```

**Update Validation Logic**:
```bash
# If validation is too strict, adjust settings
helm upgrade slo-scout slo-scout/slo-scout \
  --set backend.config.validation.promtool.strict=false \
  --namespace=slo-scout
```

#### Issue 5: PII Not Redacted

**Symptoms**:
```bash
# UI shows email addresses or IP addresses in logs
```

**Diagnosis**:
```bash
# Check redaction pipeline status
kubectl logs -n slo-scout -l app=flink-taskmanager | grep redaction

# Verify redaction patterns
kubectl exec -it backend-api-xxxxx -n slo-scout -- \
  python -c "from backend.services.pii_redaction import PIIRedactor; print(PIIRedactor().patterns)"
```

**Solutions**:

**Update Redaction Patterns**:
```bash
# Add custom PII patterns via ConfigMap
kubectl create configmap pii-patterns \
  --from-file=patterns.yaml \
  --namespace=slo-scout

# patterns.yaml:
# - pattern: '\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'
#   replacement: '<EMAIL>'
# - pattern: '\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b'
#   replacement: '<IP>'
```

**Reprocess Historical Data**:
```bash
# Trigger reprocessing of capsules
curl -X POST http://backend-api:8000/api/v1/admin/reprocess \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"start_date": "2025-09-01", "end_date": "2025-10-01"}'
```

#### Issue 6: GitOps PR Creation Fails

**Symptoms**:
```bash
# Backend logs show:
# ERROR: Failed to create GitHub PR: 401 Unauthorized
```

**Diagnosis**:
```bash
# Verify GitHub token
kubectl get secret slo-scout-secrets -n slo-scout -o jsonpath='{.data.github-token}' | base64 -d

# Test token manually
curl -H "Authorization: token $(kubectl get secret slo-scout-secrets -n slo-scout -o jsonpath='{.data.github-token}' | base64 -d)" \
  https://api.github.com/user
```

**Solutions**:

**Update GitHub Token**:
```bash
# Create new token with repo scope
# https://github.com/settings/tokens/new

kubectl create secret generic slo-scout-secrets \
  --from-literal=github-token=ghp_newtoken \
  --namespace=slo-scout \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart backend to pick up new token
kubectl rollout restart deployment backend-api -n slo-scout
```

**Use GitLab Instead**:
```bash
helm upgrade slo-scout slo-scout/slo-scout \
  --set backend.gitops.provider=gitlab \
  --set backend.gitops.gitlabUrl=https://gitlab.example.com \
  --namespace=slo-scout
```

### Debugging Tools

#### Access Pod Shell

```bash
# Backend API
kubectl exec -it backend-api-xxxxx -n slo-scout -- /bin/bash

# Flink JobManager
kubectl exec -it flink-jobmanager-xxxxx -n slo-scout -- /bin/bash

# TimescaleDB
kubectl exec -it timescaledb-0 -n slo-scout -- psql -U postgres -d slo_scout
```

#### Port Forwarding for Local Access

```bash
# Backend API
kubectl port-forward svc/backend-api 8000:8000 -n slo-scout &

# Flink UI
kubectl port-forward svc/flink-jobmanager 8081:8081 -n slo-scout &

# Prometheus
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &

# Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring &
```

#### Enable Debug Logging

```bash
helm upgrade slo-scout slo-scout/slo-scout \
  --set backend.config.logLevel=debug \
  --set flink.config.logLevel=DEBUG \
  --namespace=slo-scout

# View debug logs
kubectl logs -f backend-api-xxxxx -n slo-scout
```

#### Cluster-Wide Diagnostics

```bash
# Generate diagnostic bundle
cat <<'EOF' > collect-diagnostics.sh
#!/bin/bash
OUTDIR=slo-scout-diagnostics-$(date +%Y%m%d-%H%M%S)
mkdir -p $OUTDIR

# Pod status
kubectl get pods -n slo-scout -o wide > $OUTDIR/pods.txt

# Pod logs
for pod in $(kubectl get pods -n slo-scout -o name); do
  kubectl logs $pod -n slo-scout > $OUTDIR/$(basename $pod).log 2>&1
done

# Resource usage
kubectl top pods -n slo-scout > $OUTDIR/top-pods.txt
kubectl top nodes > $OUTDIR/top-nodes.txt

# Helm release
helm get values slo-scout -n slo-scout > $OUTDIR/helm-values.yaml
helm get manifest slo-scout -n slo-scout > $OUTDIR/helm-manifest.yaml

# Events
kubectl get events -n slo-scout --sort-by='.lastTimestamp' > $OUTDIR/events.txt

# Network
kubectl get networkpolicies -n slo-scout -o yaml > $OUTDIR/networkpolicies.yaml
kubectl get svc -n slo-scout -o yaml > $OUTDIR/services.yaml

# Persistent Volumes
kubectl get pvc -n slo-scout -o yaml > $OUTDIR/pvc.yaml
kubectl get pv -o yaml > $OUTDIR/pv.yaml

# Archive
tar czf $OUTDIR.tar.gz $OUTDIR
echo "Diagnostics collected in $OUTDIR.tar.gz"
EOF

chmod +x collect-diagnostics.sh
./collect-diagnostics.sh
```

---

## Monitoring and Self-Observability

SLO-Scout monitors its own performance and exposes metrics for external observability platforms.

### Prometheus Metrics

SLO-Scout exports the following metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `slo_scout_ingest_lag_seconds` | Gauge | Time between event creation and ingestion |
| `slo_scout_embedding_queue_length` | Gauge | Number of capsules waiting for embedding |
| `slo_scout_vector_query_latency_seconds` | Histogram | Milvus query latency |
| `slo_scout_llm_calls_total` | Counter | Total LLM API calls |
| `slo_scout_llm_tokens_total` | Counter | Total tokens consumed |
| `slo_scout_artifact_generation_duration_seconds` | Histogram | Time to generate artifacts |
| `slo_scout_promtool_validations_total` | Counter | Promtool validations (success/failure) |
| `slo_scout_policy_guard_violations_total` | Counter | Policy Guard violations |
| `slo_scout_pr_creations_total` | Counter | GitOps PR creations (success/failure) |

**Access Metrics**:
```bash
kubectl port-forward svc/backend-api 8000:8000 -n slo-scout &
curl http://localhost:8000/metrics
```

### SLO-Scout's Own SLOs

Defined in `/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/infrastructure/prometheus/slo-scout-slos.yaml`:

1. **Ingestion SLO**: 99% of telemetry ingested within 60 seconds
2. **Query SLO**: 95% of API queries respond within 2 seconds
3. **Summarization SLO**: 95% of analysis jobs complete within 5 minutes

**Verify SLOs**:
```bash
# Check SLO compliance
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &

# Query ingest lag SLO
curl -G http://localhost:9090/api/v1/query \
  --data-urlencode 'query=histogram_quantile(0.99, slo_scout_ingest_lag_seconds_bucket) < 60'
```

### Grafana Dashboards

Import pre-built dashboard:

```bash
# Apply dashboard JSON
kubectl create configmap slo-scout-dashboard \
  --from-file=/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/infrastructure/grafana/slo-scout-dashboard.json \
  --namespace=monitoring

# Configure Grafana to load dashboard
kubectl label configmap slo-scout-dashboard grafana_dashboard=1 -n monitoring
```

**Dashboard Panels**:
- Ingest lag time series
- Embedding queue depth
- Vector query latency p50/p95/p99
- LLM call rate and token usage
- Artifact generation success rate
- Policy Guard violation rate

### Alerting

Alerts defined in `/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/infrastructure/prometheus/slo-scout-alerts.yaml`:

1. **IngestLagHigh**: Ingest lag > 120s for 5 minutes
2. **EmbeddingQueueBacklog**: Embedding queue > 10,000 for 10 minutes
3. **VectorQueryLatencyHigh**: p95 query latency > 5s for 5 minutes
4. **LLMRateLimitApproaching**: LLM calls > 80% of quota
5. **PolicyGuardViolationSpike**: Policy violations increased 5x in 15 minutes

**Verify Alerts**:
```bash
# Check alert rules loaded
kubectl port-forward svc/prometheus 9090:9090 -n monitoring &
curl http://localhost:9090/api/v1/rules | jq '.data.groups[] | select(.name == "slo-scout")'

# Check alert status
curl http://localhost:9090/api/v1/alerts
```

### Log Aggregation

Configure centralized logging:

```yaml
# values.yaml
logging:
  enabled: true
  backend: elasticsearch  # elasticsearch | loki | cloudwatch
  elasticsearch:
    url: https://elasticsearch:9200
    index: slo-scout-logs
  loki:
    url: http://loki:3100
  cloudwatch:
    region: us-west-2
    logGroup: /aws/eks/slo-scout
```

**Access Logs via Kibana/Grafana**:
```bash
# Port-forward to Kibana
kubectl port-forward svc/kibana 5601:5601 -n monitoring &

# Navigate to http://localhost:5601
# Create index pattern: slo-scout-logs-*
```

### Distributed Tracing

SLO-Scout instruments itself with OpenTelemetry:

```yaml
# values.yaml
tracing:
  enabled: true
  backend: jaeger  # jaeger | tempo | zipkin
  jaeger:
    endpoint: http://jaeger-collector:14268/api/traces
  tempo:
    endpoint: http://tempo:4317
  samplingRate: 0.1  # Sample 10% of requests
```

**Access Traces**:
```bash
# Port-forward to Jaeger UI
kubectl port-forward svc/jaeger-query 16686:16686 -n monitoring &

# Navigate to http://localhost:16686
# Search for service: slo-scout-backend
```

### Health Checks

All components expose health endpoints:

```bash
# Backend API
curl http://backend-api:8000/health
# {"status":"healthy","version":"1.0.0","uptime":"3h15m"}

# Collectors
curl http://prometheus-collector:8080/health
# {"status":"healthy","kafka_connected":true}

# Flink JobManager
curl http://flink-jobmanager:8081/overview
# {"taskmanagers":5,"slots-total":10,"slots-available":2}
```

---

## Next Steps

After successful deployment:

1. **Onboard First Service**: Follow [quickstart.md](/Users/nord/Downloads/slo-scout-spec-kit/slo-scout/specs/001-ingest-spec-txt/quickstart.md) to analyze your first service
2. **Configure Integrations**: Set up GitHub/GitLab tokens, LLM API keys
3. **Customize SLO Thresholds**: Adjust Policy Guard blast radius thresholds
4. **Set Up Backup Automation**: Schedule database backups to S3
5. **Enable Monitoring**: Import Grafana dashboards and configure alerts
6. **Train Team**: Share UI walkthrough and API documentation

---

## Support

- **Documentation**: [docs.slo-scout.io](https://docs.slo-scout.io)
- **GitHub Issues**: [github.com/slo-scout/slo-scout/issues](https://github.com/slo-scout/slo-scout/issues)
- **Community Slack**: [slo-scout.slack.com](https://slo-scout.slack.com)
- **Enterprise Support**: support@slo-scout.io

---

**Document Version**: 1.0.0
**Last Updated**: 2025-10-04
**Maintained By**: SLO-Scout Platform Team
