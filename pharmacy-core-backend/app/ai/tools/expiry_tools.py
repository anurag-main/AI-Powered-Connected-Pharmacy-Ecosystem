"""The expiry-risk tool: the agent's only route to expiry data.

Same shape as the business tools — one parameterised entry point taking a validated
query. The model chooses a window, a risk level and a limit; it cannot choose a table,
a column, or how risk is computed.
"""

from __future__ import annotations

import logging
from datetime import date

from langchain_core.tools import tool

from app.ai.observability import observe_tool
from app.ai.schemas.expiry_query import ExpiryRiskQuery, ExpiryRiskReport
from app.core.database import SessionLocal
from app.repositories.expiry_repository import ExpiryRepository
from app.services.expiry_risk_service import ExpiryRiskService

logger = logging.getLogger("app.ai.tools")


def run_expiry_risk(
    query: ExpiryRiskQuery, *, as_of: date | None = None
) -> ExpiryRiskReport:
    """Assess expiry risk for one validated query.

    Opens its own session because LangGraph nodes do not receive FastAPI's
    ``Depends(get_db)``. SQL stays in the repository; the maths stays in the service.
    """

    with observe_tool("expiry_risk"):
        # Shape only — never the batches or the money.
        logger.debug(
            "expiry_query_executing",
            extra={
                "window_days": query.window_days,
                "risk_level": query.risk_level.value if query.risk_level else None,
                "limit": query.limit,
            },
        )

        with SessionLocal() as db:
            service = ExpiryRiskService(ExpiryRepository(db))
            return service.assess(query, as_of=as_of)


@tool("get_expiry_risk", args_schema=ExpiryRiskQuery)
def get_expiry_risk(**kwargs) -> dict:
    """Find stock at risk of expiring, ranked by how much money is at stake.

    Returns, for each batch: days to expiry, stock on hand, how much is expected to
    sell before it expires, the resulting excess, the value at risk, a risk level and
    the reasons behind it.

    Every figure is computed from real stock and sales data. Report them exactly as
    given — do not recalculate, re-estimate or round them.

    Examples of what maps to what:
      "what expires soon"            -> window_days=30
      "critical expiry risks"        -> risk_level=critical
      "expiring this week"           -> window_days=7
      "top 5 by value at risk"       -> limit=5
      "what should I act on first"   -> default window, limit=5
    """

    # Re-validating turns a malformed tool call into a clean ValidationError rather
    # than a confusing failure deeper down.
    report = run_expiry_risk(ExpiryRiskQuery(**kwargs))
    return report.model_dump(mode="json")


EXPIRY_TOOLS = [get_expiry_risk]
