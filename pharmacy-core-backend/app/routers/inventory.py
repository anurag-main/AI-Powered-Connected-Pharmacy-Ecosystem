"""HTTP layer for the Inventory Risk Agent."""

from fastapi import APIRouter, Depends, status

from app.ai.schemas.inventory_query import InventoryRiskQuery
from app.schemas.inventory import (
    InventoryAnalysisRequest,
    InventoryAnalysisResponse,
    InventoryExplanationResponse,
    InventoryReportResponse,
)
from app.services.inventory_agent_service import InventoryAgentService

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory Risk"])


def get_inventory_agent_service() -> InventoryAgentService:
    """Dependency provider, so a test can swap the service out."""

    return InventoryAgentService()


@router.post(
    "/analyze",
    response_model=InventoryAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask which inventory is absorbing capital, and what to review",
)
def analyze_inventory_risk(
    request: InventoryAnalysisRequest,
    service: InventoryAgentService = Depends(get_inventory_agent_service),
) -> InventoryAnalysisResponse:
    """Answer a natural-language question about inventory and capital.

    Read-only. The agent recommends what to review; it never takes an action.
    """

    return service.analyze(request)


# ---------------------------------------------------------------------------
# Dashboard endpoints
#
# The chat endpoint above takes a question. A dashboard has filters, which ARE the
# query - so these two take InventoryRiskQuery directly as the body. Using the same
# model the tool uses means the HTTP contract and the agent's contract cannot drift
# apart, and every bound on it is enforced here too.
# ---------------------------------------------------------------------------


@router.post(
    "/report",
    response_model=InventoryReportResponse,
    status_code=status.HTTP_200_OK,
    summary="Deterministic inventory risk report - no LLM, no cost",
)
def inventory_report(
    query: InventoryRiskQuery,
    service: InventoryAgentService = Depends(get_inventory_agent_service),
) -> InventoryReportResponse:
    """Every figure a dashboard needs, computed in Python from stock and sales.

    Read-only, and no model is called, so this is fast and free to poll. It is also
    the proof that the business calculation does not depend on the LLM: pull the API
    key and this endpoint is unaffected.
    """

    return service.report(query)


@router.post(
    "/explain",
    response_model=InventoryExplanationResponse,
    status_code=status.HTTP_200_OK,
    summary="Plain-language explanation of the report for the same query",
)
def explain_inventory_report(
    query: InventoryRiskQuery,
    service: InventoryAgentService = Depends(get_inventory_agent_service),
) -> InventoryExplanationResponse:
    """Prose for the report /report just returned.

    Send the identical query. The planner is skipped, so the explanation describes
    exactly the rows on screen rather than a target cover the model chose for itself.
    """

    return service.explain(query)
