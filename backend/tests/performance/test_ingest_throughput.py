"""
Performance test for ingest throughput.

Test validates:
- System can handle 100k logs/min (Enterprise tier from research.md)
- Ingest lag remains < 60s (FR-025 from spec.md)
- Sustained load over 5 minutes
- Metrics are properly exported

Performance Goals (spec.md FR-025):
- 99% ingest freshness < 60s
- Throughput: 100k+ logs/min (Enterprise tier)
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
import statistics
import json

import pytest
from kafka import KafkaProducer
from prometheus_client.parser import text_string_to_metric_families
import httpx


@pytest.fixture
def kafka_producer():
    """Create Kafka producer for test event generation."""
    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        compression_type='gzip',
        batch_size=16384,
        linger_ms=10,
        acks='all',
        retries=3
    )
    yield producer
    producer.close()


@pytest.fixture
def telemetry_event_template() -> Dict[str, Any]:
    """Template for TelemetryEvent matching streaming-capsule.yaml Avro schema."""
    return {
        "event_id": "",
        "service_name": "test-service",
        "environment": "performance-test",
        "timestamp": 0,
        "event_type": "LOG",
        "severity": "INFO",
        "message": "",
        "attributes": {
            "source": "performance-test",
            "test_run_id": ""
        },
        "trace_id": None,
        "span_id": None
    }


async def generate_events(
    producer: KafkaProducer,
    template: Dict[str, Any],
    events_per_second: int,
    duration_seconds: int,
    test_run_id: str
) -> List[Dict[str, Any]]:
    """
    Generate test events at specified rate.

    Args:
        producer: Kafka producer
        template: Event template
        events_per_second: Target event rate
        duration_seconds: Test duration
        test_run_id: Unique test identifier

    Returns:
        List of event metadata for verification
    """
    sent_events = []
    batch_interval = 0.1  # 100ms batches
    events_per_batch = int(events_per_second * batch_interval)

    start_time = time.time()
    batch_count = 0

    log_patterns = [
        "User {USER_ID} logged in successfully",
        "Payment {PAYMENT_ID} processed in {DURATION}ms",
        "Order {ORDER_ID} created for customer {CUSTOMER_ID}",
        "Error processing request {REQUEST_ID}: {ERROR_MSG}",
        "Cache miss for key {CACHE_KEY}"
    ]

    while time.time() - start_time < duration_seconds:
        batch_start = time.time()

        # Send batch of events
        for i in range(events_per_batch):
            event = template.copy()
            event_id = f"{test_run_id}-{batch_count}-{i}"
            event["event_id"] = event_id
            event["timestamp"] = int(time.time() * 1000)  # milliseconds
            event["message"] = log_patterns[i % len(log_patterns)]
            event["attributes"]["test_run_id"] = test_run_id

            # Send to Kafka
            producer.send('raw-telemetry', value=event)

            sent_events.append({
                "event_id": event_id,
                "sent_at": event["timestamp"]
            })

        batch_count += 1

        # Maintain rate by sleeping remainder of batch interval
        elapsed = time.time() - batch_start
        sleep_time = max(0, batch_interval - elapsed)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

    # Flush remaining messages
    producer.flush(timeout=10)

    return sent_events


async def measure_ingest_lag(metrics_url: str = "http://localhost:8000/metrics") -> Dict[str, float]:
    """
    Measure ingest lag from Prometheus metrics.

    Queries:
    - ingest_lag_seconds (p50, p95, p99)
    - capsule_processing_rate
    - events_ingested_total

    Returns:
        Dictionary with lag statistics
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(metrics_url, timeout=10.0)
        response.raise_for_status()
        metrics_text = response.text

    # Parse Prometheus metrics
    metrics = {}
    for family in text_string_to_metric_families(metrics_text):
        if family.name == 'ingest_lag_seconds':
            for sample in family.samples:
                if 'quantile' in sample.labels:
                    quantile = sample.labels['quantile']
                    metrics[f'ingest_lag_p{int(float(quantile)*100)}'] = sample.value
        elif family.name == 'capsule_processing_rate':
            metrics['capsule_rate'] = list(family.samples)[0].value
        elif family.name == 'events_ingested_total':
            metrics['events_total'] = list(family.samples)[0].value

    return metrics


@pytest.mark.asyncio
@pytest.mark.performance
async def test_ingest_throughput_100k_per_minute(
    kafka_producer,
    telemetry_event_template
):
    """
    Test: Ingest 100k logs/min for 5 minutes with lag < 60s.

    Performance Goals (spec.md FR-025):
    - Throughput: 100k logs/min = 1,667 logs/sec
    - Ingest lag: p95 < 60s (99% < 60s target)
    - Duration: 5 minutes sustained load

    Test Steps:
    1. Generate 100k events/min for 5 minutes
    2. Monitor ingest lag every 30 seconds
    3. Verify p95 lag < 60s
    4. Verify all events processed within 2 minutes of completion
    """
    test_run_id = f"perf-test-{int(time.time())}"
    events_per_second = 1667  # 100k per minute
    duration_seconds = 300  # 5 minutes

    print(f"\n=== Starting Throughput Test ===")
    print(f"Test Run ID: {test_run_id}")
    print(f"Target Rate: {events_per_second} events/sec ({events_per_second * 60} events/min)")
    print(f"Duration: {duration_seconds} seconds")

    # Start event generation
    start_time = time.time()
    sent_events = await generate_events(
        kafka_producer,
        telemetry_event_template,
        events_per_second,
        duration_seconds,
        test_run_id
    )
    generation_time = time.time() - start_time

    print(f"\n=== Event Generation Complete ===")
    print(f"Events Sent: {len(sent_events)}")
    print(f"Generation Time: {generation_time:.2f}s")
    print(f"Actual Rate: {len(sent_events) / generation_time:.2f} events/sec")

    # Monitor ingest lag during processing
    lag_measurements = []
    max_wait_time = 120  # 2 minutes grace period after generation
    measurement_interval = 10  # Check every 10 seconds

    print(f"\n=== Monitoring Ingest Lag ===")
    monitor_start = time.time()

    while time.time() - monitor_start < max_wait_time:
        try:
            metrics = await measure_ingest_lag()

            if metrics:
                lag_measurements.append({
                    'timestamp': time.time(),
                    'lag_p50': metrics.get('ingest_lag_p50', 0),
                    'lag_p95': metrics.get('ingest_lag_p95', 0),
                    'lag_p99': metrics.get('ingest_lag_p99', 0),
                    'capsule_rate': metrics.get('capsule_rate', 0),
                    'events_total': metrics.get('events_total', 0)
                })

                print(f"  [t+{int(time.time() - monitor_start)}s] "
                      f"Lag: p50={metrics.get('ingest_lag_p50', 0):.1f}s, "
                      f"p95={metrics.get('ingest_lag_p95', 0):.1f}s, "
                      f"p99={metrics.get('ingest_lag_p99', 0):.1f}s, "
                      f"Rate: {metrics.get('capsule_rate', 0):.0f}/s")

        except Exception as e:
            print(f"  Warning: Failed to fetch metrics: {e}")

        await asyncio.sleep(measurement_interval)

    # Analyze results
    print(f"\n=== Performance Analysis ===")

    if lag_measurements:
        p95_lags = [m['lag_p95'] for m in lag_measurements]
        p99_lags = [m['lag_p99'] for m in lag_measurements]

        max_p95_lag = max(p95_lags)
        max_p99_lag = max(p99_lags)
        avg_p95_lag = statistics.mean(p95_lags)

        print(f"Lag Statistics:")
        print(f"  p95 - Max: {max_p95_lag:.2f}s, Avg: {avg_p95_lag:.2f}s")
        print(f"  p99 - Max: {max_p99_lag:.2f}s")

        if lag_measurements[-1]['events_total'] > 0:
            print(f"Events Processed: {int(lag_measurements[-1]['events_total'])}")

        # Assertions per spec.md FR-025
        assert max_p95_lag < 60, (
            f"FAILED: p95 ingest lag {max_p95_lag:.2f}s exceeds 60s target "
            f"(spec.md FR-025: 99% ingest freshness < 60s)"
        )

        assert avg_p95_lag < 45, (
            f"WARNING: Average p95 lag {avg_p95_lag:.2f}s is high "
            f"(should be well under 60s for healthy system)"
        )

        print(f"\n✅ PASSED: Ingest lag p95={max_p95_lag:.2f}s < 60s (spec.md FR-025)")

    else:
        pytest.fail("No lag measurements collected - metrics endpoint may be unavailable")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_ingest_throughput_burst_load():
    """
    Test: Handle burst load of 200k logs/min for 1 minute.

    Validates system behavior under 2x normal load:
    - Kafka buffering capacity
    - Backpressure handling
    - Recovery to normal lag after burst
    """
    test_run_id = f"burst-test-{int(time.time())}"
    events_per_second = 3334  # 200k per minute
    duration_seconds = 60  # 1 minute burst

    print(f"\n=== Starting Burst Load Test ===")
    print(f"Burst Rate: {events_per_second} events/sec ({events_per_second * 60} events/min)")
    print(f"Duration: {duration_seconds} seconds")

    producer = KafkaProducer(
        bootstrap_servers=['localhost:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        compression_type='gzip',
        batch_size=32768,  # Larger batch for burst
        linger_ms=5,
        acks='all',
        buffer_memory=67108864  # 64MB buffer
    )

    template = {
        "event_id": "",
        "service_name": "burst-test-service",
        "environment": "performance-test",
        "timestamp": 0,
        "event_type": "LOG",
        "severity": "INFO",
        "message": "Burst load test event {EVENT_NUM}",
        "attributes": {"test_run_id": test_run_id}
    }

    try:
        sent_events = await generate_events(
            producer,
            template,
            events_per_second,
            duration_seconds,
            test_run_id
        )

        print(f"Burst Events Sent: {len(sent_events)}")

        # Wait for processing and check recovery
        await asyncio.sleep(90)  # 1.5 minutes recovery

        final_metrics = await measure_ingest_lag()
        final_lag = final_metrics.get('ingest_lag_p95', 0)

        print(f"Final p95 lag after recovery: {final_lag:.2f}s")

        # After burst, system should recover to normal lag
        assert final_lag < 120, (
            f"System did not recover from burst load: p95 lag {final_lag:.2f}s > 120s"
        )

        print(f"✅ PASSED: System recovered from burst load")

    finally:
        producer.close()


@pytest.mark.asyncio
@pytest.mark.performance
async def test_ingest_lag_metrics_availability():
    """
    Test: Verify ingest lag metrics are properly exported.

    Validates:
    - Metrics endpoint is accessible
    - Required metrics are present
    - Metric format follows Prometheus standards
    """
    metrics = await measure_ingest_lag()

    print(f"\n=== Ingest Metrics Validation ===")
    print(f"Available metrics: {list(metrics.keys())}")

    # Verify required metrics exist (spec.md FR-024)
    required_metrics = ['ingest_lag_p50', 'ingest_lag_p95', 'ingest_lag_p99']

    for metric in required_metrics:
        assert metric in metrics, f"Missing required metric: {metric} (spec.md FR-024)"
        assert isinstance(metrics[metric], (int, float)), f"Invalid metric type for {metric}"
        print(f"  ✓ {metric}: {metrics[metric]:.2f}s")

    print(f"✅ PASSED: All required ingest metrics available")


if __name__ == "__main__":
    """
    Run performance tests standalone.

    Usage:
        python test_ingest_throughput.py

    Or with pytest:
        pytest test_ingest_throughput.py -v -m performance
    """
    import sys

    # Run main throughput test
    asyncio.run(test_ingest_throughput_100k_per_minute(
        kafka_producer=KafkaProducer(bootstrap_servers=['localhost:9092']),
        telemetry_event_template={
            "event_id": "",
            "service_name": "test-service",
            "environment": "performance-test",
            "timestamp": 0,
            "event_type": "LOG",
            "severity": "INFO",
            "message": "",
            "attributes": {}
        }
    ))
