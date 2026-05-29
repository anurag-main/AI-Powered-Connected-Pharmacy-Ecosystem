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


# Future exceptions to add as we hit them (Phase 2+):
#   class StockNotAvailableError(PharmacyError):       # → HTTP 422
#   class ExpiredBatchError(PharmacyError):            # → HTTP 422
#   class MedicineNotFoundError(PharmacyError):        # → HTTP 404
