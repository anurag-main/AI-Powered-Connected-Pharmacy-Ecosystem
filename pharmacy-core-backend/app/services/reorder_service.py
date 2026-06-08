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
from app.schemas.reorder import ReorderProposal, ReorderSuggestionsResponse


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
