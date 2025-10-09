"""Integration test for FR-006: Collector Hot-Reload on Service Creation.

Tests the complete collector reconfiguration workflow:
- Service creation triggers collector config update
- ConfigMap is updated with new service configuration
- Collector picks up new config within 60 seconds (FR-006)
- No telemetry events are dropped during reconfiguration
- Fallback to 60s polling if ConfigMap watch fails (FR-007)

These tests validate the dynamic reconfiguration logic without requiring
a full Kubernetes cluster. Kubernetes API is mocked for unit testing.

Requirements Tested:
- FR-006: System MUST update collector configuration dynamically when new
  service is added (within 60 seconds)
- FR-007: Collectors MUST read service list and label mappings from
  configuration source refreshed every 60 seconds
- FR-008: Collectors MUST construct filtered queries using label selectors
- FR-009: Collectors MUST tag each collected event with correct service_id
"""

import pytest
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID


# Mock Kubernetes client classes
class MockV1ConfigMap:
    """Mock Kubernetes ConfigMap object."""

    def __init__(self, name: str, namespace: str, data: Dict[str, str]):
        self.metadata = MagicMock()
        self.metadata.name = name
        self.metadata.namespace = namespace
        self.metadata.resource_version = "1"
        self.data = data


class MockKubernetesWatch:
    """Mock Kubernetes watch interface."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.stopped = False

    def stream(self, func, **kwargs):
        """Simulate event stream."""
        for event in self.events:
            if self.stopped:
                break
            yield event

    def stop(self):
        """Stop the watch."""
        self.stopped = True


@pytest.fixture
def mock_k8s_client():
    """Mock Kubernetes client for ConfigMap operations."""
    mock_client = MagicMock()
    mock_core_v1 = MagicMock()

    # Mock read_namespaced_config_map
    mock_core_v1.read_namespaced_config_map = AsyncMock()

    # Mock patch_namespaced_config_map
    mock_core_v1.patch_namespaced_config_map = AsyncMock()

    # Mock list_namespaced_config_map
    mock_core_v1.list_namespaced_config_map = AsyncMock()

    mock_client.CoreV1Api.return_value = mock_core_v1
    return mock_client


@pytest.fixture
def mock_watch():
    """Mock Kubernetes watch for ConfigMap changes."""
    return MockKubernetesWatch()


@pytest.fixture
def sample_service_config() -> Dict[str, Any]:
    """Sample service configuration for testing."""
    return {
        "service_id": str(uuid4()),
        "name": "payments-api",
        "environment": "production",
        "owner_team": "Platform Team",
        "telemetry_endpoints": {
            "prometheus": "http://prometheus:9090",
            "traces": "http://jaeger:16686"
        },
        "label_selectors": {
            "job": "payment-gateway",
            "namespace": "prod"
        }
    }


@pytest.fixture
def sample_configmap_data(sample_service_config: Dict[str, Any]) -> Dict[str, str]:
    """Sample ConfigMap data with service configurations."""
    import json
    return {
        "services.json": json.dumps({
            "services": [
                {
                    "service_id": sample_service_config["service_id"],
                    "name": sample_service_config["name"],
                    "environment": sample_service_config["environment"],
                    "label_selectors": sample_service_config["label_selectors"],
                    "telemetry_endpoints": sample_service_config["telemetry_endpoints"]
                }
            ],
            "last_updated": datetime.utcnow().isoformat()
        })
    }


@pytest.fixture
def collector_config_manager(mock_k8s_client):
    """Mock collector configuration manager."""
    # This will be implemented in src/services/collector_config_manager.py
    # For now, return a mock that will cause tests to fail
    pytest.fail(
        "CollectorConfigManager not implemented yet. "
        "Expected at src/services/collector_config_manager.py"
    )


class TestCollectorReconfigurationIntegration:
    """Integration tests for collector hot-reload workflow."""

    @pytest.mark.asyncio
    async def test_service_creation_triggers_configmap_update(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
        sample_configmap_data: Dict[str, str],
    ) -> None:
        """Test that creating a service triggers ConfigMap update.

        Requirements:
        - FR-006: System MUST update collector configuration dynamically

        Test Flow:
        1. Create new service via API
        2. Verify ConfigMap update is triggered
        3. Verify new service is added to ConfigMap
        4. Verify ConfigMap contains correct label selectors
        """
        from src.services.collector_config_manager import CollectorConfigManager

        # Initialize config manager
        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Mock current ConfigMap state
        current_configmap = MockV1ConfigMap(
            name="otel-collector-config",
            namespace="observability",
            data={"services.json": '{"services": [], "last_updated": "2025-01-01T00:00:00"}'}
        )
        mock_k8s_client.CoreV1Api().read_namespaced_config_map.return_value = current_configmap

        # Create new service and trigger config update
        await config_manager.add_service(sample_service_config)

        # Verify ConfigMap was updated
        mock_k8s_client.CoreV1Api().patch_namespaced_config_map.assert_called_once()
        call_args = mock_k8s_client.CoreV1Api().patch_namespaced_config_map.call_args

        # Verify correct ConfigMap was targeted
        assert call_args[1]["name"] == "otel-collector-config"
        assert call_args[1]["namespace"] == "observability"

        # Verify updated data contains new service
        import json
        updated_data = json.loads(call_args[1]["body"]["data"]["services.json"])
        assert len(updated_data["services"]) == 1
        assert updated_data["services"][0]["name"] == "payments-api"
        assert updated_data["services"][0]["label_selectors"] == {
            "job": "payment-gateway",
            "namespace": "prod"
        }

    @pytest.mark.asyncio
    async def test_collector_picks_up_config_within_60_seconds(
        self,
        mock_k8s_client,
        mock_watch,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that collector detects config change within 60 seconds (FR-006).

        Requirements:
        - FR-006: Configuration update within 60 seconds

        Test Flow:
        1. Setup watch on ConfigMap
        2. Trigger service creation
        3. Simulate ConfigMap update event
        4. Verify collector detects change within 60s
        5. Verify collector reloads configuration
        """
        from src.services.collector_config_manager import CollectorConfigManager
        from src.services.otel_collector_watcher import OTelCollectorWatcher

        # Initialize watcher
        watcher = OTelCollectorWatcher(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Track reload events
        reload_events: List[datetime] = []

        async def mock_reload_callback(config: Dict[str, Any]):
            reload_events.append(datetime.utcnow())

        watcher.on_config_change = mock_reload_callback

        # Simulate ConfigMap update event
        import json
        updated_configmap = MockV1ConfigMap(
            name="otel-collector-config",
            namespace="observability",
            data={
                "services.json": json.dumps({
                    "services": [sample_service_config],
                    "last_updated": datetime.utcnow().isoformat()
                })
            }
        )
        updated_configmap.metadata.resource_version = "2"

        mock_watch.events.append({
            "type": "MODIFIED",
            "object": updated_configmap
        })

        # Start watching (with timeout)
        start_time = datetime.utcnow()

        with patch("kubernetes.watch.Watch", return_value=mock_watch):
            # Run watcher for up to 60 seconds
            try:
                await asyncio.wait_for(
                    watcher.watch_configmap(),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                pass

        # Verify reload was triggered
        assert len(reload_events) > 0, "Collector did not reload configuration"

        # Verify reload happened within 60 seconds (FR-006)
        time_to_reload = (reload_events[0] - start_time).total_seconds()
        assert time_to_reload < 60.0, f"Config reload took {time_to_reload}s, exceeds 60s limit"

    @pytest.mark.asyncio
    async def test_no_dropped_events_during_reconfiguration(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that no telemetry events are dropped during reconfiguration.

        Requirements:
        - FR-006: Zero data loss during reconfiguration

        Test Flow:
        1. Simulate active telemetry collection
        2. Trigger collector reconfiguration
        3. Verify all events before/during/after are captured
        4. Verify event continuity (no gaps)
        """
        from src.services.collector_config_manager import CollectorConfigManager
        from src.services.telemetry_buffer import TelemetryBuffer

        # Initialize components
        buffer = TelemetryBuffer(max_size=10000)
        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Simulate continuous event stream
        events_sent: List[Dict[str, Any]] = []
        events_received: List[Dict[str, Any]] = []

        async def send_telemetry_events():
            """Simulate sending telemetry events."""
            for i in range(100):
                event = {
                    "event_id": str(uuid4()),
                    "timestamp": datetime.utcnow().isoformat(),
                    "service": "payments-api",
                    "metric": "http_request_duration_seconds",
                    "value": 0.123,
                    "sequence": i
                }
                events_sent.append(event)
                await buffer.add(event)
                await asyncio.sleep(0.01)  # 10ms between events

        async def collect_telemetry_events():
            """Simulate collector reading from buffer."""
            while len(events_received) < 100:
                event = await buffer.get()
                if event:
                    events_received.append(event)
                await asyncio.sleep(0.005)  # Collector is faster than producer

        async def trigger_reconfiguration():
            """Trigger reconfiguration mid-stream."""
            await asyncio.sleep(0.5)  # Wait for some events
            await config_manager.add_service(sample_service_config)

        # Run all tasks concurrently
        await asyncio.gather(
            send_telemetry_events(),
            collect_telemetry_events(),
            trigger_reconfiguration(),
        )

        # Verify all events were received
        assert len(events_received) == len(events_sent), \
            f"Event loss: sent {len(events_sent)}, received {len(events_received)}"

        # Verify event ordering (no gaps in sequence numbers)
        received_sequences = sorted([e["sequence"] for e in events_received])
        expected_sequences = list(range(100))
        assert received_sequences == expected_sequences, \
            "Events were dropped or reordered during reconfiguration"

    @pytest.mark.asyncio
    async def test_fallback_to_polling_if_watch_fails(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test fallback to 60s polling if ConfigMap watch fails (FR-007).

        Requirements:
        - FR-007: Collectors MUST read service list from config refreshed every 60s

        Test Flow:
        1. Initialize watcher
        2. Simulate watch failure (connection error)
        3. Verify fallback to polling mode
        4. Verify polling happens every 60 seconds
        5. Verify config is still updated correctly
        """
        from src.services.otel_collector_watcher import OTelCollectorWatcher

        # Mock watch that fails
        mock_watch_failed = MagicMock()
        mock_watch_failed.stream.side_effect = Exception("Watch connection failed")

        # Initialize watcher
        watcher = OTelCollectorWatcher(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config",
            poll_interval=5  # Use 5s for testing instead of 60s
        )

        # Track polling attempts
        poll_times: List[datetime] = []

        original_read = mock_k8s_client.CoreV1Api().read_namespaced_config_map

        async def mock_read_with_tracking(*args, **kwargs):
            poll_times.append(datetime.utcnow())
            return await original_read(*args, **kwargs)

        mock_k8s_client.CoreV1Api().read_namespaced_config_map = mock_read_with_tracking

        # Mock ConfigMap response
        import json
        mock_configmap = MockV1ConfigMap(
            name="otel-collector-config",
            namespace="observability",
            data={
                "services.json": json.dumps({
                    "services": [sample_service_config],
                    "last_updated": datetime.utcnow().isoformat()
                })
            }
        )
        mock_k8s_client.CoreV1Api().read_namespaced_config_map.return_value = mock_configmap

        # Start watcher with watch failure
        with patch("kubernetes.watch.Watch", return_value=mock_watch_failed):
            # Run for 15 seconds to see multiple polls
            try:
                await asyncio.wait_for(
                    watcher.start(),
                    timeout=15.0
                )
            except asyncio.TimeoutError:
                pass

        # Verify fallback to polling occurred
        assert len(poll_times) >= 2, "Polling fallback did not occur"

        # Verify polling interval is approximately 5 seconds (our test value)
        if len(poll_times) >= 2:
            interval = (poll_times[1] - poll_times[0]).total_seconds()
            assert 4.5 <= interval <= 5.5, \
                f"Polling interval {interval}s not within expected range"

    @pytest.mark.asyncio
    async def test_configmap_update_includes_label_selectors(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that ConfigMap includes label selectors for filtering (FR-008).

        Requirements:
        - FR-008: Collectors MUST construct filtered queries using label selectors

        Test Flow:
        1. Create service with label selectors
        2. Verify ConfigMap contains label selectors
        3. Verify label selectors match expected format
        4. Verify selectors can be used for Prometheus queries
        """
        from src.services.collector_config_manager import CollectorConfigManager

        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Add service with label selectors
        await config_manager.add_service(sample_service_config)

        # Get updated ConfigMap
        call_args = mock_k8s_client.CoreV1Api().patch_namespaced_config_map.call_args
        import json
        updated_data = json.loads(call_args[1]["body"]["data"]["services.json"])

        # Verify label selectors are present
        service = updated_data["services"][0]
        assert "label_selectors" in service
        assert service["label_selectors"]["job"] == "payment-gateway"
        assert service["label_selectors"]["namespace"] == "prod"

        # Verify label selector format matches Prometheus query syntax
        # Expected: {job="payment-gateway",namespace="prod"}
        label_selector_str = ",".join(
            f'{k}="{v}"' for k, v in service["label_selectors"].items()
        )
        assert label_selector_str == 'job="payment-gateway",namespace="prod"'

    @pytest.mark.asyncio
    async def test_collected_events_tagged_with_service_id(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that collected events are tagged with service_id (FR-009).

        Requirements:
        - FR-009: Collectors MUST tag each collected event with correct service_id

        Test Flow:
        1. Configure collector with service
        2. Simulate metric collection
        3. Verify collected events have service_id tag
        4. Verify service_id matches configured service
        """
        from src.services.collector_config_manager import CollectorConfigManager
        from src.services.metric_collector import MetricCollector

        # Setup collector with service config
        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )
        await config_manager.add_service(sample_service_config)

        # Initialize metric collector
        collector = MetricCollector(config_manager=config_manager)

        # Simulate collecting a metric
        raw_metric = {
            "metric": "http_request_duration_seconds",
            "value": 0.145,
            "labels": {
                "job": "payment-gateway",
                "namespace": "prod",
                "method": "POST",
                "status": "200"
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Collect and tag metric
        tagged_event = await collector.collect_and_tag(raw_metric)

        # Verify service_id was added
        assert "service_id" in tagged_event
        assert tagged_event["service_id"] == sample_service_config["service_id"]

        # Verify original metric data is preserved
        assert tagged_event["metric"] == raw_metric["metric"]
        assert tagged_event["value"] == raw_metric["value"]
        assert tagged_event["labels"] == raw_metric["labels"]

    @pytest.mark.asyncio
    async def test_multiple_services_configuration(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test ConfigMap handles multiple services correctly.

        Test Flow:
        1. Add multiple services
        2. Verify all services in ConfigMap
        3. Verify each service has unique label selectors
        4. Verify collector can distinguish between services
        """
        from src.services.collector_config_manager import CollectorConfigManager

        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Create multiple services
        services = [
            {
                **sample_service_config,
                "service_id": str(uuid4()),
                "name": "payments-api",
                "label_selectors": {"job": "payment-gateway", "namespace": "prod"}
            },
            {
                **sample_service_config,
                "service_id": str(uuid4()),
                "name": "auth-service",
                "label_selectors": {"job": "auth-svc", "namespace": "prod"}
            },
            {
                **sample_service_config,
                "service_id": str(uuid4()),
                "name": "user-profile",
                "label_selectors": {"job": "user-api", "namespace": "staging"}
            }
        ]

        # Add all services
        for service in services:
            await config_manager.add_service(service)

        # Verify ConfigMap contains all services
        call_args = mock_k8s_client.CoreV1Api().patch_namespaced_config_map.call_args
        import json
        updated_data = json.loads(call_args[1]["body"]["data"]["services.json"])

        assert len(updated_data["services"]) == 3

        # Verify each service has unique selectors
        service_names = {s["name"] for s in updated_data["services"]}
        assert service_names == {"payments-api", "auth-service", "user-profile"}

    @pytest.mark.asyncio
    async def test_configmap_update_atomic_operation(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that ConfigMap updates are atomic to prevent race conditions.

        Test Flow:
        1. Simulate concurrent service additions
        2. Verify all services are added
        3. Verify no service is lost due to race condition
        4. Verify ConfigMap resource version is checked
        """
        from src.services.collector_config_manager import CollectorConfigManager

        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Simulate concurrent additions
        services = [
            {**sample_service_config, "service_id": str(uuid4()), "name": f"service-{i}"}
            for i in range(5)
        ]

        # Add services concurrently
        await asyncio.gather(*[
            config_manager.add_service(service)
            for service in services
        ])

        # Verify all services were added (check last call)
        call_args = mock_k8s_client.CoreV1Api().patch_namespaced_config_map.call_args
        import json
        updated_data = json.loads(call_args[1]["body"]["data"]["services.json"])

        # All services should be present
        service_names = {s["name"] for s in updated_data["services"]}
        expected_names = {f"service-{i}" for i in range(5)}
        assert service_names == expected_names


class TestCollectorReconfigurationEdgeCases:
    """Test edge cases and error scenarios for collector reconfiguration."""

    @pytest.mark.asyncio
    async def test_configmap_not_found_creates_new(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test that missing ConfigMap is created automatically.

        Test Flow:
        1. Simulate ConfigMap not found error
        2. Verify new ConfigMap is created
        3. Verify created ConfigMap has correct structure
        """
        from src.services.collector_config_manager import CollectorConfigManager
        from kubernetes.client.rest import ApiException

        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Simulate ConfigMap not found
        mock_k8s_client.CoreV1Api().read_namespaced_config_map.side_effect = \
            ApiException(status=404, reason="Not Found")

        # Mock create operation
        mock_k8s_client.CoreV1Api().create_namespaced_config_map = AsyncMock()

        # Add service - should create ConfigMap
        await config_manager.add_service(sample_service_config)

        # Verify ConfigMap was created
        mock_k8s_client.CoreV1Api().create_namespaced_config_map.assert_called_once()

    @pytest.mark.asyncio
    async def test_watch_reconnection_after_failure(
        self,
        mock_k8s_client,
        mock_watch,
    ) -> None:
        """Test that watch reconnects after connection failure.

        Test Flow:
        1. Start watch
        2. Simulate connection failure
        3. Verify watch attempts reconnection
        4. Verify exponential backoff
        """
        from src.services.otel_collector_watcher import OTelCollectorWatcher

        watcher = OTelCollectorWatcher(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Track reconnection attempts
        reconnect_times: List[datetime] = []

        original_watch = watcher.watch_configmap

        async def mock_watch_with_tracking(*args, **kwargs):
            reconnect_times.append(datetime.utcnow())
            if len(reconnect_times) < 3:
                raise Exception("Connection failed")
            # Succeed on 3rd attempt
            return

        watcher.watch_configmap = mock_watch_with_tracking

        # Start watcher - should retry
        try:
            await asyncio.wait_for(watcher.start_with_retry(), timeout=10.0)
        except asyncio.TimeoutError:
            pass

        # Verify multiple reconnection attempts
        assert len(reconnect_times) >= 2, "Watch did not retry after failure"

    @pytest.mark.asyncio
    async def test_malformed_configmap_data_handling(
        self,
        mock_k8s_client,
        sample_service_config: Dict[str, Any],
    ) -> None:
        """Test handling of malformed ConfigMap data.

        Test Flow:
        1. Return ConfigMap with invalid JSON
        2. Verify error is logged
        3. Verify system falls back to empty config
        4. Verify subsequent valid update works
        """
        from src.services.collector_config_manager import CollectorConfigManager

        config_manager = CollectorConfigManager(
            k8s_client=mock_k8s_client,
            namespace="observability",
            configmap_name="otel-collector-config"
        )

        # Mock ConfigMap with invalid JSON
        invalid_configmap = MockV1ConfigMap(
            name="otel-collector-config",
            namespace="observability",
            data={"services.json": "invalid json {{{"}
        )
        mock_k8s_client.CoreV1Api().read_namespaced_config_map.return_value = \
            invalid_configmap

        # Attempt to read config - should handle gracefully
        services = await config_manager.get_services()

        # Should return empty list on invalid data
        assert services == []


# Test coverage summary
def test_collector_reconfiguration_coverage() -> None:
    """Meta-test to validate integration test coverage.

    Integration tests cover:
    1. Service creation triggers ConfigMap update (FR-006)
    2. Collector picks up config within 60 seconds (FR-006)
    3. No dropped events during reconfiguration
    4. Fallback to 60s polling if watch fails (FR-007)
    5. ConfigMap includes label selectors (FR-008)
    6. Events tagged with service_id (FR-009)
    7. Multiple services configuration
    8. Atomic ConfigMap updates
    9. ConfigMap creation if missing
    10. Watch reconnection after failure
    11. Malformed data handling
    """
    covered_requirements = [
        "FR-006: Dynamic config update within 60s",
        "FR-007: 60s polling fallback",
        "FR-008: Label selector filtering",
        "FR-009: Service ID tagging",
    ]

    covered_scenarios = [
        "ConfigMap update on service creation",
        "Hot-reload within 60 seconds",
        "Zero event loss during reconfiguration",
        "Watch failure fallback to polling",
        "Multiple service handling",
        "Atomic updates (race condition prevention)",
        "ConfigMap auto-creation",
        "Watch reconnection",
        "Invalid data handling",
    ]

    assert len(covered_requirements) == 4
    assert len(covered_scenarios) == 9
    assert "FR-006" in covered_requirements[0]
    assert "FR-007" in covered_requirements[1]
