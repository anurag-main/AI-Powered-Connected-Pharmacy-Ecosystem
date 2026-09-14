"""Planning node for the Inventory Risk Agent."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.inventory_prompts import INVENTORY_PLANNER_SYSTEM_PROMPT
from app.ai.schemas.inventory_query import InventoryRiskQuery
from app.ai.state.inventory_state import InventoryState
from app.ai.utils.message_utils import get_latest_user_message


def inventory_planner(state: InventoryState) -> dict:
    """Turn the user's question into a validated InventoryRiskQuery.

    Structured output means an invented risk level, an out-of-range target cover or a
    sort that does not exist fails Pydantic validation here rather than reaching the
    service.
    """

    structured_llm = get_llm().with_structured_output(InventoryRiskQuery)

    messages = [
        SystemMessage(content=INVENTORY_PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=get_latest_user_message(state)),
    ]

    return {"query": structured_llm.invoke(messages)}
