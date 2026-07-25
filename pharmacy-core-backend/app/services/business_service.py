"""Business logic layer for the Business Intelligence Agent."""

import time

from app.ai.graphs.business_graph import get_business_graph
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

        final_state = get_business_graph().invoke(
            {
                "question": request.question,
            }
        )

        elapsed_ms = int((time.perf_counter() - start) * 1000)

        return BusinessAnalysisResponse(
            answer=final_state["answer"],
            confidence=final_state["confidence"],
            execution_time_ms=final_state.get("execution_time_ms", elapsed_ms),
            agent_version=final_state.get("agent_version", "business-agent-v1"),
        )