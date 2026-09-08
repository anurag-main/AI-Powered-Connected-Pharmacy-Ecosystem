"""Analysis node for the Expiry Risk Agent."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.expiry_prompts import EXPIRY_ANALYST_SYSTEM_PROMPT
from app.ai.schemas.expiry_analysis import ExpiryAnalysis
from app.ai.state.expiry_state import ExpiryState
from app.ai.utils.message_utils import get_latest_user_message


def expiry_analyzer(state: ExpiryState) -> dict:
    """Explain the computed report in the pharmacist's terms.

    The model receives the report as JSON and explains it. It computes nothing: every
    figure it can quote was already calculated deterministically upstream, and the
    prompt tells it to reproduce them unchanged.

    The answer is appended to the transcript here rather than in a separate node -
    this graph has no retry loop, so the analyzer runs exactly once per turn and
    cannot produce the duplicate-message problem the BI finalizer exists to prevent.
    """

    structured_llm = get_llm().with_structured_output(ExpiryAnalysis)

    report = state["report"]

    prompt = f"""
Question:
{get_latest_user_message(state)}

Expiry Risk Report:
{report.model_dump_json(indent=2)}
"""

    messages = [
        SystemMessage(content=EXPIRY_ANALYST_SYSTEM_PROMPT),
        *state["messages"],
        HumanMessage(content=prompt),
    ]

    result = structured_llm.invoke(messages)

    return {
        "answer": result.summary,
        "confidence": result.confidence,
        "messages": [AIMessage(content=result.summary)],
    }
