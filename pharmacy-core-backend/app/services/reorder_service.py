"""Business-rule layer for the Reorder domain.

Thin wrapper around the compiled reorder graph (same shape as BillingService):
1. Run the graph (fetch → decide → judge)
2. Read the final state
3. Map it into the clean ReorderSuggestionsResponse HTTP contract

NEVER knows HTTP status codes (the router decides). NEVER re-implements node
logic (the graph IS the engine). It's the seam where future cross-cutting rules
(auth, rate limit, caching the nightly run) will land without touching router/graph.
"""
from app.ai.graphs.reorder_graph import get_reorder_graph
from app.core.database import SessionLocal
from app.repositories.sqlalchemy_reorder_request_repository import (
    SQLAlchemyReorderRequestRepository,
)
from app.schemas.reorder import (
    ReorderProposal,
    ReorderRequestOut,
    ReorderSuggestionsResponse,
)


class ReorderService:
    """Runs the reorder graph and shapes its output into the response."""

    def get_suggestions(self) -> ReorderSuggestionsResponse:
        """Run the whole reorder agent and return the proposals.

        The graph pulls its own data (invoke with empty state). Proposals may be
        empty — that's a valid result meaning "nothing needs reordering".
        """
        final_state = get_reorder_graph().invoke({})

        # ReorderProposal ignores extra keys, so we can hand it the raw dicts.
        proposals = [ReorderProposal(**p) for p in final_state.get("proposals", [])]

        return ReorderSuggestionsResponse(
            count=len(proposals),
            proposals=proposals,
            errors=final_state.get("errors", []),
        )

    def approve(
        self, *, medicine_id: int, quantity: int, source: str, reason: str | None
    ) -> ReorderRequestOut:
        """Persist an approved suggestion as a 'pending' reorder request.

        IDEMPOTENT: if a pending request for this medicine already exists, we
        return THAT one instead of inserting a duplicate. So a double-click or a
        retried POST can't create two orders for the same medicine — the classic
        reason POST handlers need an idempotency guard.
        """
        with SessionLocal() as db:
            repo = SQLAlchemyReorderRequestRepository(db)
            row = repo.find_pending(medicine_id) or repo.create(
                medicine_id=medicine_id,
                quantity=quantity,
                source=source,
                reason=reason,
            )
            return ReorderRequestOut.model_validate(row)
