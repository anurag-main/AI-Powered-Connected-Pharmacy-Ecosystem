"""Business logic layer for the Inventory Risk Agent."""

import time
import uuid

from langchain_core.messages import HumanMessage

from app.ai.graphs.inventory_graph import (
    AGENT_NAME,
    AGENT_VERSION,
    get_inventory_graph,
)
from app.ai.observability import ai_run
from app.ai.schemas.inventory_query import InventoryRiskQuery
from app.ai.tools import inventory_tools
from app.schemas.inventory import (
    InventoryAnalysisRequest,
    InventoryAnalysisResponse,
    InventoryExplanationResponse,
    InventoryReportResponse,
)


class InventoryAgentService:
    """Runs the Inventory Risk graph and shapes its state into the HTTP contract."""

    def analyze(self, request: InventoryAnalysisRequest) -> InventoryAnalysisResponse:
        """Answer one inventory-risk question.

        The full agent flow: planner, fetcher, analyzer. This is the only endpoint
        that runs the planner, because it is the only one where the parameters have to
        be inferred from a sentence.
        """

        start = time.perf_counter()

        config = {"configurable": {"thread_id": request.thread_id}}

        # The service owns exactly one graph invocation, which is what a run is.
        with ai_run(AGENT_NAME, thread_id=request.thread_id):
            final_state = get_inventory_graph().invoke(
                {"messages": [HumanMessage(content=request.question)]},
                config=config,
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        report = final_state["report"]

        # The structured report travels alongside the prose so a caller never has to
        # parse figures back out of a sentence.
        return InventoryAnalysisResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            medicines_reviewed=report.medicines_reviewed,
            total_inventory_value=report.total_inventory_value,
            total_capital_at_risk=report.total_capital_at_risk,
            items=report.items,
            notes=report.notes,
            execution_time_ms=elapsed_ms,
            agent_version=AGENT_VERSION,
        )

    # -- dashboard: numbers first, prose second -------------------------

    def report(self, query: InventoryRiskQuery) -> InventoryReportResponse:
        """Run the deterministic assessment for an already-structured query.

        No graph, no LLM, no cost. The dashboard's filters are the query, so there is
        nothing to plan and nothing to explain yet - it just needs the numbers, as
        fast as possible.

        Reached through the module rather than by importing the function, so a test
        patching ``inventory_tools.run_inventory_risk`` is actually seen here.
        """

        start = time.perf_counter()
        report = inventory_tools.run_inventory_risk(query)

        return InventoryReportResponse(
            generated_for=report.generated_for,
            demand_lookback_days=report.demand_lookback_days,
            target_cover_days=report.target_cover_days,
            medicines_reviewed=report.medicines_reviewed,
            medicines_without_stock=report.medicines_without_stock,
            items_matching_filter=report.items_matching_filter,
            total_inventory_value=report.total_inventory_value,
            total_capital_at_risk=report.total_capital_at_risk,
            capital_at_risk_in_view=report.capital_at_risk_in_view,
            counts_by_risk=report.counts_by_risk,
            items=report.items,
            notes=report.notes,
            execution_time_ms=int((time.perf_counter() - start) * 1000),
        )

    def explain(self, query: InventoryRiskQuery) -> InventoryExplanationResponse:
        """Explain the report for a query the caller has already run.

        Goes through the graph so the analyst node, its prompt and the whole
        observability chain are shared with the chat endpoint - but seeds ``query`` in
        the initial state, which makes the graph skip the planner. The prose is
        therefore guaranteed to describe the same rows the dashboard is showing.

        A throwaway thread id: this is a one-shot explanation, not a conversation, and
        reusing one would let an earlier dashboard view leak into this answer.
        """

        start = time.perf_counter()
        thread_id = f"inventory-report-{uuid.uuid4().hex[:12]}"

        with ai_run(AGENT_NAME, thread_id=thread_id):
            final_state = get_inventory_graph().invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                "Explain this inventory risk report for a pharmacy "
                                f"owner. The report covers: {query.describe()}."
                            )
                        )
                    ],
                    "query": query,
                },
                config={"configurable": {"thread_id": thread_id}},
            )

        return InventoryExplanationResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            execution_time_ms=int((time.perf_counter() - start) * 1000),
            agent_version=AGENT_VERSION,
        )
