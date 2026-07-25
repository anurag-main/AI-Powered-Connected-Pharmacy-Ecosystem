"""Repository for Business Intelligence queries."""

from datetime import datetime, date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.sale import Sale
from app.models.purchase import Purchase
from app.models.returns import Return
from sqlalchemy import case
from app.models.batch import Batch
from app.models.purchase_item import PurchaseItem
from app.models.sale_item import SaleItem


class BusinessRepository:

    """Database access layer for Business Intelligence."""

    def __init__(self, db: Session):
        self.db = db

    def get_sales_summary(self) -> dict:
        """
        Return high-level sales metrics.
        """

        total_sales = (
            self.db.query(
                func.coalesce(func.sum(Sale.total_amount), 0)
            )
            .scalar()
        )

        total_orders = (
            self.db.query(
                func.count(Sale.id)
            )
            .scalar()
        )

        average_order_value = (
            float(total_sales) / total_orders
            if total_orders > 0
            else 0
        )

        latest_sale = (
            self.db.query(
                func.max(Sale.sold_at)
            )
            .scalar()
        )

        return {
            "total_sales": float(total_sales),
            "total_orders": total_orders,
            "average_order_value": round(
                average_order_value,
                2,
            ),
            "latest_sale": latest_sale,
        }

    def get_purchase_summary(self) -> dict:
        """
        Return high-level purchase metrics.
        """

        total_purchase = (
            self.db.query(
                func.coalesce(func.sum(Purchase.total_amount), 0)
            )
            .scalar()
        )

        total_purchase_orders = (
            self.db.query(
                func.count(Purchase.id)
            )
            .scalar()
        )

        average_purchase_value = (
            float(total_purchase) / total_purchase_orders
            if total_purchase_orders > 0
            else 0
        )

        latest_purchase = (
            self.db.query(
                func.max(Purchase.purchase_date)
            )
            .scalar()
        )

        return {
            "total_purchase": float(total_purchase),
            "total_purchase_orders": total_purchase_orders,
            "average_purchase_value": round(
                average_purchase_value,
                2,
            ),
            "latest_purchase": latest_purchase,
        }

    def get_return_summary(self) -> dict:
        """
        Return sales-return and purchase-return metrics.
        """

        total_return_amount = (
            self.db.query(
                func.coalesce(func.sum(Return.amount), 0)
            )
            .scalar()
        )

        total_returns = (
            self.db.query(
                func.count(Return.id)
            )
            .scalar()
        )

        sales_return_amount = (
            self.db.query(
                func.coalesce(func.sum(Return.amount), 0)
            )
            .filter(
                Return.return_type == "sales"
            )
            .scalar()
        )

        purchase_return_amount = (
            self.db.query(
                func.coalesce(func.sum(Return.amount), 0)
            )
            .filter(
                Return.return_type == "purchase"
            )
            .scalar()
        )

        sales_return_count = (
            self.db.query(
                func.count(Return.id)
            )
            .filter(
                Return.return_type == "sales"
            )
            .scalar()
        )

        purchase_return_count = (
            self.db.query(
                func.count(Return.id)
            )
            .filter(
                Return.return_type == "purchase"
            )
            .scalar()
        )

        return {
            "total_returns": total_returns,
            "total_return_amount": float(total_return_amount),
            "sales_return_count": sales_return_count,
            "sales_return_amount": float(sales_return_amount),
            "purchase_return_count": purchase_return_count,
            "purchase_return_amount": float(purchase_return_amount),
        }

    def get_expiry_summary(self) -> dict:
        """
        Return expiry-related business metrics.
        """

        expired_batches = (
            self.db.query(
                func.count(Batch.id)
            )
            .filter(
                Batch.expiry_date < date.today()
            )
            .scalar()
        )

        expiry_loss = (
            self.db.query(
                func.coalesce(
                    func.sum(
                        Batch.quantity * Batch.cost_price
                    ),
                    0,
                )
            )
            .filter(
                Batch.expiry_date < date.today()
            )
            .scalar()
        )

        return {
            "expired_batches": expired_batches,
            "expiry_loss": float(expiry_loss),
        }

    def get_margin_summary(self) -> dict:
        """
        Return gross profit and profit margin.

        Gross profit = sales revenue - cost of goods sold (COGS).
        COGS is summed from each sold line's batch cost_price.
        """

        revenue = (
            self.db.query(
                func.coalesce(func.sum(SaleItem.line_total), 0)
            )
            .scalar()
        )

        cogs = (
            self.db.query(
                func.coalesce(
                    func.sum(SaleItem.quantity * Batch.cost_price),
                    0,
                )
            )
            .join(Batch, Batch.id == SaleItem.batch_id)
            .scalar()
        )

        revenue = float(revenue)
        cogs = float(cogs)
        gross_profit = revenue - cogs
        profit_margin = (
            (gross_profit / revenue * 100)
            if revenue > 0
            else 0
        )

        return {
            "revenue": revenue,
            "cogs": cogs,
            "gross_profit": gross_profit,
            "profit_margin_percent": round(profit_margin, 2),
        }
