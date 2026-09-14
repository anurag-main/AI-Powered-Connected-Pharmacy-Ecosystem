"""Fetch node for the Inventory Risk Agent."""

from app.ai.state.inventory_state import InventoryState
from app.ai.tools import inventory_tools


def inventory_fetcher(state: InventoryState) -> dict:
    """Run the deterministic risk assessment for the planned query.

    Everything of substance happens below this line - repositories, demand, then the
    service. This node exists only to connect the plan to the calculation, which is
    why there is no logic in it to test.

    The tool is reached through the module rather than imported by name. `from x
    import f` binds the function by value, so a test patching
    `inventory_tools.run_inventory_risk` would never be seen here - the same trap the
    BI nodes hit with get_llm().
    """

    return {"report": inventory_tools.run_inventory_risk(state["query"])}
