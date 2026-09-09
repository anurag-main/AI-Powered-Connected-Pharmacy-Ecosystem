"""HTTP layer for the Expiry Risk Agent."""

from fastapi import APIRouter, Depends, status

from app.ai.schemas.expiry_query import ExpiryRiskQuery
from app.schemas.expiry import (
    ExpiryAnalysisRequest,
    ExpiryAnalysisResponse,
    ExpiryExplanationResponse,
    ExpiryReportResponse,
)
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


# ---------------------------------------------------------------------------
# Dashboard endpoints
#
# The chat endpoint above takes a question. A dashboard has filters, which ARE the
# query - so these two take ExpiryRiskQuery directly as the body. Using the same
# model the tool uses means the HTTP contract and the agent's contract cannot drift
# apart, and every bound on it is enforced here too.
# ---------------------------------------------------------------------------


@router.post(
    "/report",
    response_model=ExpiryReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministic expiry risk report — no LLM, no cost",
)
def expiry_report(
    query: ExpiryRiskQuery,
    service: ExpiryAgentService = Depends(get_expiry_agent_service),
) -> ExpiryReportResponse:
    """Every figure a dashboard needs, computed in Python from stock and sales.

    Read-only, and no model is called, so this is fast and free to poll.
    """

    return service.report(query)


@router.post(
    "/explain",
    response_model=ExpiryExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Plain-language explanation of the report for the same query",
)
def explain_expiry_report(
    query: ExpiryRiskQuery,
    service: ExpiryAgentService = Depends(get_expiry_agent_service),
) -> ExpiryExplanationResponse:
    """Prose for the report /report just returned.

    Send the identical query. The planner is skipped, so the explanation describes
    exactly the rows on screen rather than a window the model chose for itself.
    """

    return service.explain(query)
