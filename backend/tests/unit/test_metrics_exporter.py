"""
Unit Tests for Prometheus Metrics Exporter (T142)

Tests SLO-Scout self-observability metrics implementation.
Per spec.md FR-024, FR-025, FR-026.
"""
import pytest
from prometheus_client import CollectorRegistry
from backend.src.observability.metrics import SLOScoutMetrics, get_metrics, init_metrics


class TestSLOScoutMetrics:
    """Test suite for SLOScoutMetrics class."""

    @pytest.fixture
    def metrics(self):
        """Create isolated metrics instance for testing."""
        registry = CollectorRegistry()
        return SLOScoutMetrics(registry=registry)

    def test_init_creates_all_metrics(self, metrics):
        """Test that all required metrics are created on initialization."""
        # Verify core metrics exist per FR-024
        assert metrics.ingest_lag_seconds is not None
        assert metrics.embedding_queue_length is not None
        assert metrics.vector_query_latency is not None
        assert metrics.llm_calls_per_min is not None
        assert metrics.daily_llm_spend_usd is not None

        # Verify supporting metrics
        assert metrics.analysis_job_duration_seconds is not None
        assert metrics.artifact_generation_total is not None
        assert metrics.kafka_consumer_lag is not None
        assert metrics.http_request_duration_seconds is not None

    def test_set_system_info(self, metrics):
        """Test system info can be set."""
        metrics.set_system_info(
            version="1.0.0",
            environment="test",
            deployment_id="test-123",
            embedding_model="all-MiniLM-L6-v2"
        )

        # Export and verify system info is included
        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_system_info' in exported
        assert 'version="1.0.0"' in exported
        assert 'environment="test"' in exported

    def test_record_ingest_lag(self, metrics):
        """Test recording ingest lag metrics."""
        metrics.record_ingest_lag(
            lag_seconds=45.5,
            service="test-service",
            environment="prod",
            telemetry_type="logs"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_ingest_lag_seconds' in exported
        assert 'service="test-service"' in exported
        assert 'telemetry_type="logs"' in exported
        assert '45.5' in exported

    def test_record_ingest_event(self, metrics):
        """Test recording ingest event counter."""
        metrics.record_ingest_event(
            service="test-service",
            environment="prod",
            telemetry_type="metrics",
            status="success"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_ingest_events_total' in exported
        assert 'status="success"' in exported

    def test_record_embedding_queue_length(self, metrics):
        """Test recording embedding queue length."""
        metrics.record_embedding_queue_length(
            queue_length=250,
            embedding_model="all-MiniLM-L6-v2"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_embedding_queue_length' in exported
        assert '250' in exported

    def test_observe_embedding_generation(self, metrics):
        """Test observing embedding generation duration."""
        metrics.observe_embedding_generation(
            duration_seconds=0.045,
            embedding_model="all-MiniLM-L6-v2"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_embedding_generation_duration_seconds' in exported

    def test_observe_vector_query(self, metrics):
        """Test observing vector query latency."""
        metrics.observe_vector_query(
            duration_seconds=0.125,
            operation="search",
            collection="capsules",
            num_results=10
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_vector_query_latency_seconds' in exported
        assert 'operation="search"' in exported
        assert 'slo_scout_vector_query_results' in exported

    def test_record_llm_call_rate(self, metrics):
        """Test recording LLM call rate."""
        metrics.record_llm_call_rate(
            calls_per_min=25.5,
            model="gpt-4",
            operation="recommend_sli"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_llm_calls_per_min' in exported
        assert '25.5' in exported

    def test_observe_llm_request(self, metrics):
        """Test observing LLM request metrics."""
        metrics.observe_llm_request(
            duration_seconds=2.5,
            model="gpt-4",
            operation="recommend_sli",
            status="success",
            input_tokens=1500,
            output_tokens=500
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_llm_request_duration_seconds' in exported
        assert 'slo_scout_llm_tokens_total' in exported
        assert 'token_type="input"' in exported
        assert 'token_type="output"' in exported

    def test_update_daily_llm_spend(self, metrics):
        """Test updating daily LLM spend."""
        metrics.update_daily_llm_spend(
            spend_usd=45.67,
            model="gpt-4"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_daily_llm_spend_usd' in exported
        assert '45.67' in exported

    def test_observe_analysis_job(self, metrics):
        """Test observing analysis job duration."""
        metrics.observe_analysis_job(
            duration_seconds=180.5,
            service="checkout-api",
            status="success"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_analysis_job_duration_seconds' in exported
        assert 'service="checkout-api"' in exported

    def test_record_sli_recommendation(self, metrics):
        """Test recording SLI recommendation."""
        metrics.record_sli_recommendation(
            service="checkout-api",
            journey="checkout_flow",
            sli_type="latency_p95",
            confidence_score=0.85
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_sli_recommendations_total' in exported
        assert 'slo_scout_sli_confidence_score' in exported
        assert 'sli_type="latency_p95"' in exported

    def test_record_artifact_generation(self, metrics):
        """Test recording artifact generation."""
        metrics.record_artifact_generation(
            artifact_type="prometheus_alert",
            status="success"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_artifact_generation_total' in exported
        assert 'artifact_type="prometheus_alert"' in exported

    def test_observe_artifact_validation(self, metrics):
        """Test observing artifact validation duration."""
        metrics.observe_artifact_validation(
            duration_seconds=1.2,
            artifact_type="grafana_dashboard",
            validator="grafana_schema"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_artifact_validation_duration_seconds' in exported
        assert 'validator="grafana_schema"' in exported

    def test_observe_db_query(self, metrics):
        """Test observing database query duration."""
        metrics.observe_db_query(
            duration_seconds=0.015,
            database="timescaledb",
            operation="select",
            table="sli"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_db_query_duration_seconds' in exported
        assert 'database="timescaledb"' in exported
        assert 'table="sli"' in exported

    def test_update_db_connection_pool(self, metrics):
        """Test updating database connection pool metrics."""
        metrics.update_db_connection_pool(
            pool_size=20,
            database="timescaledb",
            state="active"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_db_connection_pool_size' in exported
        assert 'state="active"' in exported
        assert '20' in exported

    def test_update_kafka_consumer_lag(self, metrics):
        """Test updating Kafka consumer lag."""
        metrics.update_kafka_consumer_lag(
            lag=1500,
            topic="capsule-events",
            consumer_group="capsule-consumer",
            partition=0
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_kafka_consumer_lag' in exported
        assert 'topic="capsule-events"' in exported
        assert 'partition="0"' in exported
        assert '1500' in exported

    def test_record_kafka_message(self, metrics):
        """Test recording Kafka message consumption."""
        metrics.record_kafka_message(
            topic="capsule-events",
            consumer_group="capsule-consumer",
            status="success"
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_kafka_messages_consumed_total' in exported
        assert 'status="success"' in exported

    def test_observe_http_request(self, metrics):
        """Test observing HTTP request metrics."""
        metrics.observe_http_request(
            duration_seconds=0.125,
            method="POST",
            endpoint="/api/v1/analyze",
            status=202
        )

        exported = metrics.export().decode('utf-8')
        assert 'slo_scout_http_request_duration_seconds' in exported
        assert 'slo_scout_http_requests_total' in exported
        assert 'method="POST"' in exported
        assert 'status="202"' in exported

    def test_export_prometheus_format(self, metrics):
        """Test that export produces valid Prometheus format."""
        metrics.set_system_info(
            version="1.0.0",
            environment="test",
            deployment_id="test-123"
        )

        exported = metrics.export().decode('utf-8')

        # Verify Prometheus format basics
        assert '# HELP' in exported
        assert '# TYPE' in exported

        # Verify content type
        assert metrics.get_content_type() == 'text/plain; version=0.0.4; charset=utf-8'

    def test_histogram_buckets_configured(self, metrics):
        """Test that histogram metrics have appropriate buckets."""
        # Record some observations
        metrics.observe_vector_query(0.01, "search", "capsules", 5)
        metrics.observe_vector_query(0.1, "search", "capsules", 10)
        metrics.observe_vector_query(1.5, "search", "capsules", 20)

        exported = metrics.export().decode('utf-8')

        # Verify histogram buckets are present
        assert 'le="0.01"' in exported
        assert 'le="0.1"' in exported
        assert 'le="2.0"' in exported
        assert 'le="+Inf"' in exported

    def test_labels_applied_correctly(self, metrics):
        """Test that metric labels are applied correctly."""
        metrics.record_ingest_lag(
            lag_seconds=30.0,
            service="payment-api",
            environment="staging",
            telemetry_type="traces"
        )

        exported = metrics.export().decode('utf-8')

        # Verify all labels are present
        assert 'service="payment-api"' in exported
        assert 'environment="staging"' in exported
        assert 'telemetry_type="traces"' in exported

    def test_multiple_metrics_coexist(self, metrics):
        """Test that multiple metrics can be recorded and exported together."""
        # Record various metrics
        metrics.record_ingest_lag(25.0, "svc1", "prod", "logs")
        metrics.record_embedding_queue_length(500)
        metrics.observe_vector_query(0.5, "search", "capsules", 10)
        metrics.observe_llm_request(2.0, "gpt-4", "recommend", "success", 1000, 200)
        metrics.observe_analysis_job(120.0, "svc1", "success")

        exported = metrics.export().decode('utf-8')

        # Verify all metrics are present
        assert 'slo_scout_ingest_lag_seconds' in exported
        assert 'slo_scout_embedding_queue_length' in exported
        assert 'slo_scout_vector_query_latency_seconds' in exported
        assert 'slo_scout_llm_request_duration_seconds' in exported
        assert 'slo_scout_analysis_job_duration_seconds' in exported


class TestMetricsGlobalInstance:
    """Test suite for global metrics instance management."""

    def test_get_metrics_singleton(self):
        """Test that get_metrics returns singleton instance."""
        metrics1 = get_metrics()
        metrics2 = get_metrics()

        assert metrics1 is metrics2

    def test_init_metrics_sets_system_info(self):
        """Test that init_metrics properly initializes system info."""
        metrics = init_metrics(
            version="2.0.0",
            environment="production",
            deployment_id="prod-us-east-1",
            embedding_model="text-embedding-ada-002"
        )

        exported = metrics.export().decode('utf-8')

        assert 'version="2.0.0"' in exported
        assert 'environment="production"' in exported
        assert 'deployment_id="prod-us-east-1"' in exported
        assert 'embedding_model="text-embedding-ada-002"' in exported


class TestMetricsIntegrationScenarios:
    """Integration test scenarios for metrics usage."""

    @pytest.fixture
    def metrics(self):
        """Create isolated metrics instance."""
        registry = CollectorRegistry()
        return SLOScoutMetrics(registry=registry)

    def test_ingest_pipeline_workflow(self, metrics):
        """Test complete ingest pipeline metrics workflow."""
        # Simulate telemetry ingestion
        metrics.record_ingest_event("api", "prod", "logs", "success")
        metrics.record_ingest_lag(15.5, "api", "prod", "logs")

        # Simulate Kafka consumption
        metrics.update_kafka_consumer_lag(500, "raw-telemetry", "ingest-consumer", 0)
        metrics.record_kafka_message("raw-telemetry", "ingest-consumer", "success")

        # Simulate database write
        metrics.observe_db_query(0.008, "timescaledb", "insert", "capsule")

        exported = metrics.export().decode('utf-8')

        # Verify complete workflow is captured
        assert 'slo_scout_ingest_events_total' in exported
        assert 'slo_scout_ingest_lag_seconds' in exported
        assert 'slo_scout_kafka_consumer_lag' in exported
        assert 'slo_scout_db_query_duration_seconds' in exported

    def test_analysis_workflow(self, metrics):
        """Test complete analysis workflow metrics."""
        # Simulate analysis job start
        job_start = 0.0

        # Vector search
        metrics.observe_vector_query(0.15, "search", "capsules", 20)

        # LLM recommendation
        metrics.observe_llm_request(3.5, "gpt-4", "recommend_sli", "success", 2000, 800)
        metrics.record_llm_call_rate(15.0, "gpt-4", "recommend_sli")

        # SLI recommendation
        metrics.record_sli_recommendation("api", "checkout", "latency_p95", 0.92)

        # Analysis complete
        metrics.observe_analysis_job(180.0, "api", "success")

        exported = metrics.export().decode('utf-8')

        # Verify analysis metrics
        assert 'slo_scout_vector_query_latency_seconds' in exported
        assert 'slo_scout_llm_request_duration_seconds' in exported
        assert 'slo_scout_sli_recommendations_total' in exported
        assert 'slo_scout_analysis_job_duration_seconds' in exported

    def test_artifact_generation_workflow(self, metrics):
        """Test artifact generation workflow metrics."""
        # Generate Prometheus alert
        metrics.record_artifact_generation("prometheus_alert", "success")
        metrics.observe_artifact_validation(0.5, "prometheus_alert", "promtool")

        # Generate Grafana dashboard
        metrics.record_artifact_generation("grafana_dashboard", "success")
        metrics.observe_artifact_validation(0.3, "grafana_dashboard", "grafana_schema")

        # Generate runbook
        metrics.record_artifact_generation("runbook", "success")
        metrics.observe_artifact_validation(0.1, "runbook", "yaml_validator")

        exported = metrics.export().decode('utf-8')

        # Verify artifact metrics
        assert 'artifact_type="prometheus_alert"' in exported
        assert 'artifact_type="grafana_dashboard"' in exported
        assert 'artifact_type="runbook"' in exported

    def test_slo_breach_detection(self, metrics):
        """Test metrics that would indicate SLO breaches."""
        # Simulate high ingest lag (> 60s SLO)
        metrics.record_ingest_lag(75.0, "api", "prod", "logs")

        # Simulate slow vector queries (> 2s SLO)
        metrics.observe_vector_query(2.5, "search", "capsules", 10)

        # Simulate long analysis (> 300s SLO)
        metrics.observe_analysis_job(350.0, "api", "success")

        exported = metrics.export().decode('utf-8')

        # Verify breach-indicating values
        assert '75' in exported  # Ingest lag
        assert '2.5' in exported or '350' in exported  # Query or analysis duration
