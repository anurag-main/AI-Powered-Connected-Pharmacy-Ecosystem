"""Business data access for the BI agent.

WHAT CHANGED AND WHY
--------------------
This module used to expose five **zero-argument** tools (``get_sales_summary()`` and
friends). That made a whole class of question unanswerable: with no parameters the
planner had no way to express "last month" or "top 5 by product", so those questions
silently returned an all-time total — the right shape of answer to the wrong question.

Now there is one parameterised entry point. The parameters are a validated
:class:`~app.ai.schemas.business_query.BusinessQuery`, so the surface is wider in
*expressiveness* while being narrower in *authority*: every field is a closed enum or
a bounded integer, and Pydantic rejects anything else before our code runs.

The model cannot supply SQL, a table name, a column name, an operator, or an
unbounded limit. There is nothing to allowlist against, because nothing else is
representable.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from langchain_core.tools import tool

from app.ai.observability import observe_tool
from app.ai.schemas.business_query import BusinessQuery, Metric
from app.core.context import bind_context
from app.core.database import SessionLocal
from app.repositories.business_repository import BusinessRepository

logger = logging.getLogger("app.ai.tools")

# One worker per metric is the most any single plan can usefully need.
MAX_PARALLEL_QUERIES = 5

# Kept as the canonical list of what can be measured, for prompts and validation.
SUPPORTED_METRICS = frozenset(Metric)


# ------------------------------------------------------------------------
# Deterministic executor
# ------------------------------------------------------------------------


def execute_business_query(
    query: BusinessQuery, *, as_of: date | None = None
) -> dict:
    """Run one validated query against the database.

    Opens its own session because LangGraph nodes do not receive FastAPI's
    ``Depends(get_db)``. The SQL itself stays in the repository.
    """

    with observe_tool(query.key()):
        # Logged as shape, never as rows: which metric over which window, not what
        # the pharmacy earned.
        logger.debug(
            "business_query_executing",
            extra={
                "metric": query.metric.value,
                "dimension": query.dimension.value if query.dimension else None,
                "period": query.period.value,
                "limit": query.limit,
            },
        )

        with SessionLocal() as db:
            return BusinessRepository(db).run(query, as_of=as_of)


def get_business_metrics(
    queries: list[BusinessQuery], *, as_of: date | None = None
) -> dict:
    """Execute every planned query in parallel, keyed by ``query.key()``.

    Failure is isolated per query: one broken metric becomes an ``error`` entry while
    the rest return real figures, so a partial outage degrades the answer instead of
    losing it. The analyzer is prompted to disclose those entries rather than answer
    around them.
    """

    if not queries:
        return {}

    metrics: dict[str, dict] = {}
    workers = min(len(queries), MAX_PARALLEL_QUERIES)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # bind_context captures this thread's correlation ids so each worker's tool
        # log line still carries the request and run it belongs to.
        future_to_query = {
            executor.submit(
                bind_context(execute_business_query, query, as_of=as_of)
            ): query
            for query in queries
        }

        for future in as_completed(future_to_query):
            query = future_to_query[future]
            try:
                metrics[query.key()] = future.result()
            except Exception as exc:  # noqa: BLE001 — isolate, record, keep going
                metrics[query.key()] = {"error": str(exc)}

    return metrics


# ------------------------------------------------------------------------
# LangChain tool surface
# ------------------------------------------------------------------------


@tool("query_business_data", args_schema=BusinessQuery)
def query_business_data(**kwargs) -> dict:
    """Query the pharmacy's business data: sales, purchases, returns, expiry, margin.

    Returns either overall totals for a period, or a ranked breakdown when a
    dimension is given. All arithmetic and date resolution happen in the database and
    application code — the figures returned are authoritative and must be reported
    as-is, never recomputed or estimated.

    Examples of what maps to what:
      "total sales"                  -> metric=sales
      "sales last month"             -> metric=sales, period=last_month
      "top 5 products by sales"      -> metric=sales, dimension=product, limit=5
      "which supplier cost the most" -> metric=purchases, dimension=supplier, limit=1
      "profit margin this quarter"   -> metric=margin, period=this_quarter
    """

    # Re-validating turns a malformed tool call into a clean ValidationError rather
    # than a confusing failure deeper in the repository.
    return execute_business_query(BusinessQuery(**kwargs))


BUSINESS_TOOLS = [query_business_data]
