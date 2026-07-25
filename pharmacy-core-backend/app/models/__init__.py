"""SQLAlchemy ORM models package.

Importing this package imports every model module, so all tables register
with Base.metadata. Alembic relies on this in env.py to discover tables.
"""
from app.models.batch import Batch  # noqa: F401
from app.models.customer import Customer  # noqa: F401
from app.models.medicine import Medicine  # noqa: F401
from app.models.purchase import Purchase  # noqa: F401
from app.models.purchase_item import PurchaseItem  # noqa: F401
from app.models.reorder_request import ReorderRequest  # noqa: F401
from app.models.returns import Return  # noqa: F401
from app.models.sale import Sale  # noqa: F401
from app.models.sale_item import SaleItem  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401

__all__ = [
    "Batch",
    "Customer",
    "Medicine",
    "Purchase",
    "PurchaseItem",
    "ReorderRequest",
    "Return",
    "Sale",
    "SaleItem",
    "Supplier",
]
