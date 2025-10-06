"""
Pydantic schemas for API request/response validation
Per API contracts in contracts/ directory
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum


# Enums per API contracts

class Environment(str, Enum):
    PROD = "prod"
    STAGING = "staging"
    DEV = "dev"


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MetricType(str, Enum):
    LATENCY = "latency"
    AVAILABILITY = "availability"
    ERROR_RATE = "error_rate"
    CUSTOM = "custom"


class ComparisonOperator(str, Enum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"


class Severity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class SLOVariant(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


class ArtifactType(str, Enum):
    PROMETHEUS_RECORDING = "prometheus_recording"
    PROMETHEUS_ALERT = "prometheus_alert"
    GRAFANA_DASHBOARD = "grafana_dashboard"
    RUNBOOK = "runbook"


class ValidationStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    DEPLOYED = "deployed"
    ROLLBACK = "rollback"


class ArtifactAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DEPLOY = "deploy"
    ROLLBACK = "rollback"


# Analysis API schemas

class AnalyzeRequest(BaseModel):
    service_name: str = Field(..., description="Name of the service to analyze")
    environment: Environment
    analysis_window_days: int = Field(default=30, ge=1, le=90, description="Historical data window for analysis")
    force_refresh: bool = Field(default=False, description="Bypass cache and reanalyze")


class AnalyzeResponse(BaseModel):
    job_id: UUID
    status: str = Field(..., pattern="^(pending|running)$")
    estimated_duration_seconds: int


class AnalysisStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    progress_percent: int = Field(..., ge=0, le=100)
    started_at: datetime
    completed_at: Optional[datetime] = None
    result_url: Optional[str] = None
    error_message: Optional[str] = None


# Journey API schemas

class UserJourneyResponse(BaseModel):
    journey_id: UUID
    name: str
    entry_point: str
    exit_point: str
    traffic_volume_per_day: int
    confidence_score: float = Field(..., ge=0, le=100)
    discovered_at: datetime


class JourneysListResponse(BaseModel):
    journeys: List[UserJourneyResponse]
    total_count: int


# SLI API schemas

class EvidencePointer(BaseModel):
    capsule_id: Optional[UUID] = None
    trace_id: Optional[str] = None
    timestamp: datetime
    confidence_contribution: float


class SLIResponse(BaseModel):
    sli_id: UUID
    journey_id: UUID
    name: str
    metric_type: MetricType
    metric_definition: str
    confidence_score: float = Field(..., ge=0, le=100)
    current_value: Optional[float] = None
    unit: str
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class SLIDetailResponse(SLIResponse):
    evidence_pointers: List[EvidencePointer] = []


class SLIListResponse(BaseModel):
    slis: List[SLIResponse]


class SLIUpdateRequest(BaseModel):
    approved: Optional[bool] = None
    metric_definition_override: Optional[str] = None


# SLO API schemas

class SLOCreateRequest(BaseModel):
    sli_id: UUID
    threshold_value: float
    comparison_operator: ComparisonOperator
    time_window: str = Field(..., description="Time window (e.g., '30d', '1h')")
    target_percentage: float = Field(..., ge=0, le=100)
    severity: Optional[Severity] = None
    variant: Optional[SLOVariant] = None


class SLOResponse(BaseModel):
    slo_id: UUID
    sli_id: UUID
    threshold_value: float
    comparison_operator: ComparisonOperator
    time_window: str
    target_percentage: float
    severity: Optional[Severity] = None
    variant: Optional[SLOVariant] = None
    historical_breach_frequency: Optional[float] = None
    error_budget_remaining: Optional[float] = None
    deployed_at: Optional[datetime] = None


class SimulationRequest(BaseModel):
    threshold_override: Optional[float] = None
    simulation_window_days: int = Field(default=30, ge=1, le=365)


class SimulationResultResponse(BaseModel):
    slo_id: UUID
    simulated_breaches: int
    breach_timestamps: List[datetime]
    average_error_budget_remaining: float
    worst_breach_magnitude: float


# Artifact API schemas

class ArtifactGenerateRequest(BaseModel):
    slo_id: UUID
    artifact_types: List[ArtifactType]
    validate_only: bool = Field(default=False, description="Validate without saving")


class ValidationError(BaseModel):
    line: Optional[int] = None
    message: str


class ArtifactResponse(BaseModel):
    artifact_id: UUID
    slo_id: UUID
    artifact_type: ArtifactType
    validation_status: ValidationStatus
    approval_status: ApprovalStatus
    deployment_status: DeploymentStatus
    version: int
    created_at: datetime
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    deployment_pr_url: Optional[str] = None


class ArtifactDetailResponse(ArtifactResponse):
    content: str
    validation_errors: Optional[List[ValidationError]] = None


class ArtifactGenerateResponse(BaseModel):
    artifacts: List[ArtifactResponse]


class ArtifactUpdateRequest(BaseModel):
    action: ArtifactAction
    approver_comment: Optional[str] = None


class PolicyViolationResponse(BaseModel):
    error_code: str
    message: str
    policy_name: str
    violated_invariants: Dict[str, Any]
    suggested_actions: List[str]


class ValidationErrorResponse(BaseModel):
    error_code: str
    message: str
    validation_output: Optional[str] = None
    failed_artifacts: Optional[List[Dict[str, Any]]] = None


# PR API schemas

class PRCreateRequest(BaseModel):
    artifact_ids: List[UUID] = Field(..., description="List of approved artifact IDs to include")
    repository: str = Field(..., description="Repository in 'org/repo' format")
    branch_name: Optional[str] = Field(None, description="Auto-generated if not provided")
    pr_title: Optional[str] = None
    pr_body: Optional[str] = None


class PRCreateResponse(BaseModel):
    pr_url: str
    pr_number: int
    branch_name: str
    artifacts_included: List[UUID]


# Service API schemas

class ServiceCreate(BaseModel):
    name: str
    environment: str
    owner_team: str
    telemetry_endpoints: Dict[str, str] = Field(default_factory=dict)


class Service(BaseModel):
    id: str
    name: str
    environment: str
    owner_team: str
    telemetry_endpoints: Dict[str, str]
    created_at: str
    updated_at: str
    status: str


# Error schemas

class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
