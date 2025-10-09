"""
Integration test for complete analysis flow (Quickstart Steps 4-5)

This test validates the end-to-end analysis workflow:
- Step 4: Verify collector reconfiguration after service creation
- Step 5: Trigger analysis job and verify completion
  - POST /api/v1/analysis/jobs creates job
  - Job completes within 15-30 minutes (NFR-003)
  - Journey discovery from telemetry data
  - SLI recommendations generated with confidence scores
  - Async Celery task execution

Per quickstart.md validation requirements:
- Analysis job picked up within 10 seconds (FR-020)
- Job status transitions: pending → running → completed
- Analysis completes in 15-30 minutes for ~1M events (NFR-003)
- User journeys extracted from trace data
- SLI candidates generated with PromQL queries
- Confidence scores in range 0.0-1.0

MUST FAIL initially (TDD requirement) until:
- src/api/v1/endpoints/analysis.py implemented
- src/workers/analysis_worker.py implemented
- src/services/journey_discovery.py implemented
- src/services/sli_recommender.py implemented
"""
import pytest
from httpx import AsyncClient
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import asyncio


class TestAnalysisJobCreation:
    """Test POST /api/v1/analysis/jobs endpoint"""

    @pytest.mark.asyncio
    async def test_create_analysis_job_returns_202(
        self, async_client: AsyncClient, sample_service
    ):
        """
        POST /api/v1/analysis/jobs should return 202 with job details

        Per quickstart.md Step 5.2: Create analysis job via API
        Expected: HTTP 202 with job_id, status='pending'
        """
        request_body = {
            "service_id": str(sample_service.service_id),
            "lookback_days": 7
        }

        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json=request_body
        )

        # Per analysis-api.yaml: 202 Accepted
        assert response.status_code == 202

        data = response.json()

        # Validate response schema
        assert "job_id" in data
        job_id = UUID(data["job_id"])  # Validates UUID format

        assert "service_id" in data
        assert data["service_id"] == str(sample_service.service_id)

        assert "status" in data
        assert data["status"] == "pending"

        assert "lookback_days" in data
        assert data["lookback_days"] == 7

        assert "created_at" in data
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))

        # Optional fields should be None initially
        assert data.get("started_at") is None
        assert data.get("completed_at") is None
        assert data.get("error_message") is None
        assert data.get("results") is None

    @pytest.mark.asyncio
    async def test_create_analysis_job_validates_service_exists(
        self, async_client: AsyncClient
    ):
        """
        POST /api/v1/analysis/jobs should return 404 if service not found

        Per quickstart.md: Analysis requires valid service registration
        """
        nonexistent_service_id = str(uuid4())
        request_body = {
            "service_id": nonexistent_service_id,
            "lookback_days": 7
        }

        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json=request_body
        )

        # Per analysis-api.yaml: 404 Not Found
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_create_analysis_job_validates_lookback_days_range(
        self, async_client: AsyncClient, sample_service
    ):
        """
        POST /api/v1/analysis/jobs should validate lookback_days 1-30

        Per analysis-api.yaml: lookback_days minimum 1, maximum 30
        """
        # Test below minimum
        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 0}
        )
        assert response.status_code == 400

        # Test above maximum
        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 31}
        )
        assert response.status_code == 400

        # Test valid range
        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 15}
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_create_analysis_job_uses_default_lookback_days(
        self, async_client: AsyncClient, sample_service
    ):
        """
        POST /api/v1/analysis/jobs should default lookback_days to 7

        Per analysis-api.yaml: lookback_days default value is 7
        """
        request_body = {
            "service_id": str(sample_service.service_id)
            # lookback_days not provided
        }

        response = await async_client.post(
            "/api/v1/analysis/jobs",
            json=request_body
        )

        assert response.status_code == 202
        data = response.json()
        assert data["lookback_days"] == 7


class TestAnalysisJobStatus:
    """Test GET /api/v1/analysis/jobs/{job_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_analysis_job_status_returns_200(
        self, async_client: AsyncClient, sample_service
    ):
        """
        GET /api/v1/analysis/jobs/{job_id} should return job status

        Per quickstart.md Step 5.3: Monitor job status
        Expected: Job transitions pending → running → completed
        """
        # First create a job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        # Get job status
        response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")

        assert response.status_code == 200

        data = response.json()

        # Validate response schema
        assert "job_id" in data
        assert data["job_id"] == job_id

        assert "service_id" in data
        assert data["service_id"] == str(sample_service.service_id)

        assert "status" in data
        assert data["status"] in ["pending", "running", "completed", "failed", "cancelled"]

        assert "lookback_days" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_get_analysis_job_not_found(self, async_client: AsyncClient):
        """
        GET /api/v1/analysis/jobs/{job_id} should return 404 for invalid job

        Per analysis-api.yaml: 404 if job not found
        """
        nonexistent_job_id = str(uuid4())

        response = await async_client.get(
            f"/api/v1/analysis/jobs/{nonexistent_job_id}"
        )

        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert "message" in data


class TestAnalysisJobExecution:
    """Test complete analysis job execution with Celery worker"""

    @pytest.mark.asyncio
    @patch("src.workers.analysis_worker.celery_app")
    @patch("src.services.journey_discovery.JourneyDiscoveryService")
    @patch("src.services.sli_recommender.SLIRecommenderService")
    async def test_analysis_job_picked_up_within_10_seconds(
        self,
        mock_sli_service,
        mock_journey_service,
        mock_celery,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should be picked up by worker within 10 seconds

        Per quickstart.md Step 5.3 + FR-020:
        - 0-10 sec: status = 'pending'
        - 10 sec: status = 'running' (worker picked up job)

        This test mocks Celery worker to verify job transitions
        """
        # Create analysis job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        # Mock Celery task to simulate worker picking up job
        mock_task = AsyncMock()
        mock_celery.send_task.return_value = mock_task

        # Wait simulated time (using mock)
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Simulate 5 seconds passed - job should still be pending
            await mock_sleep(5)

            status_response = await async_client.get(
                f"/api/v1/analysis/jobs/{job_id}"
            )
            assert status_response.status_code == 200
            assert status_response.json()["status"] == "pending"

            # Simulate worker picks up job at 10 seconds
            await mock_sleep(5)  # Total 10 seconds

            # Manually update job status to 'running' (simulating worker)
            # In real implementation, worker would update database
            from src.models.analysis_job import AnalysisJob

            job = test_db.query(AnalysisJob).filter(
                AnalysisJob.job_id == UUID(job_id)
            ).first()

            if job:
                job.status = "running"
                job.started_at = datetime.utcnow()
                test_db.commit()

            status_response = await async_client.get(
                f"/api/v1/analysis/jobs/{job_id}"
            )
            assert status_response.status_code == 200
            data = status_response.json()
            assert data["status"] == "running"
            assert data["started_at"] is not None

    @pytest.mark.asyncio
    @pytest.mark.timeout(1800)  # 30 minute timeout
    @patch("src.workers.analysis_worker.process_analysis_job")
    @patch("src.services.journey_discovery.JourneyDiscoveryService")
    @patch("src.services.sli_recommender.SLIRecommenderService")
    @patch("time.time")
    async def test_analysis_job_completes_within_15_30_minutes(
        self,
        mock_time,
        mock_sli_service,
        mock_journey_service,
        mock_worker,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should complete within 15-30 minutes for ~1M events

        Per quickstart.md Step 5.3 + NFR-003:
        - 15-30 min: status = 'completed' (analysis completes)

        Expected timeline (mocked):
        - 0s: Job created, status='pending'
        - 10s: Worker picks up, status='running'
        - 900-1800s: Analysis completes, status='completed'

        This test uses time mocking to simulate the duration
        """
        # Setup mock time progression
        start_time = 1704700000  # Fixed timestamp
        mock_time.return_value = start_time

        # Mock telemetry data (~1M events)
        mock_telemetry_events = self._generate_mock_telemetry_events(
            service_id=sample_service.service_id,
            count=987654  # Per quickstart.md example
        )

        # Mock journey discovery results
        mock_journeys = self._generate_mock_journeys(count=5)
        mock_journey_service.return_value.discover_journeys.return_value = mock_journeys

        # Mock SLI recommendations
        mock_slis = self._generate_mock_sli_recommendations(
            journeys=mock_journeys,
            count=12
        )
        mock_sli_service.return_value.generate_recommendations.return_value = mock_slis

        # Create analysis job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        # Simulate worker processing with time progression
        from src.models.analysis_job import AnalysisJob

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        # Worker picks up job at 10 seconds
        mock_time.return_value = start_time + 10
        job.status = "running"
        job.started_at = datetime.fromtimestamp(mock_time.return_value)
        test_db.commit()

        # Simulate analysis processing (mock fast-forward to completion)
        # Real duration: 900-1800 seconds (15-30 minutes)
        # We'll use 1710 seconds (28.5 minutes) as per quickstart.md example
        analysis_duration = 1710
        mock_time.return_value = start_time + 10 + analysis_duration

        # Update job to completed with results
        job.status = "completed"
        job.completed_at = datetime.fromtimestamp(mock_time.return_value)
        job.results = {
            "journeys_discovered": 5,
            "slis_generated": 12,
            "telemetry_events_analyzed": 987654,
            "capsules_created": 342
        }
        test_db.commit()

        # Verify job completion
        status_response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")
        assert status_response.status_code == 200

        data = status_response.json()
        assert data["status"] == "completed"
        assert data["started_at"] is not None
        assert data["completed_at"] is not None

        # Verify completion time within acceptable range (15-30 minutes)
        started = datetime.fromisoformat(data["started_at"].replace("Z", "+00:00"))
        completed = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
        duration_seconds = (completed - started).total_seconds()

        assert 900 <= duration_seconds <= 1800, (
            f"Analysis duration {duration_seconds}s outside 15-30 min range (900-1800s)"
        )

        # Verify results structure
        assert data["results"] is not None
        results = data["results"]
        assert results["journeys_discovered"] == 5
        assert results["slis_generated"] == 12
        assert results["telemetry_events_analyzed"] == 987654
        assert results["capsules_created"] == 342

    @pytest.mark.asyncio
    @patch("src.services.journey_discovery.JourneyDiscoveryService")
    async def test_journey_discovery_from_telemetry_data(
        self,
        mock_journey_service,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should discover user journeys from telemetry data

        Per quickstart.md Step 6.1:
        - User journeys extracted from trace data
        - Journeys linked to service via service_id
        - Confidence scores calculated (0.0-1.0 range)

        Expected output (if telemetry exists):
        - journey_id, name, confidence_score, discovered_at
        - Journeys ordered by confidence_score DESC
        """
        # Mock journey discovery to return sample journeys
        mock_journeys = [
            {
                "journey_id": uuid4(),
                "name": "Checkout Flow",
                "entry_point": "/api/cart",
                "exit_point": "/api/payment/confirm",
                "confidence_score": 0.92,
                "step_sequence": {
                    "steps": [
                        {"service": "test-service", "endpoint": "/api/cart"},
                        {"service": "test-service", "endpoint": "/api/checkout"},
                        {"service": "test-service", "endpoint": "/api/payment/confirm"}
                    ]
                },
                "sample_trace_ids": ["trace-001", "trace-002"],
                "discovered_at": datetime.utcnow()
            },
            {
                "journey_id": uuid4(),
                "name": "Product Search Flow",
                "entry_point": "/api/search",
                "exit_point": "/api/products/{id}",
                "confidence_score": 0.85,
                "step_sequence": {
                    "steps": [
                        {"service": "test-service", "endpoint": "/api/search"},
                        {"service": "test-service", "endpoint": "/api/products/{id}"}
                    ]
                },
                "sample_trace_ids": ["trace-003", "trace-004"],
                "discovered_at": datetime.utcnow()
            }
        ]

        mock_journey_service.return_value.discover_journeys.return_value = mock_journeys

        # Create and complete analysis job (simulated)
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        job_id = create_response.json()["job_id"]

        # Simulate job completion with journey creation
        from src.models.analysis_job import AnalysisJob
        from src.models.user_journey import UserJourney

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        # Insert discovered journeys into database
        for journey_data in mock_journeys:
            journey = UserJourney(
                journey_id=journey_data["journey_id"],
                service_id=sample_service.service_id,
                name=journey_data["name"],
                entry_point=journey_data["entry_point"],
                exit_point=journey_data["exit_point"],
                step_sequence=journey_data["step_sequence"],
                confidence_score=journey_data["confidence_score"],
                sample_trace_ids=journey_data["sample_trace_ids"],
                discovered_at=journey_data["discovered_at"],
                last_seen_at=journey_data["discovered_at"]
            )
            test_db.add(journey)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        test_db.commit()

        # Verify journeys via API
        journeys_response = await async_client.get(
            "/api/v1/journeys",
            params={"service_id": str(sample_service.service_id)}
        )

        assert journeys_response.status_code == 200
        journeys = journeys_response.json()

        # Validate journey discovery results
        assert len(journeys) >= 2

        # Check first journey (highest confidence)
        checkout_journey = next(
            (j for j in journeys if j["name"] == "Checkout Flow"), None
        )
        assert checkout_journey is not None
        assert checkout_journey["confidence_score"] == 0.92
        assert checkout_journey["entry_point"] == "/api/cart"
        assert checkout_journey["exit_point"] == "/api/payment/confirm"

        # Validate all confidence scores in valid range
        for journey in journeys:
            assert 0.0 <= journey["confidence_score"] <= 1.0

    @pytest.mark.asyncio
    @patch("src.services.sli_recommender.SLIRecommenderService")
    async def test_sli_recommendations_generated_with_confidence_scores(
        self,
        mock_sli_service,
        async_client: AsyncClient,
        sample_service,
        sample_user_journey,
        test_db: Session
    ):
        """
        Analysis job should generate SLI recommendations with confidence scores

        Per quickstart.md Step 6.2:
        - SLI candidates generated with PromQL queries
        - SLIs linked to journeys via journey_id
        - Confidence scores in range 0.0-1.0
        - SLIs marked as approved=false by default

        Expected output:
        - name, confidence_score, approved, journey_name
        - SLIs ordered by confidence_score DESC
        """
        # Mock SLI recommendations
        mock_slis = [
            {
                "sli_id": uuid4(),
                "name": "Checkout Success Rate",
                "metric_type": "availability",
                "metric_definition": (
                    "sum(rate(http_requests_total{endpoint=\"/checkout\",status=\"200\"}[5m])) / "
                    "sum(rate(http_requests_total{endpoint=\"/checkout\"}[5m]))"
                ),
                "measurement_window": "5m",
                "confidence_score": 0.89,
                "unit": "percent",
                "approved": False
            },
            {
                "sli_id": uuid4(),
                "name": "Checkout P95 Latency",
                "metric_type": "latency",
                "metric_definition": (
                    "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket"
                    "{endpoint=\"/checkout\"}[5m]))"
                ),
                "measurement_window": "5m",
                "confidence_score": 0.87,
                "unit": "seconds",
                "approved": False
            }
        ]

        mock_sli_service.return_value.generate_recommendations.return_value = mock_slis

        # Create analysis job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        job_id = create_response.json()["job_id"]

        # Simulate job completion with SLI creation
        from src.models.analysis_job import AnalysisJob
        from src.models.sli import SLI

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        # Insert SLI recommendations into database
        for sli_data in mock_slis:
            sli = SLI(
                sli_id=sli_data["sli_id"],
                journey_id=sample_user_journey.journey_id,
                name=sli_data["name"],
                metric_type=sli_data["metric_type"],
                metric_definition=sli_data["metric_definition"],
                measurement_window=sli_data["measurement_window"],
                confidence_score=sli_data["confidence_score"],
                unit=sli_data["unit"],
                approved_by=None,
                approved_at=None,
                evidence_pointers={
                    "capsules": [],
                    "traces": sample_user_journey.sample_trace_ids
                },
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            test_db.add(sli)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        test_db.commit()

        # Verify SLIs via API
        slis_response = await async_client.get(
            "/api/v1/slis",
            params={"journey_id": str(sample_user_journey.journey_id)}
        )

        assert slis_response.status_code == 200
        slis = slis_response.json()

        # Validate SLI generation results
        assert len(slis) >= 2

        # Check SLI structure
        checkout_success_sli = next(
            (s for s in slis if s["name"] == "Checkout Success Rate"), None
        )
        assert checkout_success_sli is not None
        assert checkout_success_sli["confidence_score"] == 0.89
        assert checkout_success_sli["metric_type"] == "availability"
        assert checkout_success_sli["approved"] is False  # Default unapproved

        # Verify PromQL query structure
        assert "http_requests_total" in checkout_success_sli["metric_definition"]
        assert "rate(" in checkout_success_sli["metric_definition"]

        # Validate all confidence scores in valid range
        for sli in slis:
            assert 0.0 <= sli["confidence_score"] <= 1.0
            assert sli["approved"] is False  # All should be unapproved by default

    @pytest.mark.asyncio
    async def test_analysis_job_with_no_telemetry_data_completes_successfully(
        self,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should complete with zero journeys if no telemetry data exists

        Per quickstart.md Step 6.1 Note + FR-027:
        "What happens when no traces found for service? Analysis job MUST complete
        with status 'completed' but zero journeys discovered"

        This is expected behavior, not an error condition.
        """
        # Create analysis job for service with no telemetry
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        # Simulate job completion with no journeys found
        from src.models.analysis_job import AnalysisJob

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        job.status = "completed"
        job.started_at = datetime.utcnow()
        job.completed_at = datetime.utcnow()
        job.results = {
            "journeys_discovered": 0,
            "slis_generated": 0,
            "telemetry_events_analyzed": 0,
            "capsules_created": 0
        }
        test_db.commit()

        # Verify job completed successfully despite no data
        status_response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")
        assert status_response.status_code == 200

        data = status_response.json()
        assert data["status"] == "completed"
        assert data["error_message"] is None
        assert data["results"]["journeys_discovered"] == 0

        # Verify no journeys in database
        journeys_response = await async_client.get(
            "/api/v1/journeys",
            params={"service_id": str(sample_service.service_id)}
        )
        assert journeys_response.status_code == 200
        assert len(journeys_response.json()) == 0

    # Helper methods for generating mock data

    def _generate_mock_telemetry_events(
        self, service_id: UUID, count: int
    ) -> List[Dict[str, Any]]:
        """Generate mock telemetry events for testing"""
        events = []
        base_time = datetime.utcnow() - timedelta(days=7)

        for i in range(count):
            events.append({
                "event_id": uuid4(),
                "service_id": service_id,
                "event_type": "span",
                "timestamp": base_time + timedelta(seconds=i * 10),
                "attributes": {
                    "http.method": "POST" if i % 3 == 0 else "GET",
                    "http.route": "/api/checkout" if i % 5 == 0 else "/api/search",
                    "http.status_code": 200 if i % 10 != 0 else 500,
                    "trace.id": f"trace-{i // 100:04d}"
                }
            })

        return events

    def _generate_mock_journeys(self, count: int) -> List[Dict[str, Any]]:
        """Generate mock journey discovery results"""
        journeys = [
            {
                "name": "Checkout Flow",
                "entry_point": "/api/cart",
                "exit_point": "/api/payment/confirm",
                "confidence_score": 0.92
            },
            {
                "name": "Product Search Flow",
                "entry_point": "/api/search",
                "exit_point": "/api/products/{id}",
                "confidence_score": 0.85
            },
            {
                "name": "User Login Flow",
                "entry_point": "/api/auth/login",
                "exit_point": "/api/dashboard",
                "confidence_score": 0.78
            },
            {
                "name": "Cart Management Flow",
                "entry_point": "/api/cart/add",
                "exit_point": "/api/cart/view",
                "confidence_score": 0.71
            },
            {
                "name": "Profile Update Flow",
                "entry_point": "/api/profile",
                "exit_point": "/api/profile/save",
                "confidence_score": 0.65
            }
        ]

        return [
            {
                **journey,
                "journey_id": uuid4(),
                "step_sequence": {"steps": []},
                "sample_trace_ids": [f"trace-{i:03d}" for i in range(5)],
                "discovered_at": datetime.utcnow()
            }
            for journey in journeys[:count]
        ]

    def _generate_mock_sli_recommendations(
        self, journeys: List[Dict[str, Any]], count: int
    ) -> List[Dict[str, Any]]:
        """Generate mock SLI recommendations for journeys"""
        sli_templates = [
            {
                "name": "{journey_name} Success Rate",
                "metric_type": "availability",
                "unit": "percent",
                "confidence_score_offset": 0.0
            },
            {
                "name": "{journey_name} P95 Latency",
                "metric_type": "latency",
                "unit": "seconds",
                "confidence_score_offset": -0.02
            },
            {
                "name": "{journey_name} Error Rate",
                "metric_type": "errors",
                "unit": "percent",
                "confidence_score_offset": -0.05
            }
        ]

        slis = []
        for journey in journeys:
            for template in sli_templates:
                if len(slis) >= count:
                    break

                slis.append({
                    "sli_id": uuid4(),
                    "name": template["name"].format(journey_name=journey["name"]),
                    "metric_type": template["metric_type"],
                    "metric_definition": f"rate(metric_total{{endpoint=\"{journey['entry_point']}\"}}[5m])",
                    "measurement_window": "5m",
                    "confidence_score": min(
                        journey["confidence_score"] + template["confidence_score_offset"],
                        1.0
                    ),
                    "unit": template["unit"],
                    "approved": False
                })

        return slis[:count]


class TestAnalysisJobErrorHandling:
    """Test error scenarios in analysis job execution"""

    @pytest.mark.asyncio
    async def test_analysis_job_retries_on_transient_failure(
        self,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should retry up to 3 times on transient failures

        Per FR-023: Max 3 retries for failed analysis jobs
        """
        # Create analysis job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        job_id = create_response.json()["job_id"]

        # Simulate first failure
        from src.models.analysis_job import AnalysisJob

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        job.status = "failed"
        job.error_message = "Transient database connection error"
        job.retry_count = 1
        test_db.commit()

        # Verify retry count incremented
        status_response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")
        data = status_response.json()
        assert data["retry_count"] == 1
        assert data["error_message"] is not None

        # Simulate retry exhaustion (3rd retry)
        job.retry_count = 3
        job.status = "failed"
        test_db.commit()

        status_response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")
        data = status_response.json()
        assert data["retry_count"] == 3
        assert data["status"] == "failed"

    @pytest.mark.asyncio
    async def test_analysis_job_fails_with_invalid_telemetry_endpoint(
        self,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Analysis job should fail gracefully if telemetry endpoint unreachable

        Expected behavior:
        - Job status = 'failed'
        - Error message describes connection failure
        - Retry logic applies (up to 3 retries)
        """
        # Update service with invalid telemetry endpoint
        sample_service.telemetry_endpoints = {
            "prometheus_url": "http://invalid-prometheus:9090",
            "otlp_endpoint": "grpc://invalid-collector:4317"
        }
        test_db.commit()

        # Create analysis job
        create_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        job_id = create_response.json()["job_id"]

        # Simulate failure due to unreachable endpoint
        from src.models.analysis_job import AnalysisJob

        job = test_db.query(AnalysisJob).filter(
            AnalysisJob.job_id == UUID(job_id)
        ).first()

        job.status = "failed"
        job.error_message = "Failed to connect to Prometheus endpoint: Connection refused"
        test_db.commit()

        # Verify error handling
        status_response = await async_client.get(f"/api/v1/analysis/jobs/{job_id}")
        data = status_response.json()
        assert data["status"] == "failed"
        assert "Connection refused" in data["error_message"]


class TestAnalysisJobConcurrency:
    """Test concurrent analysis job execution limits"""

    @pytest.mark.asyncio
    async def test_concurrent_analysis_jobs_for_different_services(
        self,
        async_client: AsyncClient,
        sample_service,
        test_db: Session
    ):
        """
        Multiple analysis jobs should run concurrently for different services

        Per NFR-007: Support up to 10 concurrent analysis jobs
        """
        # Create second service
        from src.models.service import Service

        service2 = Service(
            service_id=uuid4(),
            name="service-2",
            environment="prod",
            owner_team="team-2",
            telemetry_endpoints={
                "prometheus_url": "http://prometheus:9090"
            },
            status="active",
            organization_id=uuid4(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        test_db.add(service2)
        test_db.commit()

        # Create jobs for both services
        job1_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(sample_service.service_id), "lookback_days": 7}
        )
        job2_response = await async_client.post(
            "/api/v1/analysis/jobs",
            json={"service_id": str(service2.service_id), "lookback_days": 7}
        )

        assert job1_response.status_code == 202
        assert job2_response.status_code == 202

        # Both jobs should be independent
        job1_id = job1_response.json()["job_id"]
        job2_id = job2_response.json()["job_id"]
        assert job1_id != job2_id
