"""
Evidence Linker Service

Links SLI recommendations to supporting evidence via:
- Vector search against capsule embeddings
- Evidence pointer creation with contribution weights
- Trace and log sample extraction

Per spec.md FR-016, FR-017 and tasks.md T092
"""
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
from datetime import datetime, timedelta
from uuid import UUID
import logging

from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models.sli import SLI
from ..models.user_journey import UserJourney
from ..models.capsule import Capsule
from ..models.evidence_pointer import EvidencePointer, RedactionStatus
from .vector_search import VectorSearchService
from ..embeddings.factory import get_embedding_service


logger = logging.getLogger(__name__)


class EvidenceLink:
    """
    Data class representing an evidence link before persistence
    """
    def __init__(
        self,
        capsule_id: UUID,
        trace_id: Optional[str],
        log_sample: Optional[str],
        confidence_contribution: Decimal,
        similarity_score: float,
        redaction_status: RedactionStatus = RedactionStatus.PENDING,
    ):
        self.capsule_id = capsule_id
        self.trace_id = trace_id
        self.log_sample = log_sample
        self.confidence_contribution = confidence_contribution
        self.similarity_score = similarity_score
        self.redaction_status = redaction_status


class EvidenceLinker:
    """
    Link SLI recommendations to supporting evidence

    Per spec.md:
    - FR-016: Evidence pointers for every SLI/SLO recommendation
    - FR-017: Drill down to raw telemetry samples with PII redaction

    Per data-model.md:
    - EvidencePointer: capsule_id, trace_id, log_sample
    - confidence_contribution: 0-100
    - redaction_status: redacted | safe | pending
    """

    # Top-K capsules to retrieve for each SLI
    DEFAULT_TOP_K = 10

    # Minimum similarity score threshold
    MIN_SIMILARITY_THRESHOLD = 0.5

    def __init__(self, db: Session, vector_search: Optional[VectorSearchService] = None):
        self.db = db
        self.vector_search = vector_search or VectorSearchService(db)
        self.embedding_service = get_embedding_service()

    def link_evidence_to_sli(
        self,
        sli_candidate_name: str,
        journey: UserJourney,
        top_k: int = DEFAULT_TOP_K,
    ) -> List[EvidenceLink]:
        """
        Find and rank evidence supporting an SLI recommendation

        Args:
            sli_candidate_name: Name of SLI candidate (e.g., "checkout-latency-p95")
            journey: UserJourney entity
            top_k: Number of top evidence items to return

        Returns:
            List of EvidenceLink objects ordered by relevance

        Raises:
            ValueError: If embedding service unavailable
        """
        logger.info(
            f"Linking evidence for SLI '{sli_candidate_name}' "
            f"on journey {journey.name}"
        )

        # Build search query from SLI name and journey context
        search_query = self._build_search_query(sli_candidate_name, journey)

        # Generate embedding for search query
        try:
            query_embedding = self.embedding_service.embed_text(search_query)
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise ValueError(f"Embedding service unavailable: {e}")

        # Perform vector search against capsules
        capsule_results = self.vector_search.search_similar_capsules(
            query_embedding=query_embedding,
            service_id=journey.service_id,
            top_k=top_k,
            min_similarity=self.MIN_SIMILARITY_THRESHOLD,
            time_range=(journey.discovered_at, journey.last_seen_at),
        )

        logger.info(f"Found {len(capsule_results)} relevant capsules")

        # Convert search results to evidence links
        evidence_links = []
        for capsule_id, similarity_score in capsule_results:
            link = self._create_evidence_link(
                capsule_id=capsule_id,
                similarity_score=similarity_score,
                journey=journey,
            )
            if link:
                evidence_links.append(link)

        # Calculate contribution weights
        evidence_links = self._calculate_contribution_weights(evidence_links)

        logger.info(
            f"Created {len(evidence_links)} evidence links for SLI {sli_candidate_name}"
        )

        return evidence_links

    def _build_search_query(
        self,
        sli_name: str,
        journey: UserJourney,
    ) -> str:
        """
        Build semantic search query from SLI and journey context

        Args:
            sli_name: SLI candidate name
            journey: UserJourney entity

        Returns:
            Search query string for embedding
        """
        # Extract metric type from SLI name
        metric_type = "performance"
        if "error" in sli_name.lower():
            metric_type = "errors"
        elif "availability" in sli_name.lower():
            metric_type = "availability"
        elif "latency" in sli_name.lower():
            metric_type = "latency"

        # Build query combining journey and metric context
        query = (
            f"{metric_type} issues in {journey.name} "
            f"endpoint {journey.entry_point} "
            f"user journey flow"
        )

        return query

    def _create_evidence_link(
        self,
        capsule_id: UUID,
        similarity_score: float,
        journey: UserJourney,
    ) -> Optional[EvidenceLink]:
        """
        Create evidence link from capsule search result

        Args:
            capsule_id: UUID of relevant capsule
            similarity_score: Vector similarity score
            journey: UserJourney entity

        Returns:
            EvidenceLink or None if capsule not found
        """
        # Fetch capsule details
        capsule = self.db.query(Capsule).filter(
            Capsule.capsule_id == capsule_id
        ).first()

        if not capsule:
            logger.warning(f"Capsule {capsule_id} not found")
            return None

        # Extract sample trace ID and log sample
        trace_id = self._extract_trace_id(capsule, journey)
        log_sample = self._extract_log_sample(capsule)

        # Determine redaction status
        redaction_status = (
            RedactionStatus.REDACTED if capsule.redaction_applied
            else RedactionStatus.PENDING
        )

        # Placeholder contribution (calculated later)
        contribution = Decimal(0)

        return EvidenceLink(
            capsule_id=capsule_id,
            trace_id=trace_id,
            log_sample=log_sample,
            confidence_contribution=contribution,
            similarity_score=similarity_score,
            redaction_status=redaction_status,
        )

    def _extract_trace_id(
        self,
        capsule: Capsule,
        journey: UserJourney,
    ) -> Optional[str]:
        """
        Extract representative trace ID from capsule samples

        Prefers traces matching the journey's sample traces

        Args:
            capsule: Capsule entity
            journey: UserJourney entity

        Returns:
            Trace ID or None
        """
        if not capsule.sample_array:
            return None

        # Prefer traces that overlap with journey samples
        journey_traces = set(journey.sample_trace_ids) if journey.sample_trace_ids else set()

        for sample in capsule.sample_array:
            sample_trace_id = sample.get("trace_id")
            if sample_trace_id:
                # Prioritize journey-overlapping traces
                if sample_trace_id in journey_traces:
                    return sample_trace_id

        # Fallback: first available trace ID
        for sample in capsule.sample_array:
            sample_trace_id = sample.get("trace_id")
            if sample_trace_id:
                return sample_trace_id

        return None

    def _extract_log_sample(self, capsule: Capsule) -> Optional[str]:
        """
        Extract representative log sample from capsule

        Args:
            capsule: Capsule entity

        Returns:
            Redacted log message or None
        """
        if not capsule.sample_array:
            return None

        # Use first sample (reservoir ensures representativeness)
        first_sample = capsule.sample_array[0]
        return first_sample.get("message", capsule.template)

    def _calculate_contribution_weights(
        self,
        evidence_links: List[EvidenceLink],
    ) -> List[EvidenceLink]:
        """
        Calculate confidence contribution weights for evidence

        Uses normalized similarity scores

        Args:
            evidence_links: List of EvidenceLink objects

        Returns:
            Updated evidence_links with contribution weights
        """
        if not evidence_links:
            return evidence_links

        # Extract similarity scores
        scores = [link.similarity_score for link in evidence_links]
        total_score = sum(scores)

        if total_score == 0:
            # Equal weights if all zero
            equal_weight = Decimal(100) / len(evidence_links)
            for link in evidence_links:
                link.confidence_contribution = equal_weight
            return evidence_links

        # Normalize to 0-100 scale
        for link in evidence_links:
            normalized = (link.similarity_score / total_score) * 100
            link.confidence_contribution = Decimal(str(normalized))

        return evidence_links

    def persist_evidence_pointers(
        self,
        sli: SLI,
        evidence_links: List[EvidenceLink],
    ) -> List[EvidencePointer]:
        """
        Persist evidence links as EvidencePointer entities

        Args:
            sli: SLI entity to link evidence to
            evidence_links: List of EvidenceLink objects

        Returns:
            List of persisted EvidencePointer entities
        """
        pointers: List[EvidencePointer] = []

        for link in evidence_links:
            pointer = EvidencePointer(
                sli_id=sli.sli_id,
                capsule_id=link.capsule_id,
                trace_id=link.trace_id,
                log_sample=link.log_sample,
                timestamp=datetime.utcnow(),
                confidence_contribution=link.confidence_contribution,
                redaction_status=link.redaction_status,
            )

            self.db.add(pointer)
            pointers.append(pointer)

            logger.debug(
                f"Created evidence pointer: capsule={link.capsule_id}, "
                f"contribution={link.confidence_contribution:.2f}%"
            )

        self.db.commit()

        logger.info(f"Persisted {len(pointers)} evidence pointers for SLI {sli.name}")

        return pointers

    def get_evidence_for_sli(
        self,
        sli_id: UUID,
        include_samples: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve evidence for an existing SLI

        Per spec.md FR-017: Drill down to raw telemetry samples

        Args:
            sli_id: UUID of SLI
            include_samples: Whether to include raw log samples

        Returns:
            List of evidence dictionaries with metadata

        Raises:
            ValueError: If SLI not found
        """
        sli = self.db.query(SLI).filter(SLI.sli_id == sli_id).first()
        if not sli:
            raise ValueError(f"SLI {sli_id} not found")

        # Query evidence pointers
        pointers = (
            self.db.query(EvidencePointer)
            .filter(EvidencePointer.sli_id == sli_id)
            .order_by(EvidencePointer.confidence_contribution.desc())
            .all()
        )

        evidence_list = []
        for pointer in pointers:
            evidence_dict = {
                "evidence_id": str(pointer.evidence_id),
                "capsule_id": str(pointer.capsule_id) if pointer.capsule_id else None,
                "trace_id": pointer.trace_id,
                "timestamp": pointer.timestamp.isoformat(),
                "confidence_contribution": float(pointer.confidence_contribution),
                "redaction_status": pointer.redaction_status.value,
            }

            # Include log sample if requested and redacted
            if include_samples and pointer.redaction_status == RedactionStatus.REDACTED:
                evidence_dict["log_sample"] = pointer.log_sample

            evidence_list.append(evidence_dict)

        return evidence_list

    def build_evidence_summary(
        self,
        evidence_links: List[EvidenceLink],
    ) -> Dict[str, Any]:
        """
        Build summary of evidence for API responses

        Args:
            evidence_links: List of EvidenceLink objects

        Returns:
            Summary dictionary with aggregate statistics
        """
        if not evidence_links:
            return {
                "total_evidence_count": 0,
                "avg_similarity": 0.0,
                "top_capsule_id": None,
            }

        avg_similarity = sum(link.similarity_score for link in evidence_links) / len(evidence_links)
        top_link = max(evidence_links, key=lambda l: l.similarity_score)

        return {
            "total_evidence_count": len(evidence_links),
            "avg_similarity": avg_similarity,
            "top_capsule_id": str(top_link.capsule_id),
            "top_similarity": top_link.similarity_score,
            "redacted_count": sum(
                1 for link in evidence_links
                if link.redaction_status == RedactionStatus.REDACTED
            ),
        }
