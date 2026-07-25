"""Business tools used by the Business Intelligence Agent."""

from app.core.database import SessionLocal
from app.repositories.business_repository import BusinessRepository


def get_business_metrics(plan: list[str]) -> dict:
    """
    Fetch all requested business metrics.
    """

    db = SessionLocal()

    try:
        repository = BusinessRepository(db)

        metrics = {}

        if "sales" in plan:
            metrics["sales"] = repository.get_sales_summary()

        if "purchases" in plan:
            metrics["purchases"] = repository.get_purchase_summary()

        if "returns" in plan:
            metrics["returns"] = repository.get_return_summary()

        if "expiry" in plan:
            metrics["expiry"] = repository.get_expiry_summary()

        if "margin" in plan:
            metrics["margin"] = repository.get_margin_summary()

        return metrics

    finally:
        db.close()