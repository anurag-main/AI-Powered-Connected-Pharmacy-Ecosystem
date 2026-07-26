"""Planning node for the Business Intelligence Agent."""

from langchain_core.messages import SystemMessage, HumanMessage 
from app.ai.state.business_state import BusinessState
from app.ai.llm import get_llm
from app.ai.schemas.planner import PlannerOutput
from app.ai.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT



# This is V1 Planner Keep this for future refrance 
# def business_planner(state: BusinessState) -> BusinessState:
#     """
#     Decide what business metrics are required
#     before answering the user's question.
#     """

#     question = state["question"].lower()

#     if "profit" in question:
#         plan = [
#             "sales",
#             "purchases",
#             "returns",
#             "expiry",
#             "margin",
#         ]

#     elif "sales" in question:
#         plan = [
#             "sales",
#         ]

#     else:
#         plan = [
#             "sales",
#             "purchases",
#             "returns",
#             "expiry",
#             "margin",
#         ]

#     state["plan"] = plan

#     return state


"""This is v2 planner node with Optimized Production grade code """

def business_planner(state: BusinessState) -> BusinessState:
    """
    Analyze the user's question and decide
    which business capabilities are required.
    """

    structured_llm = get_llm().with_structured_output(
        PlannerOutput
    )

    messages = [
        SystemMessage(
            content=PLANNER_SYSTEM_PROMPT,
        ),
        HumanMessage(
            content=state["question"],
        ),
    ]

    result = structured_llm.invoke(messages)

    state["plan"] = result.tasks

    return state
    

    
    
    