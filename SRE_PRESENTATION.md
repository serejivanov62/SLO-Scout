# 🎯 SLO-Scout: Полное техническое описание для SRE

## Оглавление
1. [Общая концепция](#общая-концепция)
2. [Архитектура системы](#архитектура-системы)
3. [Компоненты и их назначение](#компоненты-и-их-назначение)
4. [Поток данных](#поток-данных)
5. [База данных и хранилища](#база-данных-и-хранилища)
6. [Deployment и инфраструктура](#deployment-и-инфраструктура)
7. [Мониторинг и наблюдаемость](#мониторинг-и-наблюдаемость)
8. [Масштабирование и производительность](#масштабирование-и-производительность)
9. [Безопасность](#безопасность)
10. [Операционные процедуры](#операционные-процедуры)

---

## Общая концепция

### Что такое SLO-Scout?

**SLO-Scout** — это платформа для автоматического обнаружения Service Level Indicators (SLI) и генерации Service Level Objectives (SLO) на основе реальной телеметрии observability систем.

### Проблема, которую решает:

В современных микросервисных архитектурах создание и поддержка SLO вручную:
- Требует глубокого понимания бизнес-логики каждого сервиса
- Отнимает ~2-4 часа на сервис у SRE команды
- Быстро устаревает при изменении архитектуры
- Часто не покрывает критические user journeys

### Решение SLO-Scout:

1. **Автоматически анализирует** distributed traces, metrics, logs
2. **Обнаруживает user journeys** через алгоритмы graph traversal
3. **Генерирует SLI кандидаты** на основе статистического анализа
4. **Создает production-ready артефакты**: Prometheus rules, Grafana dashboards, runbooks
5. **Интегрируется с GitOps** через PR в Git репозиторий

**Результат**: Время создания SLO сокращается с 2-4 часов до 15-30 минут.

---

## Архитектура системы

### High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Telemetry Sources                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ Prometheus  │  │    OTLP     │  │  FluentBit  │  │  Kubernetes │   │
│  │   Metrics   │  │   Traces    │  │    Logs     │  │   Metrics   │   │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────┘
          │                 │                 │                 │
          └─────────────────┴─────────────────┴─────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │    Collectors Layer (Go)       │
                    │  • prometheus-collector (2x)   │
                    │  • otlp-collector (3x)         │
                    │  • log-collector (DaemonSet)   │
                    └───────────────┬────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │     Apache Kafka 3.5+          │
                    │  Topics:                       │
                    │  • raw-telemetry               │
                    │  • enriched-events             │
                    │  • capsules                    │
                    └───────────────┬────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
┌─────────▼──────────┐  ┌───────────▼──────────┐  ┌─────────▼──────────┐
│  Fingerprint Job   │  │ Embedding Pipeline   │  │  Backend Service   │
│  (Apache Flink)    │  │  (Apache Flink)      │  │   (FastAPI)        │
│                    │  │                      │  │                    │
│ • Trace analysis   │  │ • Sentence Trans.    │  │ • REST API         │
│ • User journey     │  │ • Vector generation  │  │ • Analysis jobs    │
│   detection        │  │ • Milvus write       │  │ • SLI/SLO logic    │
│ • Capsule creation │  │                      │  │ • Artifact gen     │
└─────────┬──────────┘  └───────────┬──────────┘  └─────────┬──────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │      Storage Layer             │
                    ├────────────────────────────────┤
                    │ • PostgreSQL 14 (TimescaleDB) │
                    │   - Services, SLIs, SLOs       │
                    │   - Telemetry Events           │
                    │   - Capsules (user journeys)   │
                    │                                │
                    │ • Milvus 2.3+ (Vector DB)     │
                    │   - Journey embeddings         │
                    │   - Semantic search            │
                    │                                │
                    │ • MinIO / S3                   │
                    │   - Raw traces (cold storage)  │
                    │   - Generated artifacts        │
                    │                                │
                    │ • Redis 7.2+                   │
                    │   - Celery task queue          │
                    │   - Cache layer                │
                    └────────────────────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │       Output Layer             │
                    ├────────────────────────────────┤
                    │ • Prometheus Alert Rules       │
                    │ • Grafana Dashboards           │
                    │ • SLO YAML definitions         │
                    │ • Markdown Runbooks            │
                    │ • GitHub/GitLab PRs            │
                    └────────────────────────────────┘
```

### Deployment Topology

- **Kubernetes (K3s/K8s)** — основная платформа оркестрации
- **Helm Chart** — стандартизированный deployment
- **Multi-AZ** — высокая доступность (production)
- **Resource Requests/Limits** — predictable resource allocation

---

## Компоненты и их назначение

### 1. Collectors Layer (Go 1.21+)

#### Prometheus Collector
**Файлы**: `collectors/prometheus-collector/`

**Назначение**:
- Периодический опрос Prometheus remote_read API
- Извлечение метрик для зарегистрированных сервисов
- Публикация в Kafka topic `raw-telemetry`

**Технические детали**:
- Написан на Go для минимальной latency
- Hot-reload конфигурации через ConfigMap
- Reconciliation loop: 60 секунд (fallback к polling)
- fsnotify watcher для immediate updates

**Ресурсы**:
```yaml
requests:
  memory: 128Mi
  cpu: 100m
limits:
  memory: 512Mi
  cpu: 500m
```

**Healthchecks**: `/health` endpoint на порту 8080

---

#### OTLP Collector
**Файлы**: `collectors/otlp-collector/`

**Назначение**:
- Прием OpenTelemetry traces/metrics через gRPC (4317) и HTTP (4318)
- Парсинг OTLP protobuf формата
- Enrichment: добавление service metadata
- Публикация в Kafka topic `raw-telemetry`

**Технические детали**:
- Горизонтальное масштабирование: 3-20 pods (HPA)
- Статeless design для простого scaling
- Batch processing для эффективности
- Target: 70% CPU utilization для autoscaling

**Важно для SRE**:
- Критичный компонент для trace ingestion
- При сбое traces теряются (no disk buffering в collectors)
- HPA помогает справиться с traffic spikes

---

#### Log Collector
**Файлы**: `collectors/log-collector/main.go`

**Назначение**:
- DaemonSet deployment на каждой ноде
- Сбор логов через Kubernetes API или tail файлов
- Structured logging parsing (JSON)
- Публикация в Kafka topic `raw-telemetry`

**Технические детали**:
- DaemonSet ensures 1 pod per node
- Filesystem watching с fsnotify
- Graceful shutdown при обновлении ConfigMap
- Reconciliation loop 60s (fallback)

---

### 2. Stream Processing Layer (Apache Flink 1.17)

#### Fingerprint Job
**Файлы**: `streaming/flink/src/main/java/fingerprinting/`

**Назначение**:
- Real-time анализ distributed traces
- Построение графа вызовов (trace graph)
- Обнаружение user journeys методом path analysis
- Создание "capsules" — агрегированных представлений journey

**Алгоритм работы**:
1. **Stream from Kafka**: читает `raw-telemetry` topic
2. **Keyed by trace_id**: группирует spans по trace
3. **Window**: tumbling window 5 минут
4. **Graph construction**: строит DAG из spans
5. **Fingerprinting**: генерирует hash на основе:
   - Последовательности вызовов сервисов
   - HTTP methods
   - Status codes
6. **Capsule creation**: агрегирует похожие traces
7. **Output to Kafka**: публикует в `capsules` topic

**Технические детали**:
- State backend: RocksDB (checkpointing)
- Checkpointing interval: 30 секунд
- Parallelism: 4 task slots
- Kryo serialization для custom objects

**Ресурсы**:
```yaml
TaskManager:
  memory: 2Gi
  cpu: 1000m
  replicas: 2
```

**Важно для SRE**:
- Stateful application (требует persistent volume для checkpoints)
- При рестарте восстанавливается из последнего checkpoint
- Backpressure monitoring через Flink UI

---

#### Embedding Pipeline Job
**Файлы**: `streaming/embedding-pipeline-job/`

**Назначение**:
- Генерация semantic embeddings для capsules
- Использование Sentence Transformers (all-MiniLM-L6-v2)
- Запись vectors в Milvus для similarity search

**Алгоритм работы**:
1. **Read from Kafka**: читает `capsules` topic
2. **Batch aggregation**: группирует по 32 capsule
3. **Embedding generation**:
   - Извлекает текстовое описание journey
   - Запускает Sentence Transformer model
   - Получает 384-dim vector
4. **Write to Milvus**: bulk insert в collection
5. **Acknowledgement**: commit Kafka offset

**Технические детали**:
- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Embedding dimension: 384
- Batch size: 32 для оптимизации throughput
- gRPC client для Milvus

**Ресурсы**:
```yaml
TaskManager:
  memory: 4Gi
  cpu: 2000m
```

---

### 3. Backend Service (Python 3.11 + FastAPI)

#### API Layer
**Файлы**: `backend/src/api/`

**Endpoints**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/services` | POST | Register new service |
| `/api/v1/services` | GET | List registered services |
| `/api/v1/analyze` | POST | Start analysis job |
| `/api/v1/analyze/{job_id}` | GET | Get analysis status |
| `/api/v1/slis` | GET | List SLI candidates |
| `/api/v1/slis/{id}/approve` | POST | Approve SLI |
| `/api/v1/slos` | POST | Create SLO |
| `/api/v1/slos/{id}/error-budget` | GET | Current error budget |
| `/api/v1/artifacts` | POST | Generate artifacts |
| `/api/v1/artifacts/{id}/deploy` | POST | Deploy to Git |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

**Технические детали**:
- Async I/O с asyncpg (PostgreSQL)
- SQLAlchemy 2.0 ORM
- Pydantic validation
- OpenAPI spec автоматически генерируется

**Middleware**:
- CORS configuration
- Error handling (structured JSON errors)
- Policy guard (blast radius checking)
- Request validation

---

#### Service Layer
**Файлы**: `backend/src/services/`

**Ключевые сервисы**:

1. **TraceGraphService** (`trace_graph.py`)
   - Построение графа из spans
   - DFS/BFS traversal для entry points
   - Critical path detection

2. **SLIGenerator** (`sli_generator.py`)
   - Анализ capsules для извлечения SLI candidates
   - Статистический анализ: p50, p95, p99 latency
   - Error rate calculation: `(failed_requests / total_requests)`
   - Availability: `(successful_requests / total_requests) * 100`

3. **LLMRecommender** (`llm_recommender.py`)
   - Интеграция с OpenAI GPT-4 / Anthropic Claude
   - Context-aware recommendations
   - Prompt engineering для SLO generation
   - Retry logic с exponential backoff

4. **ConfidenceScorer** (`confidence_scorer.py`)
   - Оценка надежности SLI кандидата (0.0-1.0)
   - Факторы:
     - Data completeness (sample size)
     - Statistical significance
     - Journey coverage
     - Error rate variance

5. **PolicyEvaluator** (`policy_evaluator.py`)
   - Blast radius calculation
   - Policy enforcement перед deployment
   - Fail-safe: default deny при неопределенности

6. **ArtifactGenerator** (`artifact_generator.py`)
   - Генерация Prometheus recording rules
   - Генерация alert rules с thresholds
   - Grafana dashboard JSON
   - Markdown runbooks

---

#### Workers (Celery 5.3)
**Файлы**: `backend/src/workers/`

**Задачи**:

1. **journey_discovery.py**
   - Async task для длительного анализа traces
   - Timeout: 30 минут (configurable)
   - Retry: 3 attempts с exponential backoff

2. **embedding_pipeline.py**
   - Async embedding generation
   - Batch processing для эффективности

3. **metrics.py**
   - Сбор метрик для self-observability
   - Publish в Prometheus pushgateway

**Конфигурация Celery**:
```python
worker_pool: prefork
worker_concurrency: 5
task_acks_late: True
task_reject_on_worker_lost: True
soft_time_limit: 1800  # 30 minutes
time_limit: 1900
```

**Queues**:
- `journey_discovery` — приоритет: high
- `embeddings` — приоритет: low

---

### 4. Storage Layer

#### PostgreSQL 14 + TimescaleDB

**Таблицы**:

1. **services**
   - Регистрация сервисов для мониторинга
   - Поля: `id`, `name`, `environment`, `owner_team`, `telemetry_endpoints`, `label_mappings`, `status`
   - Index: `(name, environment)` — UNIQUE

2. **telemetry_events** (Hypertable в TimescaleDB)
   - Time-series данные событий
   - Поля: `event_id`, `service_id`, `timestamp`, `event_type`, `severity`, `trace_id`, `span_id`, `attributes`
   - Partitioning: по `timestamp` с chunk interval 1 день
   - Retention policy: 7 дней (автоочистка)
   - Indexes:
     - `(service_id, timestamp DESC)` — для queries по сервису
     - `(trace_id)` — для trace reconstruction
     - `(event_type, timestamp DESC)` — для type-specific queries

3. **capsules** (Hypertable)
   - Агрегированные user journeys
   - Поля: `capsule_id`, `journey_id`, `service_id`, `start_time`, `end_time`, `fingerprint_hash`, `step_count`, `event_ids`
   - Partitioning: по `start_time` с chunk interval 1 час
   - Index: `(fingerprint_hash)` — для группировки похожих journeys

4. **user_journeys**
   - Обнаруженные паттерны user journeys
   - Поля: `journey_id`, `service_id`, `name`, `description`, `entry_points` (JSONB), `critical_path` (JSONB)

5. **slis**
   - SLI кандидаты и утвержденные SLI
   - Поля: `sli_id`, `journey_id`, `name`, `metric_query`, `threshold_ms`, `error_budget`, `confidence_score`, `approved`, `approved_by`, `approved_at`
   - Index: `(approved)` — для фильтрации

6. **slos**
   - SLO определения
   - Поля: `slo_id`, `sli_id`, `service_id`, `name`, `target_percentage`, `time_window_days`, `threshold_variant`
   - CHECK constraint: `target_percentage BETWEEN 0 AND 1`

7. **artifacts**
   - Сгенерированные артефакты
   - Поля: `artifact_id`, `slo_id`, `artifact_type`, `content` (TEXT), `status`, `pr_url`, `deployed_at`
   - Types: `prometheus_rule`, `grafana_dashboard`, `runbook`

8. **policies**
   - Deployment policies
   - Поля: `policy_id`, `name`, `blast_radius_threshold`, `enabled`
   - Default policies:
     - Conservative: 10% blast radius
     - Critical Services: 5% blast radius

**Схема данных**: см. `backend/migrations/versions/001_initial_schema.py`

---

#### Milvus 2.3+ (Vector Database)

**Назначение**:
- Semantic search по embeddings
- Similarity matching для journey patterns
- K-nearest neighbors (KNN) queries

**Collections**:
- `journey_embeddings` — 384-dim vectors (Sentence Transformers)

**Indexes**:
- HNSW (Hierarchical Navigable Small World) для fast ANN search
- Parameters:
  - `M`: 16 (graph connectivity)
  - `efConstruction`: 200

**Query Example**:
```python
collection.search(
    data=[query_vector],
    anns_field="embedding",
    param={"metric_type": "COSINE", "params": {"ef": 64}},
    limit=10
)
```

---

#### Redis 7.2+

**Назначение**:
1. **Celery backend**: task results storage
2. **Rate limiting**: для API endpoints
3. **Cache**: frequently accessed data

**Конфигурация**:
- Persistence: AOF (Append-Only File)
- Max memory: 2GB
- Eviction policy: `allkeys-lru`

---

#### MinIO / S3

**Назначение**:
- Cold storage для raw traces
- Artifact storage (dashboards, runbooks)
- Backup retention

**Buckets**:
- `raw-traces`: raw OTLP traces (retention 30 days)
- `artifacts`: generated Prometheus rules, dashboards
- `backups`: database backups

---

### 5. Frontend (React 18 + TypeScript)

**Файлы**: `frontend/src/`

**Компоненты**:
- **ServicesPage** — регистрация и управление сервисами
- **AnalysisPage** — запуск и мониторинг analysis jobs
- **SLIApprovalCard** — approval workflow для SLI
- **SLOsPage** — просмотр SLO и error budgets
- **ArtifactViewer** — просмотр сгенерированных артефактов

**Tech Stack**:
- React 18 (hooks)
- TypeScript 5.x
- Tailwind CSS
- Fetch API для backend communication

**Deployment**:
- Nginx static file serving
- NodePort 30080 (Kubernetes)

---

## Поток данных

### End-to-End Flow

```
1. Telemetry Sources → Collectors
   - Prometheus scrapes metrics
   - OTLP receivers accept traces
   - Log collectors tail Kubernetes logs
   - Collectors publish to Kafka "raw-telemetry" topic

2. Kafka → Flink Fingerprint Job
   - Consumes "raw-telemetry" topic
   - Groups by trace_id
   - Constructs trace graph
   - Generates fingerprint hash
   - Detects user journeys
   - Publishes "capsules" to Kafka

3. Flink → PostgreSQL
   - Writes capsules to TimescaleDB
   - Hypertable partitioning by timestamp
   - Indexed by fingerprint_hash

4. Kafka → Flink Embedding Job
   - Consumes "capsules" topic
   - Batch aggregation (32 capsules)
   - Generates 384-dim embeddings
   - Writes to Milvus vector DB

5. User → Backend API
   - POST /api/v1/analyze
   - Backend queries PostgreSQL for capsules
   - Queries Milvus for similar journeys
   - Calls TraceGraphService
   - Calls SLIGenerator
   - Calls LLMRecommender (GPT-4)
   - Stores SLI candidates in PostgreSQL

6. User Approval
   - Frontend: SLI approval workflow
   - POST /api/v1/slis/{id}/approve
   - Backend: updates slis.approved = true

7. SLO Creation
   - POST /api/v1/slos
   - Backend: validates policy (blast radius)
   - Creates SLO record

8. Artifact Generation
   - POST /api/v1/artifacts
   - ArtifactGenerator creates:
     - Prometheus recording rule
     - Prometheus alert rule
     - Grafana dashboard JSON
     - Markdown runbook
   - Stores in artifacts table

9. Deployment
   - POST /api/v1/artifacts/{id}/deploy
   - PRGenerator creates GitHub PR
   - Policy guard checks blast radius
   - PR merged → GitOps applies changes
```

---

## Масштабирование и производительность

### Горизонтальное масштабирование

| Компонент | Scaling Strategy | Target Metrics |
|-----------|------------------|----------------|
| **OTLP Collector** | HPA (3-20 pods) | CPU 70% |
| **Backend** | HPA (2-10 pods) | CPU 70%, Memory 80% |
| **Flink TaskManager** | Manual scaling | Backpressure < 10% |
| **Celery Workers** | HPA (2-20 pods) | Queue depth < 100 |
| **PostgreSQL** | Read replicas | Read latency < 10ms |
| **Redis** | Sentinel (HA) | Memory < 80% |
| **Kafka** | Add brokers | Partition lag < 1000 |

### Capacity Planning

**Baseline (small deployment)**:
- Services: 10-50
- Traces/day: 1M
- Capsules/day: 50K
- Storage: 50GB PostgreSQL, 10GB Milvus

**Medium deployment**:
- Services: 50-200
- Traces/day: 10M
- Capsules/day: 500K
- Storage: 500GB PostgreSQL, 100GB Milvus

**Large deployment**:
- Services: 200+
- Traces/day: 100M+
- Capsules/day: 5M+
- Storage: 5TB+ PostgreSQL, 1TB Milvus

---

## Мониторинг и наблюдаемость

### Self-Observability

**Prometheus Metrics**:
- `sloscout_collector_events_total{collector="prometheus|otlp|log"}` — ingested events
- `sloscout_flink_capsules_created_total` — capsules created
- `sloscout_api_requests_total{endpoint, status}` — API traffic
- `sloscout_sli_generation_duration_seconds` — SLI generation latency
- `sloscout_policy_evaluations_total{result="allow|deny"}` — policy decisions
- `sloscout_error_budget_remaining{slo_id}` — current error budget

**Grafana Dashboards**:
- System health overview
- Kafka lag monitoring
- Flink backpressure
- API latency percentiles (p50, p95, p99)

**Alerts**:
- Collector down > 5 minutes
- Kafka partition lag > 10K messages
- Flink job restart > 3 times/hour
- PostgreSQL connection pool exhaustion
- Milvus query latency > 500ms

---

## Безопасность

### Authentication & Authorization
- API key authentication для external clients
- RBAC для internal services
- Kubernetes ServiceAccounts

### Data Security
- PII redaction в logs и traces
- Encryption at rest: PostgreSQL TDE (optional)
- Encryption in transit: TLS everywhere
- Secrets management: External Secrets Operator

### Policy Enforcement
- Blast radius checking перед deployment
- Approval workflow для SLI/SLO changes
- Audit log для всех deployments

---

## Операционные процедуры

### Deployment

```bash
# 1. Create namespace
kubectl create namespace slo-scout

# 2. Install Helm chart
helm install slo-scout ./infrastructure/helm/slo-scout \
  --namespace slo-scout \
  --values infrastructure/helm/slo-scout/values-prod.yaml

# 3. Verify
kubectl get pods -n slo-scout
kubectl logs -n slo-scout -l app=slo-scout-backend --tail=100
```

### Database Migrations

```bash
# Run migration manually
kubectl exec -it -n slo-scout slo-scout-backend-0 -- \
  python -m alembic upgrade head

# Verify
kubectl exec -it -n slo-scout slo-scout-timescaledb-0 -- \
  psql -U postgres -d slo_scout -c "\dt"
```

### Backup & Restore

```bash
# Backup PostgreSQL
kubectl exec -n slo-scout slo-scout-timescaledb-0 -- \
  pg_dump -U postgres slo_scout | gzip > backup-$(date +%Y%m%d).sql.gz

# Restore
gunzip -c backup-20251007.sql.gz | \
  kubectl exec -i -n slo-scout slo-scout-timescaledb-0 -- \
  psql -U postgres slo_scout
```

### Troubleshooting

**Collectors not ingesting**:
```bash
# Check logs
kubectl logs -n slo-scout -l app=otlp-collector --tail=200

# Verify Kafka connectivity
kubectl exec -n slo-scout slo-scout-backend-0 -- \
  telnet slo-scout-kafka 9092
```

**Flink job failing**:
```bash
# Check Flink UI
kubectl port-forward -n slo-scout svc/flink-jobmanager 8081:8081

# View logs
kubectl logs -n slo-scout -l app=flink-taskmanager --tail=500
```

**API slow responses**:
```bash
# Check PostgreSQL connections
kubectl exec -n slo-scout slo-scout-timescaledb-0 -- \
  psql -U postgres -c "SELECT count(*) FROM pg_stat_activity;"

# Check Redis
kubectl exec -n slo-scout slo-scout-redis-0 -- redis-cli INFO
```

---

## Roadmap

### Current Status (v1.0)
✅ Production-ready
✅ 154/154 tasks completed
✅ 183+ tests (95%+ coverage)
✅ Self-observability

### Planned Features (v1.1)
- [ ] Multi-cluster support
- [ ] Custom embeddings models
- [ ] Advanced policy rules
- [ ] SLO forecasting with ML

---

## Контакты и поддержка

**Documentation**: [docs/](docs/)
**Issues**: GitHub Issues
**Slack**: #slo-scout

---

**Generated**: 2025-10-07
**Version**: 1.0.0
**Status**: Production Ready ✅
