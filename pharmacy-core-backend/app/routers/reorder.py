"""HTTP layer for the Reorder domain.

GET /api/v1/reorder/suggestions — run the reorder agent, return proposals.

Read-only: it computes suggestions but writes nothing, so the verb is GET and
the status is always 200 (an empty proposals list is a valid answer). The future
"approve & order" action will be a separate POST.
"""
from fastapi import APIRouter, Depends, status

from app.schemas.reorder import ReorderSuggestionsResponse
from app.services.reorder_service import ReorderService


def get_reorder_service() -> ReorderService:
    """Dependency provider. No DB session here — the graph owns its own sessions."""
    return ReorderService()


router = APIRouter(prefix="/api/v1/reorder", tags=["reorder"])


@router.get(
    "/suggestions",
    response_model=ReorderSuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Run the reorder agent and return reorder proposals for owner review",
)
def get_reorder_suggestions(
    service: ReorderService = Depends(get_reorder_service),
) -> ReorderSuggestionsResponse:
    """Return what to reorder. Always 200; `proposals` may be empty.

    Each proposal carries `source` ('rule' or 'llm'); LLM ones include a `reason`
    and `needs_review=true` so the UI can flag them for explicit approval.
    """
    
    return service.get_suggestions()
    ...
