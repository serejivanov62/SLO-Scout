"""
Unit tests for LLM Recommender Service

Tests T099: LLM integration
- Mock LLM API
- Assert structured response
- Assert hallucination detection (response validation)
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from decimal import Decimal
from typing import Dict, Any, List
import json

from src.services.llm_recommender import (
    LLMRecommenderService,
    SLIRecommendation,
    SLOVariant,
    InstrumentationRecommendation
)
from src.services.llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMError,
    LLMRateLimitError,
    LLMValidationError
)
from src.services.prompts import PromptTemplateManager, PromptTask
from src.services.rag_builder import RAGContextBuilder
from src.embeddings.embedding_service import EmbeddingService


class TestLLMRecommenderService:
    """Test LLM-based recommendation service"""

    @pytest.fixture
    def mock_llm_client(self) -> AsyncMock:
        """Create mock LLM client"""
        client = AsyncMock(spec=LLMClient)
        client.config = LLMConfig(
            provider=LLMProvider.LOCAL,
            model="test-model"
        )
        return client

    @pytest.fixture
    def mock_rag_builder(self) -> Mock:
        """Create mock RAG context builder"""
        builder = Mock(spec=RAGContextBuilder)

        # Default context response
        builder.build_context.return_value = {
            'service_context': {
                'service_name': 'test-service',
                'capsule_count': 50,
                'time_range_days': 30
            },
            'capsules': [
                {
                    'capsule_id': 'capsule-001',
                    'template': 'User {{USER_ID}} logged in from {{IP}}',
                    'count': 1000,
                    'severity_distribution': {'INFO': 900, 'WARN': 100}
                },
                {
                    'capsule_id': 'capsule-002',
                    'template': 'Payment {{PAYMENT_ID}} processed successfully',
                    'count': 500,
                    'severity_distribution': {'INFO': 500}
                }
            ],
            'aggregated_metrics': {
                'total_events': 150000,
                'error_rate': 0.02,
                'avg_latency_ms': 250.0
            },
            'evidence_pointers': [
                {'capsule_id': 'capsule-001', 'confidence_contribution': 60.0},
                {'capsule_id': 'capsule-002', 'confidence_contribution': 40.0}
            ]
        }

        return builder

    @pytest.fixture
    def mock_embedding_service(self) -> Mock:
        """Create mock embedding service"""
        service = Mock(spec=EmbeddingService)

        # Return mock embedding vector
        import numpy as np
        service.embed_text.return_value = np.random.rand(384)

        return service

    @pytest.fixture
    def mock_prompt_manager(self) -> Mock:
        """Create mock prompt template manager"""
        manager = Mock(spec=PromptTemplateManager)

        # Default prompts
        manager.build_sli_recommendation_prompt.return_value = [
            {"role": "system", "content": "You are an SRE expert."},
            {"role": "user", "content": "Recommend SLIs for test-service"}
        ]

        manager.build_slo_threshold_prompt.return_value = [
            {"role": "system", "content": "You are an SRE expert."},
            {"role": "user", "content": "Recommend SLO thresholds"}
        ]

        manager.build_instrumentation_advice_prompt.return_value = [
            {"role": "system", "content": "You are an observability expert."},
            {"role": "user", "content": "Recommend instrumentation improvements"}
        ]

        # Default schemas
        manager.get_schema.return_value = {
            "type": "object",
            "properties": {
                "slis": {"type": "array"}
            },
            "required": ["slis"]
        }

        return manager

    @pytest.fixture
    def recommender(
        self,
        mock_llm_client,
        mock_rag_builder,
        mock_embedding_service,
        mock_prompt_manager
    ) -> LLMRecommenderService:
        """Create LLM recommender service instance"""
        return LLMRecommenderService(
            llm_client=mock_llm_client,
            rag_builder=mock_rag_builder,
            embedding_service=mock_embedding_service,
            prompt_manager=mock_prompt_manager
        )

    @pytest.fixture
    def valid_sli_response(self) -> Dict[str, Any]:
        """Valid LLM response for SLI recommendations"""
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "slis": [
                                {
                                    "name": "test-service-latency-p95",
                                    "metric_type": "latency",
                                    "promql": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
                                    "unit": "ms",
                                    "confidence_score": 85.5,
                                    "rationale": "Based on high traffic volume and complete trace data",
                                    "evidence_capsule_ids": ["capsule-001", "capsule-002"]
                                },
                                {
                                    "name": "test-service-error-rate",
                                    "metric_type": "error_rate",
                                    "promql": "rate(http_requests_total{status_code=~\"5..\"}[5m]) * 100",
                                    "unit": "%",
                                    "confidence_score": 90.0,
                                    "rationale": "Error patterns clearly identified in logs",
                                    "evidence_capsule_ids": ["capsule-001"]
                                }
                            ]
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 500,
                "completion_tokens": 200,
                "total_tokens": 700
            }
        }

    @pytest.fixture
    def valid_slo_response(self) -> Dict[str, Any]:
        """Valid LLM response for SLO thresholds"""
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "variants": [
                                {
                                    "variant": "conservative",
                                    "threshold_value": 150.0,
                                    "target_percentage": 99.9,
                                    "time_window": "30d",
                                    "expected_breach_frequency": "~3 per month",
                                    "rationale": "Strictest threshold, lowest breach risk"
                                },
                                {
                                    "variant": "balanced",
                                    "threshold_value": 200.0,
                                    "target_percentage": 99.5,
                                    "time_window": "30d",
                                    "expected_breach_frequency": "~15 per month",
                                    "rationale": "Recommended default based on p99 performance"
                                },
                                {
                                    "variant": "aggressive",
                                    "threshold_value": 300.0,
                                    "target_percentage": 99.0,
                                    "time_window": "30d",
                                    "expected_breach_frequency": "~30 per month",
                                    "rationale": "Allows more variance, higher breach tolerance"
                                }
                            ]
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": 300,
                "completion_tokens": 150,
                "total_tokens": 450
            }
        }

    @pytest.mark.asyncio
    async def test_recommend_slis_returns_structured_response(
        self,
        recommender,
        mock_llm_client,
        valid_sli_response
    ):
        """Test SLI recommendation returns structured response"""
        # Setup mock
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        # Call service
        recommendations = await recommender.recommend_slis(
            service_name="test-service",
            environment="production"
        )

        # Verify structured response
        assert len(recommendations) == 2
        assert all(isinstance(r, SLIRecommendation) for r in recommendations)

        # Verify first recommendation
        sli = recommendations[0]
        assert sli.name == "test-service-latency-p95"
        assert sli.metric_type == "latency"
        assert "histogram_quantile" in sli.promql
        assert sli.unit == "ms"
        assert sli.confidence_score == 85.5
        assert sli.rationale is not None
        assert len(sli.evidence_capsule_ids) > 0

    @pytest.mark.asyncio
    async def test_recommend_slis_calls_llm_with_schema(
        self,
        recommender,
        mock_llm_client,
        mock_prompt_manager,
        valid_sli_response
    ):
        """Test LLM is called with schema enforcement"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        await recommender.recommend_slis(service_name="test-service")

        # Verify LLM client called with schema
        mock_llm_client.chat_completion.assert_called_once()
        call_args = mock_llm_client.chat_completion.call_args

        assert "messages" in call_args.kwargs
        assert "response_schema" in call_args.kwargs
        assert call_args.kwargs["response_schema"] is not None

    @pytest.mark.asyncio
    async def test_recommend_slis_validates_response_schema(
        self,
        recommender,
        mock_llm_client,
        valid_sli_response
    ):
        """Test response validation detects hallucinations/invalid schemas"""
        # Setup valid response
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        # Should succeed with valid response
        recommendations = await recommender.recommend_slis(service_name="test-service")
        assert len(recommendations) > 0

    @pytest.mark.asyncio
    async def test_recommend_slis_detects_invalid_response(
        self,
        recommender,
        mock_llm_client
    ):
        """Test hallucination detection via schema validation"""
        # Invalid response: missing required fields
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "slis": [
                                {
                                    "name": "incomplete-sli"
                                    # Missing: metric_type, promql, unit, etc.
                                }
                            ]
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"total_tokens": 100}
        }

        mock_llm_client.chat_completion.return_value = invalid_response
        mock_llm_client.extract_json.return_value = json.loads(
            invalid_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = invalid_response["usage"]

        # Should raise validation error
        with pytest.raises(LLMValidationError):
            await recommender.recommend_slis(service_name="test-service")

    @pytest.mark.asyncio
    async def test_recommend_slis_with_rag_context(
        self,
        recommender,
        mock_rag_builder,
        mock_embedding_service,
        mock_llm_client,
        valid_sli_response
    ):
        """Test RAG context is used in recommendations"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        await recommender.recommend_slis(
            service_name="test-service",
            top_k_capsules=10,
            time_range_days=30
        )

        # Verify embedding generated
        mock_embedding_service.embed_text.assert_called_once()

        # Verify RAG builder called with correct params
        mock_rag_builder.build_context.assert_called_once()
        call_args = mock_rag_builder.build_context.call_args

        assert call_args.kwargs['service_name'] == "test-service"
        assert call_args.kwargs['top_k'] == 10
        assert call_args.kwargs['time_range_days'] == 30

    @pytest.mark.asyncio
    async def test_recommend_slis_includes_evidence_pointers(
        self,
        recommender,
        mock_llm_client,
        valid_sli_response
    ):
        """Test recommendations include evidence pointers from RAG"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        recommendations = await recommender.recommend_slis(service_name="test-service")

        # All recommendations should have evidence
        for rec in recommendations:
            assert len(rec.evidence_capsule_ids) > 0
            # Should reference actual capsule IDs from RAG context
            assert all(
                cid.startswith('capsule-')
                for cid in rec.evidence_capsule_ids
            )

    @pytest.mark.asyncio
    async def test_recommend_slo_thresholds_returns_three_variants(
        self,
        recommender,
        mock_llm_client,
        valid_slo_response
    ):
        """Test SLO threshold recommendation returns 3 variants per spec.md FR-004"""
        mock_llm_client.chat_completion.return_value = valid_slo_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_slo_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_slo_response["usage"]

        variants = await recommender.recommend_slo_thresholds(
            sli_name="test-latency-p95",
            sli_type="latency",
            historical_percentiles={
                "p50": 100.0,
                "p95": 200.0,
                "p99": 300.0,
                "p99.9": 400.0
            },
            current_value=180.0
        )

        # Should return 3 variants
        assert len(variants) == 3
        assert all(isinstance(v, SLOVariant) for v in variants)

        # Verify variant types
        variant_names = {v.variant for v in variants}
        assert variant_names == {"conservative", "balanced", "aggressive"}

    @pytest.mark.asyncio
    async def test_slo_variants_have_correct_ordering(
        self,
        recommender,
        mock_llm_client,
        valid_slo_response
    ):
        """Test SLO variants are ordered from strictest to most lenient"""
        mock_llm_client.chat_completion.return_value = valid_slo_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_slo_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_slo_response["usage"]

        variants = await recommender.recommend_slo_thresholds(
            sli_name="test-latency-p95",
            sli_type="latency",
            historical_percentiles={"p99": 200.0},
            current_value=180.0
        )

        conservative = next(v for v in variants if v.variant == "conservative")
        balanced = next(v for v in variants if v.variant == "balanced")
        aggressive = next(v for v in variants if v.variant == "aggressive")

        # Conservative should be strictest (lowest threshold for latency)
        assert conservative.threshold_value < balanced.threshold_value
        assert balanced.threshold_value < aggressive.threshold_value

        # Target percentages should be ordered (higher is stricter)
        assert conservative.target_percentage > balanced.target_percentage
        assert balanced.target_percentage > aggressive.target_percentage

    @pytest.mark.asyncio
    async def test_recommend_instrumentation_returns_actionable_advice(
        self,
        recommender,
        mock_llm_client
    ):
        """Test instrumentation recommendations are actionable"""
        instrumentation_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "recommendations": [
                                {
                                    "type": "enable_rum",
                                    "description": "Enable Real User Monitoring for frontend tracking",
                                    "code_snippet": "import { initRUM } from '@slo-scout/rum';\ninitRUM({ serviceName: 'test-service' });",
                                    "expected_confidence_uplift": 25.0,
                                    "priority": "critical",
                                    "effort": "low"
                                },
                                {
                                    "type": "add_request_id",
                                    "description": "Add request_id to all log entries",
                                    "code_snippet": "logger.info('message', { request_id: req.id });",
                                    "expected_confidence_uplift": 15.0,
                                    "priority": "important",
                                    "effort": "medium"
                                }
                            ]
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"total_tokens": 200}
        }

        mock_llm_client.chat_completion.return_value = instrumentation_response
        mock_llm_client.extract_json.return_value = json.loads(
            instrumentation_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = instrumentation_response["usage"]

        recommendations = await recommender.recommend_instrumentation(
            service_name="test-service",
            data_quality={
                "rum_coverage": 10.0,
                "trace_coverage": 40.0,
                "structured_log_pct": 60.0
            },
            current_confidence=55.0
        )

        assert len(recommendations) == 2
        assert all(isinstance(r, InstrumentationRecommendation) for r in recommendations)

        # Verify fields
        rec = recommendations[0]
        assert rec.type == "enable_rum"
        assert rec.description is not None
        assert rec.code_snippet is not None
        assert rec.expected_confidence_uplift > 0.0
        assert rec.priority in ["critical", "important", "nice_to_have"]
        assert rec.effort in ["low", "medium", "high"]

    @pytest.mark.asyncio
    async def test_llm_api_error_handling(
        self,
        recommender,
        mock_llm_client
    ):
        """Test error handling for LLM API failures"""
        mock_llm_client.chat_completion.side_effect = LLMError("API timeout")

        with pytest.raises(LLMError, match="API timeout"):
            await recommender.recommend_slis(service_name="test-service")

    @pytest.mark.asyncio
    async def test_llm_rate_limit_error_propagated(
        self,
        recommender,
        mock_llm_client
    ):
        """Test rate limit errors are propagated"""
        mock_llm_client.chat_completion.side_effect = LLMRateLimitError(
            "Rate limit exceeded, retry after 60s"
        )

        with pytest.raises(LLMRateLimitError):
            await recommender.recommend_slis(service_name="test-service")

    @pytest.mark.asyncio
    async def test_invalid_json_response_raises_validation_error(
        self,
        recommender,
        mock_llm_client
    ):
        """Test invalid JSON response is caught"""
        invalid_response = {
            "choices": [
                {
                    "message": {
                        "content": "This is not JSON"
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"total_tokens": 50}
        }

        mock_llm_client.chat_completion.return_value = invalid_response
        mock_llm_client.extract_json.side_effect = LLMValidationError("Invalid JSON in response")

        with pytest.raises(LLMValidationError):
            await recommender.recommend_slis(service_name="test-service")

    @pytest.mark.asyncio
    async def test_response_missing_required_field_fails_validation(
        self,
        recommender,
        mock_llm_client
    ):
        """Test schema validation catches missing required fields"""
        incomplete_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            # Missing "slis" field
                            "other_field": "value"
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"total_tokens": 50}
        }

        mock_llm_client.chat_completion.return_value = incomplete_response
        mock_llm_client.extract_json.return_value = json.loads(
            incomplete_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = incomplete_response["usage"]

        with pytest.raises(LLMValidationError):
            await recommender.recommend_slis(service_name="test-service")

    @pytest.mark.asyncio
    async def test_llm_usage_metrics_logged(
        self,
        recommender,
        mock_llm_client,
        valid_sli_response
    ):
        """Test LLM token usage metrics are extracted"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        await recommender.recommend_slis(service_name="test-service")

        # Verify usage extracted
        mock_llm_client.get_usage.assert_called_once_with(valid_sli_response)

    @pytest.mark.asyncio
    async def test_prompt_building_with_data_quality(
        self,
        recommender,
        mock_prompt_manager,
        mock_llm_client,
        valid_sli_response
    ):
        """Test prompts include data quality metrics"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        data_quality = {
            "rum_coverage": 75.0,
            "trace_coverage": 80.0,
            "structured_log_pct": 90.0
        }

        await recommender.recommend_slis(
            service_name="test-service",
            data_quality=data_quality
        )

        # Verify prompt builder called with data quality
        mock_prompt_manager.build_sli_recommendation_prompt.assert_called_once()
        call_kwargs = mock_prompt_manager.build_sli_recommendation_prompt.call_args.kwargs
        assert call_kwargs['data_quality'] == data_quality

    @pytest.mark.asyncio
    async def test_evidence_pointers_merged_from_rag(
        self,
        recommender,
        mock_llm_client,
        mock_rag_builder
    ):
        """Test evidence pointers from RAG are merged into recommendations"""
        # Response without evidence
        response_no_evidence = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "slis": [
                                {
                                    "name": "test-sli",
                                    "metric_type": "latency",
                                    "promql": "query",
                                    "unit": "ms",
                                    "confidence_score": 80.0,
                                    "rationale": "test",
                                    "evidence_capsule_ids": []  # Empty
                                }
                            ]
                        })
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {"total_tokens": 100}
        }

        mock_llm_client.chat_completion.return_value = response_no_evidence
        mock_llm_client.extract_json.return_value = json.loads(
            response_no_evidence["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = response_no_evidence["usage"]

        recommendations = await recommender.recommend_slis(service_name="test-service")

        # Should use evidence from RAG context
        assert len(recommendations[0].evidence_capsule_ids) > 0
        assert recommendations[0].evidence_capsule_ids[0] == 'capsule-001'

    @pytest.mark.asyncio
    async def test_confidence_scores_within_valid_range(
        self,
        recommender,
        mock_llm_client,
        valid_sli_response
    ):
        """Test confidence scores are in valid range 0-100"""
        mock_llm_client.chat_completion.return_value = valid_sli_response
        mock_llm_client.extract_json.return_value = json.loads(
            valid_sli_response["choices"][0]["message"]["content"]
        )
        mock_llm_client.get_usage.return_value = valid_sli_response["usage"]

        recommendations = await recommender.recommend_slis(service_name="test-service")

        for rec in recommendations:
            assert 0.0 <= rec.confidence_score <= 100.0


class TestLLMClient:
    """Test LLM client functionality"""

    @pytest.mark.asyncio
    async def test_chat_completion_with_retry(self):
        """Test chat completion with retry logic"""
        config = LLMConfig(
            provider=LLMProvider.LOCAL,
            base_url="http://localhost:8000/v1",
            model="test-model",
            max_retries=3
        )

        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "test"}, "finish_reason": "stop"}],
                "usage": {"total_tokens": 100}
            }
            mock_client.post.return_value = mock_response

            client = LLMClient(config)
            response = await client.chat_completion(
                messages=[{"role": "user", "content": "test"}]
            )

            assert response is not None
            assert "choices" in response

    def test_llm_config_defaults(self):
        """Test LLM config has sensible defaults"""
        config = LLMConfig(provider=LLMProvider.OPENAI)

        assert config.base_url == "https://api.openai.com/v1"
        assert config.model == "gpt-4"
        assert config.max_tokens == 2000
        assert config.temperature == 0.3
        assert config.timeout_seconds == 60
        assert config.max_retries == 3


class TestSLIRecommendation:
    """Test SLI recommendation data class"""

    def test_sli_recommendation_creation(self):
        """Test SLIRecommendation data class"""
        rec = SLIRecommendation(
            name="test-latency-p95",
            metric_type="latency",
            promql="histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))",
            unit="ms",
            confidence_score=85.5,
            rationale="Based on high traffic volume",
            evidence_capsule_ids=["capsule-001", "capsule-002"]
        )

        assert rec.name == "test-latency-p95"
        assert rec.metric_type == "latency"
        assert "histogram_quantile" in rec.promql
        assert rec.unit == "ms"
        assert rec.confidence_score == 85.5
        assert len(rec.evidence_capsule_ids) == 2


class TestSLOVariant:
    """Test SLO variant data class"""

    def test_slo_variant_creation(self):
        """Test SLOVariant data class"""
        variant = SLOVariant(
            variant="conservative",
            threshold_value=150.0,
            target_percentage=99.9,
            time_window="30d",
            expected_breach_frequency="~3 per month",
            rationale="Strictest threshold"
        )

        assert variant.variant == "conservative"
        assert variant.threshold_value == 150.0
        assert variant.target_percentage == 99.9
        assert variant.time_window == "30d"


class TestInstrumentationRecommendation:
    """Test instrumentation recommendation data class"""

    def test_instrumentation_recommendation_creation(self):
        """Test InstrumentationRecommendation data class"""
        rec = InstrumentationRecommendation(
            type="enable_rum",
            description="Enable RUM tracking",
            code_snippet="initRUM({...})",
            expected_confidence_uplift=25.0,
            priority="critical",
            effort="low"
        )

        assert rec.type == "enable_rum"
        assert rec.description == "Enable RUM tracking"
        assert rec.code_snippet == "initRUM({...})"
        assert rec.expected_confidence_uplift == 25.0
        assert rec.priority == "critical"
        assert rec.effort == "low"
