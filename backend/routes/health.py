"""GET /healthz — trivial liveness probe.

Kept at the top-level ``/healthz`` rather than ``/api/healthz`` so
Kubernetes-style probes, Tailscale uptime monitors, and uvicorn
smoke tests all follow the usual convention.
"""

from fastapi import APIRouter

from ..schemas import HealthResponse

router = APIRouter()


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")
