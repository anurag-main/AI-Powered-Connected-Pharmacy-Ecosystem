"""Fetch node for the Expiry Risk Agent."""

from app.ai.state.expiry_state import ExpiryState
from app.ai.tools import expiry_tools


def expiry_fetcher(state: ExpiryState) -> dict:
    """Run the deterministic risk assessment for the planned query.

    Everything of substance happens below this line - repository, then service. This
    node exists only to connect the plan to the calculation, which is why there is no
    logic in it to test.

    The tool is reached through the module rather than imported by name. `from x
    import f` binds the function by value, so a test patching `expiry_tools.run_expiry_risk`
    would never be seen here - the same trap the BI nodes hit with get_llm().
    """

    return {"report": expiry_tools.run_expiry_risk(state["query"])}
