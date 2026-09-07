"""Reflection node for the Business Intelligence Agent."""

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.reflection_prompt import REFLECTION_SYSTEM_PROMPT
from app.ai.schemas.reflection import ReflectionOutput
from app.ai.state.business_state import BusinessState
from app.ai.utils.message_utils import get_latest_user_message


def business_reflector(state: BusinessState) -> dict:
    """Decide whether more business data is needed before answering.

    Two guards sit between the model's verdict and another fetch, because an
    unchecked retry is either wasted money or an infinite loop:

    1. A query already in the plan is discarded. Re-running an identical fetch
       returns identical data and changes nothing, so it can only burn a cycle.
    2. Retry happens only when there is genuinely something NEW to fetch. A
       reflector that is unhappy but cannot name a useful query is unhappy about
       something fetching will not fix — the answer is to finish, not to spin.

    Queries the model invents are filtered by Pydantic before reaching here: a
    nonexistent metric or an unsupported dimension fails validation, so the model
    cannot smuggle in a data source that does not exist.
    """

    structured_llm = get_llm().with_structured_output(ReflectionOutput)

    latest_question = get_latest_user_message(state)
    plan = state["plan"]
    collected = state.get("business_metrics") or {}

    already_asked = {query.key() for query in plan}

    messages = [
        SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
        HumanMessage(
            content=f"""
Business Question:
{latest_question}

Queries already run:
{[query.describe() for query in plan]}

Collected Business Data:
{collected}

Draft Analysis:
{state["answer"]}
"""
        ),
    ]

    result = structured_llm.invoke(messages)

    new_queries = [
        query for query in result.missing_queries if query.key() not in already_asked
    ]

    return {
        "reflection_count": state.get("reflection_count", 0) + 1,
        "reflection": result.reason,
        "retry": (not result.sufficient) and bool(new_queries),
        "plan": plan + new_queries,
    }
