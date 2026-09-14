"""Custom exceptions raised by the pharmacy domain.

Convention:
- Every domain error inherits from PharmacyError.
- Routers catch these and translate to the right HTTP status code.
- Never raise built-in exceptions (ValueError, RuntimeError) from business logic.
"""


class PharmacyError(Exception):
    """Base class for every domain-level error in this app."""


class DuplicateMedicineError(PharmacyError):
    """Raised when a medicine with the same normalized name already exists.

    The router catches this and translates to HTTP 409 Conflict.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Medicine '{name}' already exists.")


class MedicineNotFoundError(PharmacyError):
    """Raised when a request names a medicine id that is not in the catalogue.

    The router translates this to HTTP 404. Goods receipt deliberately does NOT
    create the medicine for you: a receipt form that silently invents catalogue
    entries is how you end up with five spellings of the same tablet.
    """

    def __init__(self, medicine_id: int) -> None:
        self.medicine_id = medicine_id
        super().__init__(f"Medicine {medicine_id} not found.")


class SupplierNotFoundError(PharmacyError):
    """Raised when a request names a supplier id that does not exist.

    Only reachable when the client sends ``supplier_id``. Sending
    ``supplier_name`` creates the vendor instead, so this is genuinely a
    "you referenced something that is not there" error → HTTP 404.
    """

    def __init__(self, supplier_id: int) -> None:
        self.supplier_id = supplier_id
        super().__init__(f"Supplier {supplier_id} not found.")


class InvalidGoodsReceiptError(PharmacyError):
    """Raised when a receipt is well-formed JSON but not a legal delivery.

    Pydantic already rejects negative quantities and malformed dates. This covers
    the rules Pydantic cannot see because they need the database or the other
    fields: expiry in the past, cost above MRP, a purchase dated in the future,
    the same batch listed twice in one request.

    The router translates this to HTTP 422 — the request was understood and
    refused, not misunderstood.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class BatchConflictError(PharmacyError):
    """Raised when an incoming batch contradicts the batch already on the shelf.

    Same medicine, same batch number, but a different expiry date or a different
    cost price. One of the two records is wrong and this service cannot know
    which, so it refuses rather than silently overwriting a cost basis that
    profit reporting depends on. Router translates to HTTP 409 Conflict.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# Future exceptions to add as we hit them:
#   class StockNotAvailableError(PharmacyError):       # → HTTP 422
#   class ExpiredBatchError(PharmacyError):            # → HTTP 422
