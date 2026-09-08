"""Planning node for the Expiry Risk Agent."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.expiry_prompts import EXPIRY_PLANNER_SYSTEM_PROMPT
from app.ai.schemas.expiry_query import ExpiryRiskQuery
from app.ai.state.expiry_state import ExpiryState
from app.ai.utils.message_utils import get_latest_user_message


def expiry_planner(state: ExpiryState) -> dict:
    """Turn the user's question into a validated ExpiryRiskQuery.

    Structured output means a nonsensical window or an invented risk level fails
    Pydantic validation here rather than reaching the repository.
    """

    structured_llm = get_llm().with_structured_output(ExpiryRiskQuery)

    messages = [
        SystemMessage(content=EXPIRY_PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=get_latest_user_message(state)),
    ]

    return {"query": structured_llm.invoke(messages)}
