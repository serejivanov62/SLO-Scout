"""
RAG context builder per T083
Takes query embedding, retrieves top-K capsules
Builds LLM prompt with capsule templates + aggregated metrics
"""
from typing import List, Dict, Optional

from ..services.vector_search import VectorSearchService
from ..services.capsule_retrieval import CapsuleRetrievalService


class RAGContextBuilder:
    """
    Builds context for RAG-based LLM prompts

    Per spec.md FR-016: Provides evidence pointers for SLI/SLO recommendations
    """

    def __init__(
        self,
        vector_search: VectorSearchService,
        capsule_retrieval: CapsuleRetrievalService
    ):
        self.vector_search = vector_search
        self.capsule_retrieval = capsule_retrieval

    def build_context(
        self,
        query_embedding: List[float],
        service_name: str,
        top_k: int = 10,
        time_range_days: int = 30
    ) -> Dict:
        """
        Build RAG context for LLM prompt

        Args:
            query_embedding: Query vector (from service analysis)
            service_name: Service to analyze
            top_k: Number of similar capsules to retrieve
            time_range_days: Time window for historical data

        Returns:
            Context dictionary:
            {
                "capsules": [...],  # Top-K similar capsules
                "aggregated_metrics": {...},  # Summary statistics
                "evidence_pointers": [...],  # Capsule IDs for traceability
                "service_context": {...}  # Service metadata
            }
        """
        # Step 1: Vector search for similar capsules
        search_results = self.vector_search.search_similar_capsules(
            query_embedding=query_embedding,
            top_k=top_k,
            service_name=service_name,
            time_range_days=time_range_days
        )

        # Step 2: Retrieve full capsule data
        capsule_ids = [result['capsule_id'] for result in search_results]
        from uuid import UUID
        evidence = self.capsule_retrieval.get_evidence_for_sli(
            capsule_ids=[UUID(cid) for cid in capsule_ids],
            include_samples=True
        )

        # Step 3: Aggregate metrics
        aggregated_metrics = self._aggregate_metrics(evidence)

        # Step 4: Build context
        context = {
            "capsules": evidence,
            "aggregated_metrics": aggregated_metrics,
            "evidence_pointers": [
                {
                    "capsule_id": ev["capsule_id"],
                    "confidence_contribution": ev["confidence_contribution"]
                }
                for ev in evidence
            ],
            "service_context": {
                "service_name": service_name,
                "time_range_days": time_range_days,
                "capsule_count": len(evidence)
            }
        }

        return context

    def build_prompt(
        self,
        context: Dict,
        task: str = "sli_recommendation"
    ) -> str:
        """
        Build LLM prompt from RAG context

        Args:
            context: Context dictionary from build_context()
            task: Task type ("sli_recommendation", "slo_thresholds", etc.)

        Returns:
            Formatted prompt string
        """
        if task == "sli_recommendation":
            return self._build_sli_prompt(context)
        elif task == "slo_thresholds":
            return self._build_slo_prompt(context)
        else:
            raise ValueError(f"Unknown task: {task}")

    def _aggregate_metrics(self, evidence: List[Dict]) -> Dict:
        """
        Aggregate metrics from capsules

        Returns:
            {
                "total_events": int,
                "unique_templates": int,
                "severity_distribution": {...},
                "top_templates": [...]
            }
        """
        total_events = sum(ev["count"] for ev in evidence)
        unique_templates = len(set(ev["template"] for ev in evidence))

        # Count severity distribution (if available)
        severity_dist = {}
        for ev in evidence:
            # TODO: Extract severity from capsule data
            pass

        # Top templates by count
        top_templates = sorted(
            evidence,
            key=lambda ev: ev["count"],
            reverse=True
        )[:5]

        return {
            "total_events": total_events,
            "unique_templates": unique_templates,
            "severity_distribution": severity_dist,
            "top_templates": [
                {
                    "template": t["template"],
                    "count": t["count"]
                }
                for t in top_templates
            ]
        }

    def _build_sli_prompt(self, context: Dict) -> str:
        """Build prompt for SLI recommendation task"""
        service_name = context["service_context"]["service_name"]
        capsule_count = context["service_context"]["capsule_count"]
        total_events = context["aggregated_metrics"]["total_events"]

        prompt = f"""You are analyzing telemetry data for service "{service_name}".

Based on analysis of {total_events} events across {capsule_count} log patterns, recommend Service Level Indicators (SLIs).

Top log patterns observed:
"""
        # Add top templates
        for template_info in context["aggregated_metrics"]["top_templates"]:
            prompt += f"- {template_info['template']} (count: {template_info['count']})\n"

        prompt += """
Recommend 3-5 SLIs that best reflect user experience for this service.
For each SLI, provide:
1. Name (e.g., "checkout-latency-p95")
2. Metric type (latency, availability, error_rate)
3. PromQL definition
4. Confidence score (0-100) based on data coverage

Output as JSON array.
"""
        return prompt

    def _build_slo_prompt(self, context: Dict) -> str:
        """Build prompt for SLO threshold recommendation"""
        # TODO: Implement SLO threshold prompt
        return ""
