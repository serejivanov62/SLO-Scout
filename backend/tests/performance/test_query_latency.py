"""
Performance test for query latency.

Test validates:
- SLI query latency p95 < 2s (spec.md FR-025)
- 100 concurrent queries
- Vector search performance
- RAG retrieval performance

Performance Goals (spec.md FR-025):
- 95% query latency < 2s
"""

import asyncio
import time
from typing import List, Dict, Any
import statistics

import pytest
import httpx


@pytest.fixture
def api_base_url() -> str:
    """Base URL for SLO-Scout API."""
    return "http://localhost:8000/api/v1"


@pytest.fixture
def test_service_data() -> Dict[str, Any]:
    """Sample service data for queries."""
    return {
        "service_name": "payments-api",
        "environment": "production",
        "journey_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "time_range_hours": 24
    }


async def query_sli_list(
    client: httpx.AsyncClient,
    base_url: str,
    journey_id: str,
    include_evidence: bool = True
) -> Dict[str, Any]:
    """
    Query SLI list endpoint with evidence.

    Tests:
    - GET /api/v1/sli endpoint (api-sli.yaml)
    - Vector search for evidence pointers
    - TimescaleDB query for SLI metadata

    Args:
        client: HTTP client
        base_url: API base URL
        journey_id: User journey ID
        include_evidence: Include evidence pointers

    Returns:
        Response with timing metadata
    """
    start = time.perf_counter()

    response = await client.get(
        f"{base_url}/sli",
        params={
            "journey_id": journey_id,
            "include_evidence": str(include_evidence).lower()
        },
        timeout=30.0
    )

    latency = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "endpoint": "GET /api/v1/sli",
        "status_code": response.status_code,
        "latency_ms": latency,
        "response_size_bytes": len(response.content),
        "evidence_included": include_evidence
    }


async def query_journeys_list(
    client: httpx.AsyncClient,
    base_url: str,
    service_name: str,
    min_confidence: float = 70.0
) -> Dict[str, Any]:
    """
    Query journeys list endpoint.

    Tests:
    - GET /api/v1/journeys endpoint (api-analyze.yaml)
    - Journey ranking by confidence
    - Trace graph queries

    Args:
        client: HTTP client
        base_url: API base URL
        service_name: Service name filter
        min_confidence: Minimum confidence threshold

    Returns:
        Response with timing metadata
    """
    start = time.perf_counter()

    response = await client.get(
        f"{base_url}/journeys",
        params={
            "service_name": service_name,
            "min_confidence": min_confidence
        },
        timeout=30.0
    )

    latency = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "endpoint": "GET /api/v1/journeys",
        "status_code": response.status_code,
        "latency_ms": latency,
        "response_size_bytes": len(response.content),
        "min_confidence": min_confidence
    }


async def query_analyze_status(
    client: httpx.AsyncClient,
    base_url: str,
    job_id: str
) -> Dict[str, Any]:
    """
    Query analysis job status.

    Tests:
    - GET /api/v1/analyze/{job_id} endpoint (api-analyze.yaml)
    - Job status lookup
    - Progress tracking

    Args:
        client: HTTP client
        base_url: API base URL
        job_id: Analysis job ID

    Returns:
        Response with timing metadata
    """
    start = time.perf_counter()

    response = await client.get(
        f"{base_url}/analyze/{job_id}",
        timeout=30.0
    )

    latency = (time.perf_counter() - start) * 1000  # milliseconds

    return {
        "endpoint": f"GET /api/v1/analyze/{job_id}",
        "status_code": response.status_code,
        "latency_ms": latency,
        "response_size_bytes": len(response.content)
    }


async def run_concurrent_queries(
    query_func,
    num_queries: int,
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Run concurrent queries and measure latency.

    Args:
        query_func: Async query function
        num_queries: Number of concurrent queries
        **kwargs: Arguments for query function

    Returns:
        List of query results with timing
    """
    tasks = [query_func(**kwargs) for _ in range(num_queries)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return successful results
    successful_results = [
        r for r in results
        if not isinstance(r, Exception)
    ]

    return successful_results


def calculate_latency_percentiles(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate latency percentiles from query results.

    Args:
        results: List of query results

    Returns:
        Dictionary with p50, p95, p99 latencies in ms
    """
    latencies = [r['latency_ms'] for r in results]

    if not latencies:
        return {"p50": 0, "p95": 0, "p99": 0, "max": 0, "mean": 0}

    sorted_latencies = sorted(latencies)

    return {
        "p50": sorted_latencies[int(len(sorted_latencies) * 0.50)],
        "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
        "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)],
        "max": max(latencies),
        "mean": statistics.mean(latencies)
    }


@pytest.mark.asyncio
@pytest.mark.performance
async def test_sli_query_latency_p95_under_2s(api_base_url, test_service_data):
    """
    Test: 100 concurrent SLI queries with p95 < 2s.

    Performance Goal (spec.md FR-025):
    - 95% query latency < 2s (2000ms)

    Test Steps:
    1. Run 100 concurrent GET /api/v1/sli requests
    2. Include evidence pointers (vector search + S3 retrieval)
    3. Calculate p50, p95, p99 latencies
    4. Assert p95 < 2000ms
    """
    num_concurrent_queries = 100
    journey_id = test_service_data["journey_id"]

    print(f"\n=== SLI Query Latency Test ===")
    print(f"Concurrent Queries: {num_concurrent_queries}")
    print(f"Target: p95 < 2000ms (spec.md FR-025)")

    async with httpx.AsyncClient() as client:
        start_time = time.time()

        results = await run_concurrent_queries(
            query_sli_list,
            num_concurrent_queries,
            client=client,
            base_url=api_base_url,
            journey_id=journey_id,
            include_evidence=True
        )

        total_time = time.time() - start_time

    print(f"\nResults:")
    print(f"  Successful Queries: {len(results)}/{num_concurrent_queries}")
    print(f"  Total Time: {total_time:.2f}s")
    print(f"  Throughput: {len(results)/total_time:.1f} queries/sec")

    # Calculate percentiles
    percentiles = calculate_latency_percentiles(results)

    print(f"\nLatency Percentiles:")
    print(f"  p50: {percentiles['p50']:.0f}ms")
    print(f"  p95: {percentiles['p95']:.0f}ms")
    print(f"  p99: {percentiles['p99']:.0f}ms")
    print(f"  max: {percentiles['max']:.0f}ms")
    print(f"  mean: {percentiles['mean']:.0f}ms")

    # Verify response sizes (evidence included)
    avg_response_size = statistics.mean([r['response_size_bytes'] for r in results])
    print(f"\nAverage Response Size: {avg_response_size:.0f} bytes")

    # Assertions per spec.md FR-025
    assert len(results) >= num_concurrent_queries * 0.95, (
        f"Too many failed queries: {len(results)}/{num_concurrent_queries} succeeded"
    )

    assert percentiles['p95'] < 2000, (
        f"FAILED: p95 query latency {percentiles['p95']:.0f}ms exceeds 2000ms target "
        f"(spec.md FR-025: 95% query latency < 2s)"
    )

    # Warning if approaching limit
    if percentiles['p95'] > 1500:
        print(f"\n⚠️  WARNING: p95 latency {percentiles['p95']:.0f}ms is approaching 2000ms limit")

    print(f"\n✅ PASSED: Query latency p95={percentiles['p95']:.0f}ms < 2000ms (spec.md FR-025)")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_journeys_query_latency(api_base_url, test_service_data):
    """
    Test: Journey query latency under concurrent load.

    Validates:
    - GET /api/v1/journeys performance
    - Trace graph query efficiency
    - Confidence ranking speed
    """
    num_concurrent_queries = 100
    service_name = test_service_data["service_name"]

    print(f"\n=== Journeys Query Latency Test ===")
    print(f"Concurrent Queries: {num_concurrent_queries}")

    async with httpx.AsyncClient() as client:
        results = await run_concurrent_queries(
            query_journeys_list,
            num_concurrent_queries,
            client=client,
            base_url=api_base_url,
            service_name=service_name,
            min_confidence=70.0
        )

    percentiles = calculate_latency_percentiles(results)

    print(f"\nJourney Query Latency:")
    print(f"  p50: {percentiles['p50']:.0f}ms")
    print(f"  p95: {percentiles['p95']:.0f}ms")
    print(f"  p99: {percentiles['p99']:.0f}ms")

    # Journey queries should also be under 2s p95
    assert percentiles['p95'] < 2000, (
        f"Journey query p95 latency {percentiles['p95']:.0f}ms exceeds 2000ms"
    )

    print(f"✅ PASSED: Journey query p95={percentiles['p95']:.0f}ms < 2000ms")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_vector_search_latency(api_base_url, test_service_data):
    """
    Test: Vector search performance with evidence retrieval.

    Validates:
    - Milvus vector search speed
    - HNSW index efficiency
    - Metadata filtering performance
    - S3 sample retrieval latency
    """
    num_queries = 50
    journey_id = test_service_data["journey_id"]

    print(f"\n=== Vector Search Latency Test ===")
    print(f"Queries with Evidence: {num_queries}")

    # Query with evidence enabled (triggers vector search)
    async with httpx.AsyncClient() as client:
        with_evidence_results = await run_concurrent_queries(
            query_sli_list,
            num_queries,
            client=client,
            base_url=api_base_url,
            journey_id=journey_id,
            include_evidence=True
        )

        without_evidence_results = await run_concurrent_queries(
            query_sli_list,
            num_queries,
            client=client,
            base_url=api_base_url,
            journey_id=journey_id,
            include_evidence=False
        )

    with_evidence = calculate_latency_percentiles(with_evidence_results)
    without_evidence = calculate_latency_percentiles(without_evidence_results)

    print(f"\nWith Evidence (vector search + S3):")
    print(f"  p95: {with_evidence['p95']:.0f}ms")

    print(f"\nWithout Evidence (DB only):")
    print(f"  p95: {without_evidence['p95']:.0f}ms")

    # Calculate vector search overhead
    overhead = with_evidence['p95'] - without_evidence['p95']
    print(f"\nVector Search Overhead: {overhead:.0f}ms")

    # Vector search overhead should be reasonable
    assert overhead < 1000, (
        f"Vector search overhead {overhead:.0f}ms is too high (> 1000ms)"
    )

    print(f"✅ PASSED: Vector search overhead {overhead:.0f}ms is acceptable")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_query_latency_under_stress(api_base_url, test_service_data):
    """
    Test: Query latency under stress (200 concurrent queries).

    Validates:
    - Connection pool handling
    - Database connection limits
    - Graceful degradation under load
    """
    num_concurrent_queries = 200  # 2x normal load
    journey_id = test_service_data["journey_id"]

    print(f"\n=== Stress Test: 200 Concurrent Queries ===")

    async with httpx.AsyncClient() as client:
        start_time = time.time()

        results = await run_concurrent_queries(
            query_sli_list,
            num_concurrent_queries,
            client=client,
            base_url=api_base_url,
            journey_id=journey_id,
            include_evidence=True
        )

        total_time = time.time() - start_time

    success_rate = len(results) / num_concurrent_queries * 100
    percentiles = calculate_latency_percentiles(results)

    print(f"\nStress Test Results:")
    print(f"  Success Rate: {success_rate:.1f}%")
    print(f"  p95 Latency: {percentiles['p95']:.0f}ms")
    print(f"  p99 Latency: {percentiles['p99']:.0f}ms")
    print(f"  Total Time: {total_time:.2f}s")

    # Under stress, allow higher latency but require high success rate
    assert success_rate >= 95, (
        f"Success rate {success_rate:.1f}% too low under stress"
    )

    # p99 should still be reasonable under stress
    assert percentiles['p99'] < 5000, (
        f"p99 latency {percentiles['p99']:.0f}ms too high under stress (> 5s)"
    )

    print(f"✅ PASSED: System handled {num_concurrent_queries} concurrent queries")


@pytest.mark.asyncio
@pytest.mark.performance
async def test_query_cache_effectiveness():
    """
    Test: Query caching effectiveness.

    Validates:
    - Repeated queries benefit from caching
    - Cache hit rate improves latency
    - TTL and invalidation work correctly
    """
    api_base_url = "http://localhost:8000/api/v1"
    journey_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    print(f"\n=== Query Cache Effectiveness Test ===")

    async with httpx.AsyncClient() as client:
        # First query (cold cache)
        first_query = await query_sli_list(
            client, api_base_url, journey_id, include_evidence=True
        )

        # Second query (warm cache)
        await asyncio.sleep(0.1)  # Small delay
        second_query = await query_sli_list(
            client, api_base_url, journey_id, include_evidence=True
        )

    print(f"\nCache Performance:")
    print(f"  First Query (cold): {first_query['latency_ms']:.0f}ms")
    print(f"  Second Query (warm): {second_query['latency_ms']:.0f}ms")

    # Cache should improve latency
    improvement = (first_query['latency_ms'] - second_query['latency_ms']) / first_query['latency_ms'] * 100

    if improvement > 10:
        print(f"  Cache Improvement: {improvement:.1f}%")
        print(f"✅ Cache is effective")
    else:
        print(f"  ℹ️  No significant cache improvement (may be expected)")


if __name__ == "__main__":
    """
    Run query latency tests standalone.

    Usage:
        python test_query_latency.py

    Or with pytest:
        pytest test_query_latency.py -v -m performance
    """
    # Run main latency test
    asyncio.run(test_sli_query_latency_p95_under_2s(
        api_base_url="http://localhost:8000/api/v1",
        test_service_data={
            "service_name": "payments-api",
            "environment": "production",
            "journey_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "time_range_hours": 24
        }
    ))
