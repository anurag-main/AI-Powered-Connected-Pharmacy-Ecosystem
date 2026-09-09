"""Business logic layer for the Expiry Risk Agent."""

import time
import uuid

from langchain_core.messages import HumanMessage

from app.ai.graphs.expiry_graph import AGENT_NAME, AGENT_VERSION, get_expiry_graph
from app.ai.observability import ai_run
from app.ai.schemas.expiry_query import ExpiryRiskQuery
from app.ai.tools import expiry_tools
from app.schemas.expiry import (
    ExpiryAnalysisRequest,
    ExpiryAnalysisResponse,
    ExpiryExplanationResponse,
    ExpiryReportResponse,
)


class ExpiryAgentService:
    """Runs the Expiry Risk graph and shapes its state into the HTTP contract."""

    def analyze(self, request: ExpiryAnalysisRequest) -> ExpiryAnalysisResponse:
        """Answer one expiry-risk question."""

        start = time.perf_counter()

        config = {"configurable": {"thread_id": request.thread_id}}

        # The service owns exactly one graph invocation, which is what a run is.
        with ai_run(AGENT_NAME, thread_id=request.thread_id):
            final_state = get_expiry_graph().invoke(
                {"messages": [HumanMessage(content=request.question)]},
                config=config,
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)
        report = final_state["report"]

        # The structured report travels alongside the prose so a caller never has to
        # parse figures back out of a sentence.
        return ExpiryAnalysisResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            total_batches_reviewed=report.total_batches_reviewed,
            total_at_risk=report.total_at_risk,
            total_value_at_risk=report.total_value_at_risk,
            items=report.items,
            notes=report.notes,
            execution_time_ms=elapsed_ms,
            agent_version=AGENT_VERSION,
        )

    # -- dashboard: numbers first, prose second -------------------------

    def report(self, query: ExpiryRiskQuery) -> ExpiryReportResponse:
        """Run the deterministic assessment for an already-structured query.

        No graph, no LLM, no cost. The dashboard's filters are the query, so there
        is nothing to plan and nothing to explain yet - it just needs the numbers,
        as fast as possible.

        Reached through the module rather than by importing the function, so a test
        patching ``expiry_tools.run_expiry_risk`` is actually seen here.
        """

        start = time.perf_counter()
        report = expiry_tools.run_expiry_risk(query)

        return ExpiryReportResponse(
            generated_for=report.generated_for,
            window_days=report.window_days,
            demand_lookback_days=report.demand_lookback_days,
            total_batches_reviewed=report.total_batches_reviewed,
            total_at_risk=report.total_at_risk,
            total_value_at_risk=report.total_value_at_risk,
            counts_by_risk=report.counts_by_risk,
            items=report.items,
            notes=report.notes,
            execution_time_ms=int((time.perf_counter() - start) * 1000),
        )

    def explain(self, query: ExpiryRiskQuery) -> ExpiryExplanationResponse:
        """Explain the report for a query the caller has already run.

        Goes through the graph so the analyst node, its prompt and the whole
        observability chain are shared with the chat endpoint - but seeds ``query``
        in the initial state, which makes the graph skip the planner. The prose is
        therefore guaranteed to describe the same rows the dashboard is showing.

        A throwaway thread id: this is a one-shot explanation, not a conversation,
        and reusing one would let an earlier dashboard view leak into this answer.
        """

        start = time.perf_counter()
        thread_id = f"expiry-report-{uuid.uuid4().hex[:12]}"

        with ai_run(AGENT_NAME, thread_id=thread_id):
            final_state = get_expiry_graph().invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=(
                                "Explain this expiry risk report for a pharmacy "
                                f"owner. The report covers: {query.describe()}."
                            )
                        )
                    ],
                    "query": query,
                },
                config={"configurable": {"thread_id": thread_id}},
            )

        return ExpiryExplanationResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            execution_time_ms=int((time.perf_counter() - start) * 1000),
            agent_version=AGENT_VERSION,
        )
