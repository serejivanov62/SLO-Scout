"""Minimal SLO-Scout Backend API for deployment demo."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="SLO-Scout API",
    version="1.0.0",
    description="Automated SLI/SLO Discovery Platform"
)


class HealthResponse(BaseModel):
    status: str
    version: str


class AnalyzeRequest(BaseModel):
    service_name: str
    namespace: str = "default"


class AnalyzeResponse(BaseModel):
    job_id: str
    status: str
    message: str


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@app.get("/", response_model=dict)
async def root():
    """Root endpoint."""
    return {
        "service": "SLO-Scout Backend API",
        "version": "1.0.0",
        "status": "running"
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Analyze service for SLI/SLO recommendations (minimal mock)."""
    return AnalyzeResponse(
        job_id=f"job-{request.service_name}-123",
        status="accepted",
        message=f"Analysis started for {request.service_name} in {request.namespace}"
    )


@app.get("/api/v1/analyze/{job_id}", response_model=dict)
async def get_analysis(job_id: str):
    """Get analysis results (minimal mock)."""
    return {
        "job_id": job_id,
        "status": "completed",
        "slis_found": 3,
        "slos_generated": 2
    }
