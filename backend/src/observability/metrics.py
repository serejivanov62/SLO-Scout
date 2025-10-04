"""
Prometheus Metrics Exporter (T142)

Exports SLO-Scout's own metrics for self-observability.
Per spec.md FR-024: Export ingest_lag_seconds, embedding_queue_length,
vector_query_latency, llm_calls_per_min, daily_llm_spend_usd
"""
from typing import Optional
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)
from datetime import datetime, timedelta
import time


class SLOScoutMetrics:
    """
    Self-observability metrics for SLO-Scout.

    Per FR-024: Exports metrics for monitoring SLO-Scout's own performance.
    Per FR-025: Enables SLO-Scout to measure its own SLOs (99% ingest < 60s,
    95% query < 2s, 95% summarization < 5m).
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """
        Initialize metrics collectors.

        Args:
            registry: Prometheus registry (default creates new registry)
        """
        self.registry = registry or CollectorRegistry()

        # System info
        self.info = Info(
            'slo_scout_system',
            'SLO-Scout system information',
            registry=self.registry
        )

        # Ingest pipeline metrics (FR-024)
        self.ingest_lag_seconds = Gauge(
            'slo_scout_ingest_lag_seconds',
            'Time delay between telemetry event timestamp and ingestion to capsule store',
            ['service', 'environment', 'telemetry_type'],
            registry=self.registry
        )

        self.ingest_events_total = Counter(
            'slo_scout_ingest_events_total',
            'Total number of telemetry events ingested',
            ['service', 'environment', 'telemetry_type', 'status'],
            registry=self.registry
        )

        # Embedding pipeline metrics (FR-024)
        self.embedding_queue_length = Gauge(
            'slo_scout_embedding_queue_length',
            'Number of capsules waiting for embedding generation',
            ['embedding_model'],
            registry=self.registry
        )

        self.embedding_generation_duration_seconds = Histogram(
            'slo_scout_embedding_generation_duration_seconds',
            'Time to generate embeddings for a batch of capsules',
            ['embedding_model'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry
        )

        # Vector search metrics (FR-024)
        self.vector_query_latency = Histogram(
            'slo_scout_vector_query_latency_seconds',
            'Latency of vector similarity search queries',
            ['operation', 'collection'],
            buckets=[0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0],
            registry=self.registry
        )

        self.vector_query_results = Histogram(
            'slo_scout_vector_query_results',
            'Number of results returned from vector queries',
            ['operation', 'collection'],
            buckets=[1, 5, 10, 20, 50, 100, 200],
            registry=self.registry
        )

        # LLM integration metrics (FR-024)
        self.llm_calls_per_min = Gauge(
            'slo_scout_llm_calls_per_min',
            'Rate of LLM API calls per minute',
            ['model', 'operation'],
            registry=self.registry
        )

        self.llm_request_duration_seconds = Histogram(
            'slo_scout_llm_request_duration_seconds',
            'Duration of LLM API requests',
            ['model', 'operation', 'status'],
            buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
            registry=self.registry
        )

        self.llm_tokens_total = Counter(
            'slo_scout_llm_tokens_total',
            'Total LLM tokens consumed',
            ['model', 'operation', 'token_type'],
            registry=self.registry
        )

        self.daily_llm_spend_usd = Gauge(
            'slo_scout_daily_llm_spend_usd',
            'Estimated daily LLM API cost in USD',
            ['model'],
            registry=self.registry
        )

        # Analysis workflow metrics
        self.analysis_job_duration_seconds = Histogram(
            'slo_scout_analysis_job_duration_seconds',
            'Total duration of analysis jobs from start to completion',
            ['service', 'status'],
            buckets=[10, 30, 60, 120, 300, 600, 1800, 3600],
            registry=self.registry
        )

        self.sli_recommendations_total = Counter(
            'slo_scout_sli_recommendations_total',
            'Total number of SLI recommendations generated',
            ['service', 'journey', 'sli_type'],
            registry=self.registry
        )

        self.sli_confidence_score = Histogram(
            'slo_scout_sli_confidence_score',
            'Confidence scores of generated SLI recommendations',
            ['service', 'sli_type'],
            buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            registry=self.registry
        )

        # Artifact generation metrics
        self.artifact_generation_total = Counter(
            'slo_scout_artifact_generation_total',
            'Total number of artifacts generated',
            ['artifact_type', 'status'],
            registry=self.registry
        )

        self.artifact_validation_duration_seconds = Histogram(
            'slo_scout_artifact_validation_duration_seconds',
            'Time to validate generated artifacts',
            ['artifact_type', 'validator'],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry
        )

        # Database metrics
        self.db_query_duration_seconds = Histogram(
            'slo_scout_db_query_duration_seconds',
            'Database query execution time',
            ['database', 'operation', 'table'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
            registry=self.registry
        )

        self.db_connection_pool_size = Gauge(
            'slo_scout_db_connection_pool_size',
            'Number of database connections in pool',
            ['database', 'state'],
            registry=self.registry
        )

        # Kafka consumer metrics
        self.kafka_consumer_lag = Gauge(
            'slo_scout_kafka_consumer_lag',
            'Kafka consumer lag (uncommitted messages)',
            ['topic', 'consumer_group', 'partition'],
            registry=self.registry
        )

        self.kafka_messages_consumed_total = Counter(
            'slo_scout_kafka_messages_consumed_total',
            'Total Kafka messages consumed',
            ['topic', 'consumer_group', 'status'],
            registry=self.registry
        )

        # API endpoint metrics
        self.http_request_duration_seconds = Histogram(
            'slo_scout_http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint', 'status'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
            registry=self.registry
        )

        self.http_requests_total = Counter(
            'slo_scout_http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status'],
            registry=self.registry
        )

    def set_system_info(
        self,
        version: str,
        environment: str,
        deployment_id: str,
        embedding_model: str = "all-MiniLM-L6-v2"
    ) -> None:
        """Set system information metrics."""
        self.info.info({
            'version': version,
            'environment': environment,
            'deployment_id': deployment_id,
            'embedding_model': embedding_model
        })

    def record_ingest_lag(
        self,
        lag_seconds: float,
        service: str,
        environment: str,
        telemetry_type: str
    ) -> None:
        """
        Record ingest lag for a telemetry event.

        Args:
            lag_seconds: Time between event timestamp and ingestion
            service: Service name
            environment: Environment
            telemetry_type: Type of telemetry (metrics, traces, logs)
        """
        self.ingest_lag_seconds.labels(
            service=service,
            environment=environment,
            telemetry_type=telemetry_type
        ).set(lag_seconds)

    def record_ingest_event(
        self,
        service: str,
        environment: str,
        telemetry_type: str,
        status: str = "success"
    ) -> None:
        """Record an ingested telemetry event."""
        self.ingest_events_total.labels(
            service=service,
            environment=environment,
            telemetry_type=telemetry_type,
            status=status
        ).inc()

    def record_embedding_queue_length(
        self,
        queue_length: int,
        embedding_model: str = "all-MiniLM-L6-v2"
    ) -> None:
        """Record current embedding queue length."""
        self.embedding_queue_length.labels(
            embedding_model=embedding_model
        ).set(queue_length)

    def observe_embedding_generation(
        self,
        duration_seconds: float,
        embedding_model: str = "all-MiniLM-L6-v2"
    ) -> None:
        """Observe embedding generation duration."""
        self.embedding_generation_duration_seconds.labels(
            embedding_model=embedding_model
        ).observe(duration_seconds)

    def observe_vector_query(
        self,
        duration_seconds: float,
        operation: str,
        collection: str = "capsules",
        num_results: int = 0
    ) -> None:
        """
        Observe vector search query latency and results.

        Args:
            duration_seconds: Query duration
            operation: Operation type (search, insert, delete)
            collection: Vector collection name
            num_results: Number of results returned
        """
        self.vector_query_latency.labels(
            operation=operation,
            collection=collection
        ).observe(duration_seconds)

        if num_results > 0:
            self.vector_query_results.labels(
                operation=operation,
                collection=collection
            ).observe(num_results)

    def record_llm_call_rate(
        self,
        calls_per_min: float,
        model: str,
        operation: str
    ) -> None:
        """Record LLM call rate."""
        self.llm_calls_per_min.labels(
            model=model,
            operation=operation
        ).set(calls_per_min)

    def observe_llm_request(
        self,
        duration_seconds: float,
        model: str,
        operation: str,
        status: str,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> None:
        """
        Observe LLM request metrics.

        Args:
            duration_seconds: Request duration
            model: LLM model name
            operation: Operation type (recommend_sli, generate_artifact)
            status: Request status (success, error)
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        """
        self.llm_request_duration_seconds.labels(
            model=model,
            operation=operation,
            status=status
        ).observe(duration_seconds)

        if input_tokens > 0:
            self.llm_tokens_total.labels(
                model=model,
                operation=operation,
                token_type="input"
            ).inc(input_tokens)

        if output_tokens > 0:
            self.llm_tokens_total.labels(
                model=model,
                operation=operation,
                token_type="output"
            ).inc(output_tokens)

    def update_daily_llm_spend(
        self,
        spend_usd: float,
        model: str
    ) -> None:
        """Update estimated daily LLM spend."""
        self.daily_llm_spend_usd.labels(model=model).set(spend_usd)

    def observe_analysis_job(
        self,
        duration_seconds: float,
        service: str,
        status: str = "success"
    ) -> None:
        """Observe analysis job duration."""
        self.analysis_job_duration_seconds.labels(
            service=service,
            status=status
        ).observe(duration_seconds)

    def record_sli_recommendation(
        self,
        service: str,
        journey: str,
        sli_type: str,
        confidence_score: float
    ) -> None:
        """Record SLI recommendation generation."""
        self.sli_recommendations_total.labels(
            service=service,
            journey=journey,
            sli_type=sli_type
        ).inc()

        self.sli_confidence_score.labels(
            service=service,
            sli_type=sli_type
        ).observe(confidence_score)

    def record_artifact_generation(
        self,
        artifact_type: str,
        status: str = "success"
    ) -> None:
        """Record artifact generation."""
        self.artifact_generation_total.labels(
            artifact_type=artifact_type,
            status=status
        ).inc()

    def observe_artifact_validation(
        self,
        duration_seconds: float,
        artifact_type: str,
        validator: str
    ) -> None:
        """Observe artifact validation duration."""
        self.artifact_validation_duration_seconds.labels(
            artifact_type=artifact_type,
            validator=validator
        ).observe(duration_seconds)

    def observe_db_query(
        self,
        duration_seconds: float,
        database: str,
        operation: str,
        table: str
    ) -> None:
        """Observe database query duration."""
        self.db_query_duration_seconds.labels(
            database=database,
            operation=operation,
            table=table
        ).observe(duration_seconds)

    def update_db_connection_pool(
        self,
        pool_size: int,
        database: str,
        state: str = "active"
    ) -> None:
        """Update database connection pool metrics."""
        self.db_connection_pool_size.labels(
            database=database,
            state=state
        ).set(pool_size)

    def update_kafka_consumer_lag(
        self,
        lag: int,
        topic: str,
        consumer_group: str,
        partition: int
    ) -> None:
        """Update Kafka consumer lag."""
        self.kafka_consumer_lag.labels(
            topic=topic,
            consumer_group=consumer_group,
            partition=str(partition)
        ).set(lag)

    def record_kafka_message(
        self,
        topic: str,
        consumer_group: str,
        status: str = "success"
    ) -> None:
        """Record Kafka message consumption."""
        self.kafka_messages_consumed_total.labels(
            topic=topic,
            consumer_group=consumer_group,
            status=status
        ).inc()

    def observe_http_request(
        self,
        duration_seconds: float,
        method: str,
        endpoint: str,
        status: int
    ) -> None:
        """Observe HTTP request metrics."""
        status_str = str(status)

        self.http_request_duration_seconds.labels(
            method=method,
            endpoint=endpoint,
            status=status_str
        ).observe(duration_seconds)

        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status_str
        ).inc()

    def export(self) -> bytes:
        """
        Export metrics in Prometheus format.

        Returns:
            Prometheus-formatted metrics
        """
        return generate_latest(self.registry)

    def get_content_type(self) -> str:
        """Get Prometheus metrics content type."""
        return CONTENT_TYPE_LATEST


# Global metrics instance
_metrics_instance: Optional[SLOScoutMetrics] = None


def get_metrics() -> SLOScoutMetrics:
    """
    Get global metrics instance (singleton).

    Returns:
        SLOScoutMetrics instance
    """
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = SLOScoutMetrics()
    return _metrics_instance


def init_metrics(
    version: str = "1.0.0",
    environment: str = "production",
    deployment_id: str = "default",
    embedding_model: str = "all-MiniLM-L6-v2"
) -> SLOScoutMetrics:
    """
    Initialize global metrics instance with system info.

    Args:
        version: Application version
        environment: Deployment environment
        deployment_id: Unique deployment identifier
        embedding_model: Embedding model name

    Returns:
        Initialized SLOScoutMetrics instance
    """
    metrics = get_metrics()
    metrics.set_system_info(
        version=version,
        environment=environment,
        deployment_id=deployment_id,
        embedding_model=embedding_model
    )
    return metrics
