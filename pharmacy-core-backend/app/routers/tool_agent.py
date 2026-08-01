"""Routes for the LangGraph Tool Calling Agent."""

from fastapi import APIRouter, Depends

from app.schemas.business import (
    BusinessAnalysisRequest,
    BusinessAnalysisResponse,
)
from app.services.tool_agent_service import (
    ToolAgentService,
)

router = APIRouter(
    prefix="/tool-agent",
    tags=["Tool Agent"],
)


def get_tool_agent_service() -> ToolAgentService:
    """
    Dependency injection for the Tool Agent service.
    """
    return ToolAgentService()


@router.post(
    "/chat",
    response_model=BusinessAnalysisResponse,
)
def chat(
    request: BusinessAnalysisRequest,
    service: ToolAgentService = Depends(
        get_tool_agent_service,
    ),
) -> BusinessAnalysisResponse:
    """
    Chat with the LangGraph Tool Calling Agent.
    """

    return service.chat(request)