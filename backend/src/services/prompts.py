"""
Prompt template manager per T094
Few-shot prompts for SLI recommendation
Structured JSON schema enforcement
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class PromptTask(Enum):
    """Task types for LLM prompts"""
    SLI_RECOMMENDATION = "sli_recommendation"
    SLO_THRESHOLD = "slo_threshold"
    INSTRUMENTATION_ADVICE = "instrumentation_advice"
    RUNBOOK_GENERATION = "runbook_generation"


@dataclass
class PromptExample:
    """
    Few-shot example for prompt

    Attributes:
        input: Example input context
        output: Expected output
        explanation: Why this is the correct output (optional)
    """
    input: Dict[str, Any]
    output: Dict[str, Any]
    explanation: Optional[str] = None


class PromptTemplateManager:
    """
    Manages prompt templates for LLM interactions

    Per spec.md FR-002: Generates top 5 SLI recommendations per journey
    Per spec.md FR-004: Recommends 3 SLO threshold variants

    Implements few-shot learning with structured JSON schema enforcement
    to reduce hallucinations and ensure consistent output format.
    """

    def __init__(self):
        """Initialize prompt template manager"""
        self.system_prompts = self._load_system_prompts()
        self.schemas = self._load_schemas()
        self.examples = self._load_examples()

    def _load_system_prompts(self) -> Dict[str, str]:
        """Load system prompts for each task type"""
        return {
            PromptTask.SLI_RECOMMENDATION.value: """You are an SRE expert specializing in Service Level Indicators (SLIs).
Your task is to analyze telemetry data and recommend meaningful SLIs that reflect user experience.

Key principles:
- Focus on user-facing metrics (latency, availability, error rate)
- Base recommendations on actual observed patterns in the data
- Provide PromQL queries that are syntactically valid
- Assign confidence scores based on data coverage and sample size
- Avoid generic recommendations that don't match the service's actual behavior

Output MUST be valid JSON matching the provided schema.""",

            PromptTask.SLO_THRESHOLD.value: """You are an SRE expert specializing in Service Level Objectives (SLOs).
Your task is to recommend realistic SLO thresholds based on historical performance.

Key principles:
- Conservative: p99.9 of historical values (strictest, 99.9% target)
- Balanced: p99 of historical values (recommended, 99% target)
- Aggressive: p95 of historical values (tolerates variance, 95% target)
- Include expected breach frequency based on historical simulation
- Consider business impact and operational feasibility

Output MUST be valid JSON matching the provided schema.""",

            PromptTask.INSTRUMENTATION_ADVICE.value: """You are an observability expert specializing in instrumentation.
Your task is to identify data quality gaps and recommend concrete instrumentation improvements.

Key principles:
- Identify missing telemetry (traces, metrics, logs, RUM)
- Provide actionable code snippets for recommended changes
- Estimate expected confidence uplift from improvements
- Prioritize high-impact, low-effort changes
- Consider the service's technology stack

Output MUST be valid JSON matching the provided schema.""",
        }

    def _load_schemas(self) -> Dict[str, Dict[str, Any]]:
        """Load JSON schemas for structured output"""
        return {
            PromptTask.SLI_RECOMMENDATION.value: {
                "type": "object",
                "properties": {
                    "slis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "SLI name (e.g., checkout-latency-p95)"
                                },
                                "metric_type": {
                                    "type": "string",
                                    "enum": ["latency", "availability", "error_rate", "throughput", "correctness"],
                                    "description": "Type of SLI metric"
                                },
                                "promql": {
                                    "type": "string",
                                    "description": "PromQL query for this SLI"
                                },
                                "unit": {
                                    "type": "string",
                                    "description": "Unit of measurement (ms, %, requests/s, etc.)"
                                },
                                "confidence_score": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 100,
                                    "description": "Confidence in recommendation (0-100)"
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "Why this SLI is important for this service"
                                },
                                "evidence_capsule_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Capsule IDs that support this recommendation"
                                }
                            },
                            "required": ["name", "metric_type", "promql", "unit", "confidence_score", "rationale"],
                            "additionalProperties": False
                        },
                        "minItems": 3,
                        "maxItems": 5
                    }
                },
                "required": ["slis"],
                "additionalProperties": False
            },

            PromptTask.SLO_THRESHOLD.value: {
                "type": "object",
                "properties": {
                    "variants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "variant": {
                                    "type": "string",
                                    "enum": ["conservative", "balanced", "aggressive"]
                                },
                                "threshold_value": {
                                    "type": "number",
                                    "description": "Threshold value for SLO"
                                },
                                "target_percentage": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 100,
                                    "description": "Target percentage (e.g., 99.9 for 99.9% availability)"
                                },
                                "time_window": {
                                    "type": "string",
                                    "description": "Time window (e.g., 30d, 7d, 24h)"
                                },
                                "expected_breach_frequency": {
                                    "type": "string",
                                    "description": "Expected breach frequency (e.g., 'once per month', 'twice per week')"
                                },
                                "rationale": {
                                    "type": "string",
                                    "description": "Why this threshold is appropriate"
                                }
                            },
                            "required": ["variant", "threshold_value", "target_percentage", "time_window", "expected_breach_frequency", "rationale"],
                            "additionalProperties": False
                        },
                        "minItems": 3,
                        "maxItems": 3
                    }
                },
                "required": ["variants"],
                "additionalProperties": False
            },

            PromptTask.INSTRUMENTATION_ADVICE.value: {
                "type": "object",
                "properties": {
                    "recommendations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["enable_rum", "add_tracing", "add_structured_logs", "add_request_id", "increase_sampling", "reduce_cardinality"]
                                },
                                "description": {
                                    "type": "string",
                                    "description": "What to implement"
                                },
                                "code_snippet": {
                                    "type": "string",
                                    "description": "Example code or configuration"
                                },
                                "expected_confidence_uplift": {
                                    "type": "number",
                                    "minimum": 0,
                                    "maximum": 100,
                                    "description": "Expected improvement in confidence score"
                                },
                                "priority": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"]
                                },
                                "effort": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"]
                                }
                            },
                            "required": ["type", "description", "expected_confidence_uplift", "priority", "effort"],
                            "additionalProperties": False
                        }
                    }
                },
                "required": ["recommendations"],
                "additionalProperties": False
            }
        }

    def _load_examples(self) -> Dict[str, List[PromptExample]]:
        """Load few-shot examples for each task"""
        return {
            PromptTask.SLI_RECOMMENDATION.value: [
                PromptExample(
                    input={
                        "service_name": "payment-gateway",
                        "total_events": 15000,
                        "capsule_count": 12,
                        "top_templates": [
                            {"template": "Payment processed successfully for order {ORDER_ID}", "count": 8500},
                            {"template": "Payment failed: insufficient funds for user {USER_ID}", "count": 1200},
                            {"template": "Payment gateway timeout after {DURATION}ms", "count": 300}
                        ]
                    },
                    output={
                        "slis": [
                            {
                                "name": "payment-success-rate",
                                "metric_type": "availability",
                                "promql": "sum(rate(payment_processed_total{service='payment-gateway',status='success'}[5m])) / sum(rate(payment_processed_total{service='payment-gateway'}[5m]))",
                                "unit": "%",
                                "confidence_score": 92,
                                "rationale": "High volume of payment events with clear success/failure patterns",
                                "evidence_capsule_ids": []
                            },
                            {
                                "name": "payment-latency-p95",
                                "metric_type": "latency",
                                "promql": "histogram_quantile(0.95, rate(payment_duration_seconds_bucket{service='payment-gateway'}[5m]))",
                                "unit": "ms",
                                "confidence_score": 85,
                                "rationale": "Timeout errors indicate latency is critical metric",
                                "evidence_capsule_ids": []
                            },
                            {
                                "name": "payment-error-rate",
                                "metric_type": "error_rate",
                                "promql": "sum(rate(payment_processed_total{service='payment-gateway',status='error'}[5m])) / sum(rate(payment_processed_total{service='payment-gateway'}[5m]))",
                                "unit": "%",
                                "confidence_score": 90,
                                "rationale": "Significant error volume warrants dedicated SLI",
                                "evidence_capsule_ids": []
                            }
                        ]
                    }
                )
            ],

            PromptTask.SLO_THRESHOLD.value: [
                PromptExample(
                    input={
                        "sli_name": "payment-success-rate",
                        "historical_values": {
                            "p50": 99.5,
                            "p95": 99.2,
                            "p99": 99.0,
                            "p999": 98.5
                        },
                        "current_value": 99.3
                    },
                    output={
                        "variants": [
                            {
                                "variant": "conservative",
                                "threshold_value": 98.5,
                                "target_percentage": 99.9,
                                "time_window": "30d",
                                "expected_breach_frequency": "once per quarter",
                                "rationale": "Based on p99.9 historical performance, very safe threshold"
                            },
                            {
                                "variant": "balanced",
                                "threshold_value": 99.0,
                                "target_percentage": 99.0,
                                "time_window": "30d",
                                "expected_breach_frequency": "once per month",
                                "rationale": "Based on p99 historical performance, recommended default"
                            },
                            {
                                "variant": "aggressive",
                                "threshold_value": 99.2,
                                "target_percentage": 95.0,
                                "time_window": "30d",
                                "expected_breach_frequency": "once per week",
                                "rationale": "Based on p95 historical performance, tolerates more variance"
                            }
                        ]
                    }
                )
            ]
        }

    def build_sli_recommendation_prompt(
        self,
        service_name: str,
        capsules: List[Dict[str, Any]],
        aggregated_metrics: Dict[str, Any],
        data_quality: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, str]]:
        """
        Build prompt for SLI recommendation task

        Args:
            service_name: Service being analyzed
            capsules: Capsule evidence from RAG
            aggregated_metrics: Aggregated statistics
            data_quality: Data quality metrics (RUM %, trace %, etc.)

        Returns:
            List of message dicts for chat completion
        """
        messages = [
            {
                "role": "system",
                "content": self.system_prompts[PromptTask.SLI_RECOMMENDATION.value]
            }
        ]

        # Add few-shot examples
        for example in self.examples[PromptTask.SLI_RECOMMENDATION.value]:
            messages.append({
                "role": "user",
                "content": f"""Analyze service: {example.input['service_name']}

Total events: {example.input['total_events']}
Capsule patterns: {example.input['capsule_count']}

Top observed patterns:
{self._format_templates(example.input['top_templates'])}

Recommend SLIs based on this data."""
            })

            messages.append({
                "role": "assistant",
                "content": str(example.output)
            })

        # Add actual query
        user_prompt = f"""Analyze service: {service_name}

Total events: {aggregated_metrics.get('total_events', 0)}
Unique patterns: {aggregated_metrics.get('unique_templates', 0)}
Time range: {len(capsules)} capsule snapshots

Top observed patterns:
{self._format_templates(aggregated_metrics.get('top_templates', []))}
"""

        if data_quality:
            user_prompt += f"""
Data quality metrics:
- RUM coverage: {data_quality.get('rum_coverage', 0):.1f}%
- Trace coverage: {data_quality.get('trace_coverage', 0):.1f}%
- Structured logs: {data_quality.get('structured_log_percentage', 0):.1f}%
- Request ID presence: {data_quality.get('request_id_presence', 0):.1f}%
"""

        user_prompt += """
Based on this telemetry data, recommend 3-5 Service Level Indicators that best reflect user experience.
Consider the observed patterns and data quality when assigning confidence scores.
"""

        messages.append({
            "role": "user",
            "content": user_prompt
        })

        return messages

    def build_slo_threshold_prompt(
        self,
        sli_name: str,
        sli_type: str,
        historical_percentiles: Dict[str, float],
        current_value: float,
        service_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """
        Build prompt for SLO threshold recommendation

        Args:
            sli_name: Name of the SLI
            sli_type: Type (latency, availability, etc.)
            historical_percentiles: Historical performance percentiles
            current_value: Current SLI value
            service_context: Additional service context

        Returns:
            List of message dicts for chat completion
        """
        messages = [
            {
                "role": "system",
                "content": self.system_prompts[PromptTask.SLO_THRESHOLD.value]
            }
        ]

        # Add few-shot examples
        for example in self.examples[PromptTask.SLO_THRESHOLD.value]:
            messages.append({
                "role": "user",
                "content": f"""Recommend SLO thresholds for: {example.input['sli_name']}

Historical performance:
- p50: {example.input['historical_values']['p50']}
- p95: {example.input['historical_values']['p95']}
- p99: {example.input['historical_values']['p99']}
- p99.9: {example.input['historical_values']['p999']}

Current value: {example.input['current_value']}

Provide 3 variants: conservative, balanced, aggressive."""
            })

            messages.append({
                "role": "assistant",
                "content": str(example.output)
            })

        # Add actual query
        user_prompt = f"""Recommend SLO thresholds for: {sli_name}
Type: {sli_type}

Historical performance:
{self._format_percentiles(historical_percentiles)}

Current value: {current_value}
"""

        if service_context:
            user_prompt += f"\nService context: {service_context}\n"

        user_prompt += """
Provide 3 threshold variants (conservative, balanced, aggressive) with expected breach frequencies.
Base recommendations on historical p99.9, p99, and p95 values respectively.
"""

        messages.append({
            "role": "user",
            "content": user_prompt
        })

        return messages

    def build_instrumentation_advice_prompt(
        self,
        service_name: str,
        data_quality: Dict[str, float],
        current_confidence: float,
        technology_stack: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """
        Build prompt for instrumentation advice

        Args:
            service_name: Service being analyzed
            data_quality: Current data quality metrics
            current_confidence: Current recommendation confidence score
            technology_stack: Service technologies (Python, Go, etc.)

        Returns:
            List of message dicts for chat completion
        """
        messages = [
            {
                "role": "system",
                "content": self.system_prompts[PromptTask.INSTRUMENTATION_ADVICE.value]
            }
        ]

        user_prompt = f"""Analyze instrumentation gaps for service: {service_name}

Current data quality:
- RUM coverage: {data_quality.get('rum_coverage', 0):.1f}%
- Trace coverage: {data_quality.get('trace_coverage', 0):.1f}%
- Structured logs: {data_quality.get('structured_log_percentage', 0):.1f}%
- Request ID presence: {data_quality.get('request_id_presence', 0):.1f}%

Current SLI confidence score: {current_confidence:.1f}%
"""

        if technology_stack:
            user_prompt += f"\nTechnology stack: {', '.join(technology_stack)}\n"

        user_prompt += """
Recommend concrete instrumentation improvements to increase confidence score.
Prioritize high-impact, low-effort changes. Provide code snippets where applicable.
"""

        messages.append({
            "role": "user",
            "content": user_prompt
        })

        return messages

    def get_schema(self, task: PromptTask) -> Dict[str, Any]:
        """
        Get JSON schema for task

        Args:
            task: Prompt task type

        Returns:
            JSON schema dictionary
        """
        return self.schemas[task.value]

    def _format_templates(self, templates: List[Dict[str, Any]]) -> str:
        """Format template list for prompt"""
        if not templates:
            return "(No templates available)"

        lines = []
        for i, template in enumerate(templates[:5], 1):
            lines.append(f"{i}. {template.get('template', 'N/A')} (count: {template.get('count', 0)})")

        return "\n".join(lines)

    def _format_percentiles(self, percentiles: Dict[str, float]) -> str:
        """Format percentiles for prompt"""
        lines = []
        for key, value in sorted(percentiles.items()):
            lines.append(f"- {key}: {value}")

        return "\n".join(lines)
