"""Business tools used by the Business Intelligence Agent."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from app.core.database import SessionLocal
from app.repositories.business_repository import BusinessRepository


# ------------------------------------------------------------------------
# Tool Registry
# ------------------------------------------------------------------------

TOOL_REGISTRY = {
    "sales": BusinessRepository.get_sales_summary,
    "purchases": BusinessRepository.get_purchase_summary,
    "returns": BusinessRepository.get_return_summary,
    "expiry": BusinessRepository.get_expiry_summary,
    "margin": BusinessRepository.get_margin_summary,
}


def execute_tool(task: str) -> tuple[str, dict]:
    """
    Execute a single business capability.

    Each execution gets its own database session,
    making it safe for parallel execution.
    """

    db = SessionLocal()

    try:
        repository = BusinessRepository(db)

        tool = TOOL_REGISTRY.get(task)

        if tool is None:
            raise ValueError(
                f"Unknown business capability: {task}"
            )

        result = tool(repository)

        return task, result

    finally:
        db.close()


def get_business_metrics(plan: list[str]) -> dict:
    """
    Execute all requested business capabilities
    in parallel and return the collected metrics.
    """

    metrics = {}

    if not plan:
        return metrics

    max_workers = max(1, min(len(plan), 5))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:

        future_to_task = {
            executor.submit(execute_tool, task): task
            for task in plan
        }

        for future in as_completed(future_to_task):

            task = future_to_task[future]

            # Isolate failures: one broken capability records an error and the
            # rest of the metrics still come back, instead of failing the run.
            try:
                _, result = future.result()
                metrics[task] = result
            except Exception as exc:  # noqa: BLE001
                metrics[task] = {"error": str(exc)}

    return metrics