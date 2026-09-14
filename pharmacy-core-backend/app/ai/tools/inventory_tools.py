"""The inventory-risk tool: the agent's only route to inventory data.

Same shape as the expiry and business tools — one parameterised entry point taking a
validated query. The model chooses a target cover, a risk level, a sort and a limit;
it cannot choose a table, a column, a threshold, or how capital at risk is computed.
"""

from __future__ import annotations

import logging
from datetime import date

from langchain_core.tools import tool

from app.ai.observability import observe_tool
from app.ai.schemas.inventory_query import InventoryRiskQuery, InventoryRiskReport
from app.core.database import SessionLocal
from app.repositories.inventory_repository import InventoryRepository
from app.services.demand_service import DemandService
from app.services.inventory_risk_service import InventoryRiskService

logger = logging.getLogger("app.ai.tools")


def run_inventory_risk(
    query: InventoryRiskQuery, *, as_of: date | None = None
) -> InventoryRiskReport:
    """Assess inventory risk for one validated query.

    Opens its own session because LangGraph nodes do not receive FastAPI's
    ``Depends(get_db)``. SQL stays in the repositories, demand stays in
    ``DemandService``, and the maths stays in ``InventoryRiskService``.
    """

    with observe_tool("inventory_risk"):
        # Shape only. Never the medicines, the stock levels, or the money — this
        # endpoint handles cost prices, which are more sensitive than the expiry
        # report's figures.
        logger.debug(
            "inventory_query_executing",
            extra={
                "target_cover_days": query.target_cover_days,
                "risk_level": query.risk_level.value if query.risk_level else None,
                "sort": query.sort.value,
                "limit": query.limit,
            },
        )

        with SessionLocal() as db:
            service = InventoryRiskService(
                InventoryRepository(db), DemandService(db)
            )
            return service.assess(query, as_of=as_of)


@tool("get_inventory_risk", args_schema=InventoryRiskQuery)
def get_inventory_risk(**kwargs) -> dict:
    """Find inventory that is absorbing capital, ranked worst first.

    Returns, for each medicine: stock on hand, what it is worth, how fast it sells,
    days of cover, how much sits above the target, the money at risk, how long the
    stock has been held, a risk level and the reasons behind it.

    This is about CAPITAL, not dates. For "what will expire", use the expiry tool.

    Every figure is computed from real stock and sales data. Report them exactly as
    given — do not recalculate, re-estimate or round them.

    Examples of what maps to what:
      "what is overstocked"            -> defaults
      "dead stock"                     -> risk_level=dead
      "where is my money stuck"        -> sort=capital_at_risk
      "what have I held longest"       -> sort=stock_age
      "what do I have most of"         -> sort=days_of_cover
      "anything over Rs 10,000"        -> min_capital_at_risk=10000
      "if I only kept a month's stock" -> target_cover_days=30
    """

    # Re-validating turns a malformed tool call into a clean ValidationError rather
    # than a confusing failure deeper down.
    report = run_inventory_risk(InventoryRiskQuery(**kwargs))
    return report.model_dump(mode="json")


INVENTORY_TOOLS = [get_inventory_risk]
