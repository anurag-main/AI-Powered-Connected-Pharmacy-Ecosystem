"""LangGraph node — extract_intent.

Takes the pharmacist's free-text sentence (state['pharmacist_input'])
and produces a validated `ExtractedIntent` (state['extracted_intent']).

This is the FIRST node in the billing graph. Its job is to convert
unstructured text into a clean dict the downstream nodes can trust.

Analogy (kid-level):
    A kid walks into the candy shop. Rohit (the LLM helper):
      1. Listens to the kid               (read state['pharmacist_input'])
      2. Calls mom if the kid is silent   (return errors and skip the LLM)
      3. Pulls out the instruction card   (SystemMessage with our prompt)
      4. Reads the kid's words to himself (HumanMessage with the sentence)
      5. Fills the notebook page          (.with_structured_output(ExtractedIntent))
      6. Drops the page in mom's basket   (return {'extracted_intent': ...})

Why return a partial dict instead of the whole state?
    LangGraph MERGES the dict you return into the existing state automatically.
    Returning {"extracted_intent": ...} keeps the rest of the state untouched.
    Cleaner than copying state and mutating it.
"""
from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import get_llm
from app.ai.prompts.billing_prompts import EXTRACT_INTENT_SYSTEM_PROMPT_V1
from app.ai.schemas.extracted_intent import ExtractedIntent
from app.ai.state.billing_state import BillingState


def extract_intent(state: BillingState) -> dict:
    """Parse pharmacist_input → extracted_intent."""

    # YOUR JOB 1 — read pharmacist_input out of state
    # The pharmacist's typed/spoken sentence sits at state["pharmacist_input"].
    # Use state.get(...) with a default of "" so a missing key doesn't crash.
    # Write 1 line below:
    #     pharmacist_input: str = state.get("pharmacist_input", "")


    # YOUR JOB 2 — empty-input guard
    # If pharmacist_input is empty or only whitespace, return early with
    # an errors list — do NOT call the LLM (saves money, surfaces bugs cleanly).
    # Return shape:  {"errors": ["pharmacist_input is empty"]}
    # Write 2 lines below (an `if` and a `return`):


    # YOUR JOB 3 — build the structured LLM chain
    # Step A: get the cached client (Maverick) via get_llm()
    # Step B: wrap it with .with_structured_output(ExtractedIntent)
    #         This is what forces Maverick to return a Pydantic instance.
    # Write 2 lines below:
    #     llm = get_llm()
    #     structured_llm = llm.with_structured_output(ExtractedIntent)


    # YOUR JOB 4 — build the messages list
    # Two messages — order matters: System FIRST, Human SECOND.
    #   - SystemMessage(content=EXTRACT_INTENT_SYSTEM_PROMPT_V1)  ← the instruction card
    #   - HumanMessage(content=pharmacist_input)                  ← the kid's words
    # Write the list below (3 lines):


    # YOUR JOB 5 — invoke the chain
    # Call structured_llm.invoke(messages). The return is an ExtractedIntent instance.
    # If validation fails inside, this raises — let it propagate for now (we'll add
    # retries in a later step).
    # Write 1 line below:
    #     result: ExtractedIntent = structured_llm.invoke(messages)


    # YOUR JOB 6 — return the state update
    # LangGraph will merge whatever dict you return INTO the existing state.
    # Return {"extracted_intent": <plain dict, NOT the Pydantic object>}.
    # Use result.model_dump() to convert Pydantic → dict.
    # Write 1 line below:
    #     return {"extracted_intent": result.model_dump()}

    # Replace this placeholder when you've written the steps above:
    raise NotImplementedError("YOUR JOB markers not implemented yet")


# ============================================================================
# End-to-end smoke test — actually calls Maverick via NVIDIA
# Run with:
#     cd c:\ai-pharmacy-ecosystem\pharmacy-core-backend
#     .\venv\Scripts\Activate.ps1
#     python -m app.ai.nodes.extract_intent
# ============================================================================

if __name__ == "__main__":
    import json

    test_inputs = [
        "2 strips Crocin 500mg and 1 bottle Benadryl cough syrup for Anurag 9876543210",
        "give me 3 strips Dolo 650",
        "5 tubes Volini gel for Sneha, her number is +91 98765-43210",  # tests rule 10 (phone format)
        "",  # tests the empty-input guard — should NOT call the LLM
    ]

    for i, text in enumerate(test_inputs, 1):
        print(f"\n========== Test {i} ==========")
        print(f"INPUT : {text!r}")
        try:
            output = extract_intent({"pharmacist_input": text})
            print("OUTPUT:")
            print(json.dumps(output, indent=2, ensure_ascii=False))
        except NotImplementedError as e:
            print(f"OUTPUT: NotImplementedError → {e}")
            print("(fill in the YOUR JOB markers, then re-run this test)")
            break
        except Exception as e:  # noqa: BLE001
            print(f"OUTPUT: {type(e).__name__} → {e}")
