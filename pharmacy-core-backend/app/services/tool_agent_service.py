"""Service for the LangGraph Tool Calling Agent."""

import time

from langchain_core.messages import HumanMessage

from app.ai.graphs.business_tool_graph import (
    get_business_tool_graph,
)
from app.schemas.business import (
    BusinessAnalysisRequest,
    BusinessAnalysisResponse,
)


class ToolAgentService:
    """
    Executes the native LangGraph Tool Calling Agent.
    """

    def chat(
        self,
        request: BusinessAnalysisRequest,
    ) -> BusinessAnalysisResponse:
        """
        Execute the Tool Calling graph.
        """

        start = time.perf_counter()

        config = {
            "configurable": {
                "thread_id": "tool-agent-demo",
            }
        }

        final_state = get_business_tool_graph().invoke(
            {
                "messages": [
                    HumanMessage(
                        content=request.question,
                    )
                ]
            },
            config=config,
        )

        elapsed_ms = int(
            (time.perf_counter() - start) * 1000
        )

        return BusinessAnalysisResponse(
            answer=final_state["messages"][-1].content,
            confidence=1.0,
            execution_time_ms=elapsed_ms,
            agent_version="tool-agent-v1",
        )