"""Business logic layer for the Expiry Risk Agent."""

import time

from langchain_core.messages import HumanMessage

from app.ai.graphs.expiry_graph import AGENT_NAME, AGENT_VERSION, get_expiry_graph
from app.ai.observability import ai_run
from app.schemas.expiry import ExpiryAnalysisRequest, ExpiryAnalysisResponse


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
