"""Custom exceptions raised by the pharmacy domain.

Convention:
- Every domain error inherits from PharmacyError.
- Routers catch these and translate to the right HTTP status code.
- Never raise built-in exceptions (ValueError, RuntimeError) from business logic.
"""


class PharmacyError(Exception):
    """Base class for every domain-level error in this app."""


# YOUR JOB (step 1.5 onwards): define specific exceptions as we hit them, e.g.
#   class DuplicateMedicineError(PharmacyError):
#       """Raised when a medicine with the same normalized name already exists."""
#
#   class StockNotAvailableError(PharmacyError):
#       """Raised when requested quantity exceeds available stock."""
#
#   class ExpiredBatchError(PharmacyError):
#       """Raised when attempting to sell from an expired batch."""
