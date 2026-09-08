"""HTTP layer for the Expiry Risk Agent."""

from fastapi import APIRouter, Depends, status

from app.schemas.expiry import ExpiryAnalysisRequest, ExpiryAnalysisResponse
from app.services.expiry_agent_service import ExpiryAgentService

router = APIRouter(prefix="/api/v1/expiry", tags=["Expiry Risk"])


def get_expiry_agent_service() -> ExpiryAgentService:
    """Dependency provider, so a test can swap the service out."""

    return ExpiryAgentService()


@router.post(
    "/analyze",
    response_model=ExpiryAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Assess which stock is at risk of expiring, and what to do about it",
)
def analyze_expiry_risk(
    request: ExpiryAnalysisRequest,
    service: ExpiryAgentService = Depends(get_expiry_agent_service),
) -> ExpiryAnalysisResponse:
    """Answer a natural-language question about expiry risk.

    Read-only. The agent recommends actions; it never takes them.
    """

    return service.analyze(request)
