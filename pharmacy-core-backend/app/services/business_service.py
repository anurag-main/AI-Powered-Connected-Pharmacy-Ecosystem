"""Business logic layer for the Business Intelligence Agent."""

import time

from langchain_core.messages import HumanMessage

from app.ai.graphs.business_graph import AGENT_NAME, AGENT_VERSION, get_business_graph
from app.ai.observability import ai_run
from app.schemas.business import (
    BusinessAnalysisRequest,
    BusinessAnalysisResponse,
)


class BusinessService:
    """Runs the Business Intelligence graph."""

    def analyze(
        self,
        request: BusinessAnalysisRequest,
    ) -> BusinessAnalysisResponse:
        """
        Run the Business Intelligence Agent.
        """

        start = time.perf_counter()

        config = {
            "configurable": {
                "thread_id": request.thread_id,
            }
        }

        # The service is where a run_id is minted: it owns exactly one graph
        # invocation, which is precisely what a run is. The router above it handles
        # many kinds of request, and the graph below it should not have to know it is
        # being observed.
        with ai_run(AGENT_NAME, thread_id=request.thread_id):
            final_state = get_business_graph().invoke(
                {
                    "messages": [
                        HumanMessage(
                            content=request.question,
                        )
                    ],
                },
                config=config,
            )

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        # Both fields used to be read out of graph state with a fallback, and no
        # node ever wrote either — so the fallback was always what shipped. They are
        # now computed where the information actually exists: the elapsed time here,
        # the version alongside the graph it describes.
        return BusinessAnalysisResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            execution_time_ms=elapsed_ms,
            agent_version=AGENT_VERSION,
        )