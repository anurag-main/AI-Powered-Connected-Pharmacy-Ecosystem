"""Business tools used by the Business Intelligence Agent."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from langchain_core.tools import tool

from app.core.database import SessionLocal
from app.repositories.business_repository import BusinessRepository


# ------------------------------------------------------------------------
# Shared Repository Executor
# ------------------------------------------------------------------------

def execute_repository_method(
    repository_method: Callable[[BusinessRepository], dict],
) -> dict:
    """
    Execute a repository method with its own database session.
    """

    db = SessionLocal()

    try:
        repository = BusinessRepository(db)
        return repository_method(repository)

    finally:
        db.close()


# ------------------------------------------------------------------------
# LangChain Tools
# ------------------------------------------------------------------------

@tool
def get_sales_summary() -> dict:
    """
    Return pharmacy sales metrics.

    Use for:
    - sales
    - revenue
    - orders
    """

    return execute_repository_method(
        BusinessRepository.get_sales_summary,
    )


@tool
def get_purchase_summary() -> dict:
    """
    Return pharmacy purchase metrics.

    Use for:
    - purchases
    - suppliers
    """

    return execute_repository_method(
        BusinessRepository.get_purchase_summary,
    )


@tool
def get_return_summary() -> dict:
    """
    Return pharmacy return metrics.

    Use for:
    - returns
    - return analysis
    """

    return execute_repository_method(
        BusinessRepository.get_return_summary,
    )


@tool
def get_expiry_summary() -> dict:
    """
    Return pharmacy expiry metrics.

    Use for:
    - expiry
    - expired medicines
    """

    return execute_repository_method(
        BusinessRepository.get_expiry_summary,
    )


@tool
def get_margin_summary() -> dict:
    """
    Return pharmacy profit metrics.

    Use for:
    - profit
    - margin
    """

    return execute_repository_method(
        BusinessRepository.get_margin_summary,
    )


# ------------------------------------------------------------------------
# Existing Registry (Temporary)
# ------------------------------------------------------------------------

TOOL_REGISTRY = {
    "sales": get_sales_summary,
    "purchases": get_purchase_summary,
    "returns": get_return_summary,
    "expiry": get_expiry_summary,
    "margin": get_margin_summary,
}


# ------------------------------------------------------------------------
# Existing Fetcher Support (Temporary)
# ------------------------------------------------------------------------

def execute_tool(task: str) -> tuple[str, dict]:
    """
    Execute one business capability.

    Temporary adapter until ToolNode replaces the Fetcher.
    """

    tool_fn = TOOL_REGISTRY.get(task)

    if tool_fn is None:
        raise ValueError(
            f"Unknown business capability: {task}"
        )

    result = tool_fn.invoke({})

    return task, result


def get_business_metrics(
    plan: list[str],
) -> dict:
    """
    Execute all requested tools in parallel.

    Temporary implementation until ToolNode replaces this function.
    """

    if not plan:
        return {}

    metrics = {}

    max_workers = min(len(plan), 5)

    with ThreadPoolExecutor(
        max_workers=max_workers,
    ) as executor:

        future_to_task = {
            executor.submit(
                execute_tool,
                task,
            ): task
            for task in plan
        }

        for future in as_completed(
            future_to_task
        ):

            task = future_to_task[future]

            try:
                _, result = future.result()

                metrics[task] = result

            except Exception as exc:  # noqa: BLE001

                metrics[task] = {
                    "error": str(exc)
                }

    return metrics