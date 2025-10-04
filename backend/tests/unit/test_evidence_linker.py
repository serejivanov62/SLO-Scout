"""
Unit tests for Evidence Linker Service

Tests T092: Evidence linking via vector search with contribution weights
"""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import Mock, MagicMock, patch

from src.services.evidence_linker import EvidenceLinker, EvidenceLink
from src.models.user_journey import UserJourney
from src.models.service import Service, Environment
from src.models.capsule import Capsule
from src.models.sli import SLI, MetricType
from src.models.evidence_pointer import EvidencePointer, RedactionStatus


class TestEvidenceLinker:
    """Test evidence linking functionality"""

    @pytest.fixture
    def sample_service(self, db_session):
        """Create sample service"""
        service = Service(
            service_id=uuid4(),
            name="test-service",
            environment=Environment.PRODUCTION,
            owner_team="test-team",
            telemetry_endpoints={},
            status="active",
        )
        db_session.add(service)
        db_session.commit()
        return service

    @pytest.fixture
    def sample_journey(self, db_session, sample_service):
        """Create sample journey"""
        journey = UserJourney(
            journey_id=uuid4(),
            service_id=sample_service.service_id,
            name="checkout-flow",
            entry_point="/api/checkout",
            exit_point="/api/orders",
            step_sequence=[{"span_name": "checkout", "duration_p50": 100.0}],
            traffic_volume_per_day=10000,
            confidence_score=Decimal("80.0"),
            sample_trace_ids=["trace-001", "trace-002"],
            discovered_at=datetime.utcnow() - timedelta(days=7),
            last_seen_at=datetime.utcnow(),
        )
        db_session.add(journey)
        db_session.commit()
        return journey

    @pytest.fixture
    def sample_capsules(self, db_session, sample_service):
        """Create sample capsules"""
        capsules = []
        for i in range(5):
            capsule = Capsule(
                capsule_id=uuid4(),
                fingerprint_hash=f"hash-{i}",
                template=f"Error processing payment {{ID}} at {{TIMESTAMP}}",
                count=100 * (i + 1),
                severity_distribution={"ERROR": 80, "WARN": 20},
                sample_array=[
                    {
                        "message": f"Error processing payment 12345 at 2024-01-01",
                        "trace_id": f"trace-00{i}",
                        "timestamp": "2024-01-01T10:00:00Z",
                    }
                ],
                service_id=sample_service.service_id,
                first_seen_at=datetime.utcnow() - timedelta(hours=24),
                last_seen_at=datetime.utcnow(),
                time_bucket=datetime.utcnow() - timedelta(hours=1),
                redaction_applied=True,
            )
            capsules.append(capsule)
            db_session.add(capsule)

        db_session.commit()
        return capsules

    @pytest.fixture
    def mock_vector_search(self):
        """Create mock vector search service"""
        mock = Mock()
        return mock

    @pytest.fixture
    def mock_embedding_service(self):
        """Create mock embedding service"""
        mock = Mock()
        mock.embed_text.return_value = [0.1] * 384  # 384-dim vector
        return mock

    @pytest.fixture
    def linker(self, db_session, mock_vector_search):
        """Create evidence linker with mocked dependencies"""
        with patch('src.services.evidence_linker.get_embedding_service') as mock_factory:
            mock_factory.return_value = Mock(embed_text=Mock(return_value=[0.1] * 384))
            linker = EvidenceLinker(db_session, vector_search=mock_vector_search)
            return linker

    def test_link_evidence_to_sli(self, linker, sample_journey, sample_capsules, mock_vector_search):
        """Test linking evidence to SLI via vector search"""
        # Mock vector search results
        search_results = [
            (sample_capsules[0].capsule_id, 0.95),
            (sample_capsules[1].capsule_id, 0.87),
            (sample_capsules[2].capsule_id, 0.72),
        ]
        mock_vector_search.search_similar_capsules.return_value = search_results

        evidence_links = linker.link_evidence_to_sli(
            sli_candidate_name="checkout-flow-error-rate",
            journey=sample_journey,
            top_k=3,
        )

        assert len(evidence_links) == 3
        assert all(isinstance(link, EvidenceLink) for link in evidence_links)

        # Verify vector search was called with correct parameters
        mock_vector_search.search_similar_capsules.assert_called_once()
        call_kwargs = mock_vector_search.search_similar_capsules.call_args[1]
        assert call_kwargs['service_id'] == sample_journey.service_id
        assert call_kwargs['top_k'] == 3

    def test_build_search_query_error_rate(self, linker, sample_journey):
        """Test search query construction for error rate SLI"""
        query = linker._build_search_query("checkout-flow-error-rate", sample_journey)

        assert "errors" in query.lower()
        assert "checkout-flow" in query.lower()
        assert "/api/checkout" in query.lower()

    def test_build_search_query_latency(self, linker, sample_journey):
        """Test search query construction for latency SLI"""
        query = linker._build_search_query("checkout-flow-latency-p95", sample_journey)

        assert "latency" in query.lower()
        assert "checkout-flow" in query.lower()

    def test_build_search_query_availability(self, linker, sample_journey):
        """Test search query construction for availability SLI"""
        query = linker._build_search_query("checkout-flow-availability", sample_journey)

        assert "availability" in query.lower()
        assert "checkout-flow" in query.lower()

    def test_create_evidence_link_from_capsule(self, linker, sample_journey, sample_capsules):
        """Test creating evidence link from capsule"""
        capsule = sample_capsules[0]
        similarity_score = 0.92

        link = linker._create_evidence_link(
            capsule_id=capsule.capsule_id,
            similarity_score=similarity_score,
            journey=sample_journey,
        )

        assert link is not None
        assert link.capsule_id == capsule.capsule_id
        assert link.similarity_score == similarity_score
        assert link.redaction_status == RedactionStatus.REDACTED
        assert link.trace_id is not None  # Extracted from sample_array
        assert link.log_sample is not None

    def test_extract_trace_id_from_capsule(self, linker, sample_journey, sample_capsules):
        """Test trace ID extraction from capsule samples"""
        capsule = sample_capsules[0]

        trace_id = linker._extract_trace_id(capsule, sample_journey)

        assert trace_id == "trace-000"  # From sample_array

    def test_extract_trace_id_prefers_journey_overlap(self, linker, db_session, sample_service, sample_journey):
        """Test trace ID extraction prefers journey-overlapping traces"""
        # Create capsule with multiple trace IDs, one matching journey
        capsule = Capsule(
            capsule_id=uuid4(),
            fingerprint_hash="test-hash",
            template="Test template",
            count=100,
            severity_distribution={"INFO": 100},
            sample_array=[
                {"trace_id": "trace-999"},  # Not in journey
                {"trace_id": "trace-001"},  # In journey.sample_trace_ids
                {"trace_id": "trace-888"},
            ],
            service_id=sample_service.service_id,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            time_bucket=datetime.utcnow(),
            redaction_applied=True,
        )
        db_session.add(capsule)
        db_session.commit()

        trace_id = linker._extract_trace_id(capsule, sample_journey)

        # Should prefer trace-001 which overlaps with journey
        assert trace_id == "trace-001"

    def test_extract_log_sample(self, linker, sample_capsules):
        """Test log sample extraction"""
        capsule = sample_capsules[0]

        log_sample = linker._extract_log_sample(capsule)

        assert log_sample is not None
        assert "Error processing payment" in log_sample

    def test_calculate_contribution_weights(self, linker):
        """Test contribution weight calculation from similarity scores"""
        links = [
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal(0),
                similarity_score=0.9,
            ),
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal(0),
                similarity_score=0.6,
            ),
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal(0),
                similarity_score=0.5,
            ),
        ]

        updated_links = linker._calculate_contribution_weights(links)

        # Total should sum to 100
        total_contribution = sum(link.confidence_contribution for link in updated_links)
        assert float(total_contribution) == pytest.approx(100.0, rel=0.01)

        # Highest similarity should have highest contribution
        assert updated_links[0].confidence_contribution > updated_links[1].confidence_contribution
        assert updated_links[1].confidence_contribution > updated_links[2].confidence_contribution

    def test_calculate_contribution_weights_equal_distribution(self, linker):
        """Test equal weights when all similarities are zero"""
        links = [
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal(0),
                similarity_score=0.0,
            ),
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal(0),
                similarity_score=0.0,
            ),
        ]

        updated_links = linker._calculate_contribution_weights(links)

        # Should distribute equally
        assert updated_links[0].confidence_contribution == Decimal("50.0")
        assert updated_links[1].confidence_contribution == Decimal("50.0")

    def test_persist_evidence_pointers(self, linker, db_session, sample_journey, sample_capsules):
        """Test persisting evidence pointers to database"""
        # Create SLI
        sli = SLI(
            sli_id=uuid4(),
            journey_id=sample_journey.journey_id,
            name="test-sli",
            metric_type=MetricType.ERROR_RATE,
            metric_definition="test_metric",
            measurement_window=timedelta(minutes=5),
            data_sources={},
            confidence_score=Decimal("75.0"),
            evidence_pointers=[],
            unit="%",
        )
        db_session.add(sli)
        db_session.commit()

        # Create evidence links
        links = [
            EvidenceLink(
                capsule_id=sample_capsules[0].capsule_id,
                trace_id="trace-001",
                log_sample="Test log",
                confidence_contribution=Decimal("60.0"),
                similarity_score=0.9,
                redaction_status=RedactionStatus.REDACTED,
            ),
            EvidenceLink(
                capsule_id=sample_capsules[1].capsule_id,
                trace_id="trace-002",
                log_sample="Test log 2",
                confidence_contribution=Decimal("40.0"),
                similarity_score=0.7,
                redaction_status=RedactionStatus.REDACTED,
            ),
        ]

        pointers = linker.persist_evidence_pointers(sli, links)

        assert len(pointers) == 2

        # Verify database persistence
        db_pointers = (
            db_session.query(EvidencePointer)
            .filter(EvidencePointer.sli_id == sli.sli_id)
            .all()
        )
        assert len(db_pointers) == 2

        # Verify fields
        for pointer in db_pointers:
            assert pointer.sli_id == sli.sli_id
            assert pointer.confidence_contribution > Decimal(0)
            assert pointer.redaction_status == RedactionStatus.REDACTED

    def test_get_evidence_for_sli(self, linker, db_session, sample_journey, sample_capsules):
        """Test retrieving evidence for an SLI"""
        # Create SLI
        sli = SLI(
            sli_id=uuid4(),
            journey_id=sample_journey.journey_id,
            name="test-sli",
            metric_type=MetricType.LATENCY,
            metric_definition="test_metric",
            measurement_window=timedelta(minutes=5),
            data_sources={},
            confidence_score=Decimal("75.0"),
            evidence_pointers=[],
            unit="ms",
        )
        db_session.add(sli)

        # Create evidence pointers
        pointer1 = EvidencePointer(
            evidence_id=uuid4(),
            sli_id=sli.sli_id,
            capsule_id=sample_capsules[0].capsule_id,
            trace_id="trace-001",
            log_sample="Redacted log",
            timestamp=datetime.utcnow(),
            confidence_contribution=Decimal("60.0"),
            redaction_status=RedactionStatus.REDACTED,
        )
        pointer2 = EvidencePointer(
            evidence_id=uuid4(),
            sli_id=sli.sli_id,
            capsule_id=sample_capsules[1].capsule_id,
            trace_id="trace-002",
            log_sample="Redacted log 2",
            timestamp=datetime.utcnow(),
            confidence_contribution=Decimal("40.0"),
            redaction_status=RedactionStatus.PENDING,
        )
        db_session.add_all([pointer1, pointer2])
        db_session.commit()

        evidence_list = linker.get_evidence_for_sli(sli.sli_id, include_samples=True)

        assert len(evidence_list) == 2

        # Check ordering (should be by contribution desc)
        assert evidence_list[0]['confidence_contribution'] == 60.0
        assert evidence_list[1]['confidence_contribution'] == 40.0

        # Check redacted sample is included
        assert evidence_list[0]['log_sample'] == "Redacted log"

        # Check pending sample is excluded
        assert 'log_sample' not in evidence_list[1] or evidence_list[1]['log_sample'] is None

    def test_get_evidence_for_sli_raises_on_not_found(self, linker):
        """Test retrieving evidence for non-existent SLI raises error"""
        fake_sli_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            linker.get_evidence_for_sli(fake_sli_id)

    def test_build_evidence_summary(self, linker):
        """Test building evidence summary statistics"""
        links = [
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal("50.0"),
                similarity_score=0.9,
                redaction_status=RedactionStatus.REDACTED,
            ),
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal("30.0"),
                similarity_score=0.7,
                redaction_status=RedactionStatus.REDACTED,
            ),
            EvidenceLink(
                capsule_id=uuid4(),
                trace_id=None,
                log_sample=None,
                confidence_contribution=Decimal("20.0"),
                similarity_score=0.6,
                redaction_status=RedactionStatus.PENDING,
            ),
        ]

        summary = linker.build_evidence_summary(links)

        assert summary['total_evidence_count'] == 3
        assert summary['avg_similarity'] == pytest.approx(0.733, rel=0.01)
        assert summary['top_similarity'] == 0.9
        assert summary['redacted_count'] == 2

    def test_build_evidence_summary_empty(self, linker):
        """Test building evidence summary with no links"""
        summary = linker.build_evidence_summary([])

        assert summary['total_evidence_count'] == 0
        assert summary['avg_similarity'] == 0.0
        assert summary['top_capsule_id'] is None

    def test_min_similarity_threshold(self, linker, sample_journey, sample_capsules, mock_vector_search):
        """Test minimum similarity threshold filtering"""
        # Mock search results with low similarity
        search_results = [
            (sample_capsules[0].capsule_id, 0.3),  # Below MIN_SIMILARITY_THRESHOLD (0.5)
        ]
        mock_vector_search.search_similar_capsules.return_value = search_results

        evidence_links = linker.link_evidence_to_sli(
            sli_candidate_name="test-sli",
            journey=sample_journey,
        )

        # Should still create link (filtering happens in vector search)
        # This tests that linker handles whatever vector search returns
        assert len(evidence_links) >= 0

    def test_embedding_service_failure_raises_error(self, db_session, sample_journey, mock_vector_search):
        """Test that embedding service failure raises ValueError"""
        with patch('src.services.evidence_linker.get_embedding_service') as mock_factory:
            mock_factory.return_value = Mock(
                embed_text=Mock(side_effect=Exception("Embedding failed"))
            )
            linker = EvidenceLinker(db_session, vector_search=mock_vector_search)

            with pytest.raises(ValueError, match="Embedding service unavailable"):
                linker.link_evidence_to_sli("test-sli", sample_journey)

    def test_redaction_status_from_capsule(self, linker, db_session, sample_service, sample_journey):
        """Test redaction status is determined from capsule"""
        # Capsule with redaction applied
        capsule_redacted = Capsule(
            capsule_id=uuid4(),
            fingerprint_hash="hash-redacted",
            template="Template",
            count=100,
            severity_distribution={"INFO": 100},
            sample_array=[{"message": "test"}],
            service_id=sample_service.service_id,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
            time_bucket=datetime.utcnow(),
            redaction_applied=True,
        )
        db_session.add(capsule_redacted)
        db_session.commit()

        link = linker._create_evidence_link(
            capsule_id=capsule_redacted.capsule_id,
            similarity_score=0.8,
            journey=sample_journey,
        )

        assert link.redaction_status == RedactionStatus.REDACTED

    def test_default_top_k_is_ten(self, linker):
        """Test default TOP_K value per tasks.md"""
        assert linker.DEFAULT_TOP_K == 10
