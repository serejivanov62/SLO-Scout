"""
Unit tests for prompt template manager (T094)
Tests few-shot prompt templates and JSON schema enforcement
"""
import pytest

from src.services.prompts import (
    PromptTemplateManager,
    PromptTask,
    PromptExample
)


@pytest.fixture
def prompt_manager():
    """Create prompt template manager"""
    return PromptTemplateManager()


class TestPromptTemplateManager:
    """Test prompt template manager functionality"""

    def test_initialization(self, prompt_manager):
        """Test manager initializes with all components"""
        assert len(prompt_manager.system_prompts) > 0
        assert len(prompt_manager.schemas) > 0
        assert len(prompt_manager.examples) > 0

    def test_system_prompt_for_sli_recommendation(self, prompt_manager):
        """Test SLI recommendation system prompt exists"""
        system_prompt = prompt_manager.system_prompts[PromptTask.SLI_RECOMMENDATION.value]
        assert "SRE expert" in system_prompt
        assert "Service Level Indicators" in system_prompt
        assert "JSON" in system_prompt

    def test_system_prompt_for_slo_threshold(self, prompt_manager):
        """Test SLO threshold system prompt exists"""
        system_prompt = prompt_manager.system_prompts[PromptTask.SLO_THRESHOLD.value]
        assert "Service Level Objectives" in system_prompt
        assert "conservative" in system_prompt.lower()
        assert "balanced" in system_prompt.lower()
        assert "aggressive" in system_prompt.lower()

    def test_sli_recommendation_schema(self, prompt_manager):
        """Test SLI recommendation JSON schema"""
        schema = prompt_manager.schemas[PromptTask.SLI_RECOMMENDATION.value]

        # Verify top-level structure
        assert schema['type'] == 'object'
        assert 'slis' in schema['properties']

        # Verify SLI array structure
        sli_items = schema['properties']['slis']['items']
        assert 'name' in sli_items['properties']
        assert 'metric_type' in sli_items['properties']
        assert 'promql' in sli_items['properties']
        assert 'confidence_score' in sli_items['properties']

        # Verify metric type enum
        metric_type_enum = sli_items['properties']['metric_type']['enum']
        assert 'latency' in metric_type_enum
        assert 'availability' in metric_type_enum
        assert 'error_rate' in metric_type_enum

        # Verify array bounds (3-5 SLIs per FR-002)
        assert schema['properties']['slis']['minItems'] == 3
        assert schema['properties']['slis']['maxItems'] == 5

    def test_slo_threshold_schema(self, prompt_manager):
        """Test SLO threshold JSON schema"""
        schema = prompt_manager.schemas[PromptTask.SLO_THRESHOLD.value]

        # Verify top-level structure
        assert schema['type'] == 'object'
        assert 'variants' in schema['properties']

        # Verify variant array structure
        variant_items = schema['properties']['variants']['items']
        assert 'variant' in variant_items['properties']
        assert 'threshold_value' in variant_items['properties']
        assert 'target_percentage' in variant_items['properties']

        # Verify variant enum (3 variants per FR-004)
        variant_enum = variant_items['properties']['variant']['enum']
        assert 'conservative' in variant_enum
        assert 'balanced' in variant_enum
        assert 'aggressive' in variant_enum

        # Verify exactly 3 variants
        assert schema['properties']['variants']['minItems'] == 3
        assert schema['properties']['variants']['maxItems'] == 3

    def test_instrumentation_advice_schema(self, prompt_manager):
        """Test instrumentation advice JSON schema"""
        schema = prompt_manager.schemas[PromptTask.INSTRUMENTATION_ADVICE.value]

        # Verify top-level structure
        assert schema['type'] == 'object'
        assert 'recommendations' in schema['properties']

        # Verify recommendation structure
        rec_items = schema['properties']['recommendations']['items']
        assert 'type' in rec_items['properties']
        assert 'description' in rec_items['properties']
        assert 'expected_confidence_uplift' in rec_items['properties']
        assert 'priority' in rec_items['properties']
        assert 'effort' in rec_items['properties']

        # Verify recommendation type enum
        type_enum = rec_items['properties']['type']['enum']
        assert 'enable_rum' in type_enum
        assert 'add_tracing' in type_enum
        assert 'add_structured_logs' in type_enum

    def test_sli_recommendation_examples(self, prompt_manager):
        """Test SLI recommendation examples are present"""
        examples = prompt_manager.examples[PromptTask.SLI_RECOMMENDATION.value]
        assert len(examples) > 0

        # Verify example structure
        example = examples[0]
        assert isinstance(example, PromptExample)
        assert 'service_name' in example.input
        assert 'total_events' in example.input
        assert 'slis' in example.output

        # Verify example SLIs follow schema
        for sli in example.output['slis']:
            assert 'name' in sli
            assert 'metric_type' in sli
            assert 'promql' in sli
            assert 'confidence_score' in sli

    def test_slo_threshold_examples(self, prompt_manager):
        """Test SLO threshold examples are present"""
        examples = prompt_manager.examples[PromptTask.SLO_THRESHOLD.value]
        assert len(examples) > 0

        # Verify example structure
        example = examples[0]
        assert 'sli_name' in example.input
        assert 'historical_values' in example.input
        assert 'variants' in example.output

        # Verify 3 variants
        assert len(example.output['variants']) == 3
        variants = {v['variant'] for v in example.output['variants']}
        assert variants == {'conservative', 'balanced', 'aggressive'}

    def test_build_sli_recommendation_prompt(self, prompt_manager):
        """Test SLI recommendation prompt building"""
        service_name = "payment-api"
        capsules = [
            {"template": "Payment succeeded", "count": 1000},
            {"template": "Payment failed", "count": 100}
        ]
        aggregated_metrics = {
            "total_events": 1100,
            "unique_templates": 2,
            "top_templates": [
                {"template": "Payment succeeded", "count": 1000},
                {"template": "Payment failed", "count": 100}
            ]
        }

        messages = prompt_manager.build_sli_recommendation_prompt(
            service_name=service_name,
            capsules=capsules,
            aggregated_metrics=aggregated_metrics
        )

        # Verify message structure
        assert len(messages) > 0
        assert messages[0]['role'] == 'system'
        assert 'SRE expert' in messages[0]['content']

        # Verify few-shot examples are included
        user_messages = [m for m in messages if m['role'] == 'user']
        assistant_messages = [m for m in messages if m['role'] == 'assistant']
        assert len(user_messages) >= 2  # At least 1 example + 1 actual query
        assert len(assistant_messages) >= 1  # At least 1 example response

        # Verify actual query includes service name
        last_user_message = user_messages[-1]['content']
        assert service_name in last_user_message
        assert 'Payment succeeded' in last_user_message

    def test_build_sli_recommendation_prompt_with_data_quality(self, prompt_manager):
        """Test SLI prompt with data quality metrics"""
        data_quality = {
            'rum_coverage': 75.0,
            'trace_coverage': 85.0,
            'structured_log_percentage': 90.0,
            'request_id_presence': 95.0
        }

        messages = prompt_manager.build_sli_recommendation_prompt(
            service_name="test-service",
            capsules=[],
            aggregated_metrics={
                'total_events': 1000,
                'unique_templates': 10,
                'top_templates': []
            },
            data_quality=data_quality
        )

        # Verify data quality is mentioned in prompt
        last_message = messages[-1]['content']
        assert '75.0%' in last_message  # RUM coverage
        assert 'Data quality metrics' in last_message

    def test_build_slo_threshold_prompt(self, prompt_manager):
        """Test SLO threshold prompt building"""
        historical_percentiles = {
            'p50': 99.5,
            'p95': 99.2,
            'p99': 99.0,
            'p999': 98.5
        }

        messages = prompt_manager.build_slo_threshold_prompt(
            sli_name="payment-success-rate",
            sli_type="availability",
            historical_percentiles=historical_percentiles,
            current_value=99.3
        )

        # Verify message structure
        assert len(messages) > 0
        assert messages[0]['role'] == 'system'

        # Verify content includes percentiles
        last_message = messages[-1]['content']
        assert 'payment-success-rate' in last_message
        assert '99.5' in last_message  # p50
        assert '99.3' in last_message  # current value

    def test_build_instrumentation_advice_prompt(self, prompt_manager):
        """Test instrumentation advice prompt building"""
        data_quality = {
            'rum_coverage': 25.0,
            'trace_coverage': 50.0,
            'structured_log_percentage': 60.0,
            'request_id_presence': 40.0
        }

        messages = prompt_manager.build_instrumentation_advice_prompt(
            service_name="underinstrumented-service",
            data_quality=data_quality,
            current_confidence=45.0,
            technology_stack=['Python', 'FastAPI', 'PostgreSQL']
        )

        # Verify message structure
        assert len(messages) > 0
        assert messages[0]['role'] == 'system'

        # Verify content includes data quality and tech stack
        last_message = messages[-1]['content']
        assert 'underinstrumented-service' in last_message
        assert '25.0%' in last_message  # RUM coverage
        assert '45.0%' in last_message  # Current confidence
        assert 'Python' in last_message

    def test_get_schema(self, prompt_manager):
        """Test schema retrieval"""
        schema = prompt_manager.get_schema(PromptTask.SLI_RECOMMENDATION)
        assert schema['type'] == 'object'
        assert 'slis' in schema['properties']

    def test_format_templates(self, prompt_manager):
        """Test template formatting for prompts"""
        templates = [
            {"template": "Template 1", "count": 100},
            {"template": "Template 2", "count": 50},
            {"template": "Template 3", "count": 25}
        ]

        formatted = prompt_manager._format_templates(templates)

        assert "Template 1" in formatted
        assert "count: 100" in formatted
        assert "1." in formatted  # Numbered list

    def test_format_templates_empty(self, prompt_manager):
        """Test template formatting with empty list"""
        formatted = prompt_manager._format_templates([])
        assert "No templates available" in formatted

    def test_format_percentiles(self, prompt_manager):
        """Test percentile formatting for prompts"""
        percentiles = {
            'p50': 99.5,
            'p95': 99.2,
            'p99': 99.0
        }

        formatted = prompt_manager._format_percentiles(percentiles)

        assert '99.5' in formatted
        assert '99.2' in formatted
        assert '99.0' in formatted
        assert 'p' in formatted  # Percentile labels

    def test_schema_validation_ready(self, prompt_manager):
        """Test that schemas are ready for JSON schema validation"""
        for task_value, schema in prompt_manager.schemas.items():
            # Verify required fields
            assert 'type' in schema
            assert schema['type'] == 'object'
            assert 'properties' in schema
            assert 'required' in schema

            # Verify strict mode compatibility
            assert schema.get('additionalProperties') == False


class TestPromptExample:
    """Test PromptExample dataclass"""

    def test_create_example(self):
        """Test creating prompt example"""
        example = PromptExample(
            input={"test": "input"},
            output={"test": "output"},
            explanation="Test explanation"
        )

        assert example.input == {"test": "input"}
        assert example.output == {"test": "output"}
        assert example.explanation == "Test explanation"

    def test_create_example_without_explanation(self):
        """Test creating example without explanation"""
        example = PromptExample(
            input={"test": "input"},
            output={"test": "output"}
        )

        assert example.explanation is None
