"""
LLM recommender per T095
RAG retrieval → build prompt → call LLM → validate response schema
Returns SLI recommendations with evidence pointers
"""
import logging
from typing import List, Dict, Optional, Any
from uuid import UUID
from dataclasses import dataclass

from jsonschema import validate, ValidationError

from .llm_client import LLMClient, LLMConfig, LLMError, LLMValidationError
from .prompts import PromptTemplateManager, PromptTask
from .rag_builder import RAGContextBuilder
from .vector_search import VectorSearchService
from ..embeddings.embedding_service import EmbeddingService


logger = logging.getLogger(__name__)


@dataclass
class SLIRecommendation:
    """
    SLI recommendation result

    Attributes:
        name: SLI name
        metric_type: Type of metric (latency, availability, etc.)
        promql: PromQL query definition
        unit: Unit of measurement
        confidence_score: Confidence in recommendation (0-100)
        rationale: Explanation for recommendation
        evidence_capsule_ids: Supporting capsule IDs
    """
    name: str
    metric_type: str
    promql: str
    unit: str
    confidence_score: float
    rationale: str
    evidence_capsule_ids: List[str]


@dataclass
class SLOVariant:
    """
    SLO threshold variant

    Attributes:
        variant: Variant type (conservative, balanced, aggressive)
        threshold_value: Threshold value
        target_percentage: Target percentage (e.g., 99.9%)
        time_window: Time window (e.g., 30d)
        expected_breach_frequency: Expected breach frequency
        rationale: Explanation for threshold
    """
    variant: str
    threshold_value: float
    target_percentage: float
    time_window: str
    expected_breach_frequency: str
    rationale: str


@dataclass
class InstrumentationRecommendation:
    """
    Instrumentation improvement recommendation

    Attributes:
        type: Recommendation type
        description: What to implement
        code_snippet: Example code (optional)
        expected_confidence_uplift: Expected confidence improvement
        priority: Priority level
        effort: Implementation effort
    """
    type: str
    description: str
    code_snippet: Optional[str]
    expected_confidence_uplift: float
    priority: str
    effort: str


class LLMRecommenderService:
    """
    LLM-based recommendation service with RAG retrieval

    Per spec.md FR-002: Generates top 5 SLI recommendations per journey
    Per spec.md FR-004: Recommends 3 SLO threshold variants
    Per spec.md FR-016: Provides evidence pointers for recommendations

    Implementation flow:
    1. RAG retrieval: Get relevant capsules from vector DB
    2. Build prompt: Construct few-shot prompt with context
    3. Call LLM: Get structured JSON response
    4. Validate: Check response against JSON schema
    5. Return: Structured recommendations with evidence

    Usage:
        recommender = LLMRecommenderService(llm_client, rag_builder, ...)
        recommendations = await recommender.recommend_slis(
            service_name="payment-api",
            data_quality={"rum_coverage": 75.0, ...}
        )
    """

    def __init__(
        self,
        llm_client: LLMClient,
        rag_builder: RAGContextBuilder,
        embedding_service: EmbeddingService,
        prompt_manager: Optional[PromptTemplateManager] = None
    ):
        """
        Initialize LLM recommender service

        Args:
            llm_client: LLM API client
            rag_builder: RAG context builder
            embedding_service: Embedding service for queries
            prompt_manager: Prompt template manager (creates if None)
        """
        self.llm_client = llm_client
        self.rag_builder = rag_builder
        self.embedding_service = embedding_service
        self.prompt_manager = prompt_manager or PromptTemplateManager()

        logger.info("Initialized LLM recommender service")

    async def recommend_slis(
        self,
        service_name: str,
        environment: str = "production",
        data_quality: Optional[Dict[str, float]] = None,
        top_k_capsules: int = 10,
        time_range_days: int = 30
    ) -> List[SLIRecommendation]:
        """
        Generate SLI recommendations using LLM + RAG

        Args:
            service_name: Service to analyze
            environment: Environment (production, staging, etc.)
            data_quality: Data quality metrics
            top_k_capsules: Number of capsules to retrieve
            time_range_days: Historical time window

        Returns:
            List of SLI recommendations

        Raises:
            LLMError: On LLM API errors
            LLMValidationError: On response validation errors
        """
        logger.info(
            f"Generating SLI recommendations for service={service_name}, "
            f"environment={environment}"
        )

        # Step 1: Generate query embedding
        query_text = f"Service level indicators for {service_name}"
        query_embedding = self.embedding_service.embed_text(query_text)

        # Step 2: RAG retrieval
        context = self.rag_builder.build_context(
            query_embedding=query_embedding.tolist(),
            service_name=service_name,
            top_k=top_k_capsules,
            time_range_days=time_range_days
        )

        logger.debug(
            f"RAG context built: {context['service_context']['capsule_count']} capsules, "
            f"{context['aggregated_metrics']['total_events']} events"
        )

        # Step 3: Build prompt
        messages = self.prompt_manager.build_sli_recommendation_prompt(
            service_name=service_name,
            capsules=context['capsules'],
            aggregated_metrics=context['aggregated_metrics'],
            data_quality=data_quality
        )

        # Step 4: Call LLM with schema enforcement
        schema = self.prompt_manager.get_schema(PromptTask.SLI_RECOMMENDATION)

        try:
            response = await self.llm_client.chat_completion(
                messages=messages,
                response_schema=schema
            )

            # Extract usage metrics
            usage = self.llm_client.get_usage(response)
            logger.info(
                f"LLM call completed: {usage['total_tokens']} tokens "
                f"(prompt={usage['prompt_tokens']}, completion={usage['completion_tokens']})"
            )

            # Step 5: Parse and validate response
            result_json = self.llm_client.extract_json(response)
            self._validate_response(result_json, schema)

            # Step 6: Convert to structured recommendations
            recommendations = self._parse_sli_recommendations(
                result_json,
                context['evidence_pointers']
            )

            logger.info(f"Generated {len(recommendations)} SLI recommendations")

            return recommendations

        except LLMError as e:
            logger.error(f"LLM API error during SLI recommendation: {str(e)}")
            raise

        except ValidationError as e:
            logger.error(f"Response validation failed: {str(e)}")
            raise LLMValidationError(f"Invalid response schema: {str(e)}")

    async def recommend_slo_thresholds(
        self,
        sli_name: str,
        sli_type: str,
        historical_percentiles: Dict[str, float],
        current_value: float,
        service_context: Optional[Dict[str, Any]] = None
    ) -> List[SLOVariant]:
        """
        Generate SLO threshold recommendations

        Args:
            sli_name: SLI name
            sli_type: SLI type (latency, availability, etc.)
            historical_percentiles: Historical performance percentiles
            current_value: Current SLI value
            service_context: Additional service context

        Returns:
            List of 3 SLO variants (conservative, balanced, aggressive)

        Raises:
            LLMError: On LLM API errors
            LLMValidationError: On response validation errors
        """
        logger.info(f"Generating SLO thresholds for SLI={sli_name}")

        # Build prompt
        messages = self.prompt_manager.build_slo_threshold_prompt(
            sli_name=sli_name,
            sli_type=sli_type,
            historical_percentiles=historical_percentiles,
            current_value=current_value,
            service_context=service_context
        )

        # Call LLM with schema
        schema = self.prompt_manager.get_schema(PromptTask.SLO_THRESHOLD)

        try:
            response = await self.llm_client.chat_completion(
                messages=messages,
                response_schema=schema
            )

            # Parse response
            result_json = self.llm_client.extract_json(response)
            self._validate_response(result_json, schema)

            # Convert to structured variants
            variants = self._parse_slo_variants(result_json)

            logger.info(f"Generated {len(variants)} SLO threshold variants")

            return variants

        except LLMError as e:
            logger.error(f"LLM API error during SLO threshold recommendation: {str(e)}")
            raise

        except ValidationError as e:
            logger.error(f"Response validation failed: {str(e)}")
            raise LLMValidationError(f"Invalid response schema: {str(e)}")

    async def recommend_instrumentation(
        self,
        service_name: str,
        data_quality: Dict[str, float],
        current_confidence: float,
        technology_stack: Optional[List[str]] = None
    ) -> List[InstrumentationRecommendation]:
        """
        Generate instrumentation improvement recommendations

        Args:
            service_name: Service being analyzed
            data_quality: Current data quality metrics
            current_confidence: Current recommendation confidence
            technology_stack: Service technologies

        Returns:
            List of instrumentation recommendations

        Raises:
            LLMError: On LLM API errors
            LLMValidationError: On response validation errors
        """
        logger.info(f"Generating instrumentation advice for service={service_name}")

        # Build prompt
        messages = self.prompt_manager.build_instrumentation_advice_prompt(
            service_name=service_name,
            data_quality=data_quality,
            current_confidence=current_confidence,
            technology_stack=technology_stack
        )

        # Call LLM with schema
        schema = self.prompt_manager.get_schema(PromptTask.INSTRUMENTATION_ADVICE)

        try:
            response = await self.llm_client.chat_completion(
                messages=messages,
                response_schema=schema
            )

            # Parse response
            result_json = self.llm_client.extract_json(response)
            self._validate_response(result_json, schema)

            # Convert to structured recommendations
            recommendations = self._parse_instrumentation_recommendations(result_json)

            logger.info(f"Generated {len(recommendations)} instrumentation recommendations")

            return recommendations

        except LLMError as e:
            logger.error(f"LLM API error during instrumentation recommendation: {str(e)}")
            raise

        except ValidationError as e:
            logger.error(f"Response validation failed: {str(e)}")
            raise LLMValidationError(f"Invalid response schema: {str(e)}")

    def _validate_response(self, response: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Validate LLM response against JSON schema

        Args:
            response: Response JSON
            schema: JSON schema

        Raises:
            ValidationError: If validation fails
        """
        validate(instance=response, schema=schema)
        logger.debug("Response validation passed")

    def _parse_sli_recommendations(
        self,
        result_json: Dict[str, Any],
        evidence_pointers: List[Dict[str, Any]]
    ) -> List[SLIRecommendation]:
        """
        Parse SLI recommendations from LLM response

        Args:
            result_json: LLM response JSON
            evidence_pointers: Evidence pointers from RAG

        Returns:
            List of SLIRecommendation objects
        """
        recommendations = []

        for sli_data in result_json.get('slis', []):
            # Merge evidence from RAG context
            capsule_ids = sli_data.get('evidence_capsule_ids', [])
            if not capsule_ids:
                # Use top capsules from evidence
                capsule_ids = [ep['capsule_id'] for ep in evidence_pointers[:3]]

            recommendations.append(SLIRecommendation(
                name=sli_data['name'],
                metric_type=sli_data['metric_type'],
                promql=sli_data['promql'],
                unit=sli_data['unit'],
                confidence_score=sli_data['confidence_score'],
                rationale=sli_data['rationale'],
                evidence_capsule_ids=capsule_ids
            ))

        return recommendations

    def _parse_slo_variants(self, result_json: Dict[str, Any]) -> List[SLOVariant]:
        """
        Parse SLO variants from LLM response

        Args:
            result_json: LLM response JSON

        Returns:
            List of SLOVariant objects
        """
        variants = []

        for variant_data in result_json.get('variants', []):
            variants.append(SLOVariant(
                variant=variant_data['variant'],
                threshold_value=variant_data['threshold_value'],
                target_percentage=variant_data['target_percentage'],
                time_window=variant_data['time_window'],
                expected_breach_frequency=variant_data['expected_breach_frequency'],
                rationale=variant_data['rationale']
            ))

        return variants

    def _parse_instrumentation_recommendations(
        self,
        result_json: Dict[str, Any]
    ) -> List[InstrumentationRecommendation]:
        """
        Parse instrumentation recommendations from LLM response

        Args:
            result_json: LLM response JSON

        Returns:
            List of InstrumentationRecommendation objects
        """
        recommendations = []

        for rec_data in result_json.get('recommendations', []):
            recommendations.append(InstrumentationRecommendation(
                type=rec_data['type'],
                description=rec_data['description'],
                code_snippet=rec_data.get('code_snippet'),
                expected_confidence_uplift=rec_data['expected_confidence_uplift'],
                priority=rec_data['priority'],
                effort=rec_data['effort']
            ))

        return recommendations
