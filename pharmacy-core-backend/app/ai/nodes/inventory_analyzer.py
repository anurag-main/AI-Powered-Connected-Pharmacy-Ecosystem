"""Analysis node for the Inventory Risk Agent."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.inventory_prompts import INVENTORY_ANALYST_SYSTEM_PROMPT
from app.ai.schemas.inventory_analysis import InventoryAnalysis
from app.ai.state.inventory_state import InventoryState
from app.ai.utils.message_utils import get_latest_user_message


def inventory_analyzer(state: InventoryState) -> dict:
    """Explain the computed report in the pharmacist's terms.

    The model receives the report as JSON and explains it. It computes nothing: every
    figure it can quote was already calculated deterministically upstream, and the
    prompt tells it to reproduce them unchanged.

    The answer is appended to the transcript here rather than in a separate node -
    this graph has no retry loop, so the analyzer runs exactly once per turn and
    cannot produce the duplicate-message problem the BI finalizer exists to prevent.
    """

    structured_llm = get_llm().with_structured_output(InventoryAnalysis)

    report = state["report"]

    prompt = f"""
Question:
{get_latest_user_message(state)}

Inventory Risk Report:
{report.model_dump_json(indent=2)}
"""

    messages = [
        SystemMessage(content=INVENTORY_ANALYST_SYSTEM_PROMPT),
        *state["messages"],
        HumanMessage(content=prompt),
    ]

    result = structured_llm.invoke(messages)

    return {
        "answer": result.summary,
        "confidence": result.confidence,
        "messages": [AIMessage(content=result.summary)],
    }
