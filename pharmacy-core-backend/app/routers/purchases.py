"""HTTP layer for the Goods Receipt (stock intake) domain.

This is the write path the system was missing: the only way, outside a seed
script, for stock to enter the database. Everything else that touches batches
either reads them (expiry, inventory, reorder) or decrements them (billing).

The router's whole job is translation. It maps domain exceptions to status codes
and nothing else -- no rules, no arithmetic, no SQL. Each mapping is a deliberate
statement about whose fault the request was:

    MedicineNotFoundError    404  you referenced a catalogue entry that is absent
    SupplierNotFoundError    404  you referenced a vendor that is absent
    InvalidGoodsReceiptError 422  understood, and refused on a domain rule
    BatchConflictError       409  contradicts a record already on the shelf

422 rather than 400 for the domain rules keeps them consistent with the 422s
Pydantic already returns for a malformed body, so a client has one error shape to
handle for "your request was wrong" and reserves 500 for "we were wrong".
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.exceptions import (
    BatchConflictError,
    InvalidGoodsReceiptError,
    MedicineNotFoundError,
    SupplierNotFoundError,
)
from app.schemas.purchase import (
    GoodsReceiptCreate,
    GoodsReceiptOut,
    PurchaseSummary,
    SupplierOut,
)
from app.services.goods_receipt_service import GoodsReceiptService

router = APIRouter(prefix="/api/v1/purchases", tags=["purchases"])


def get_service(db: Session = Depends(get_db)) -> GoodsReceiptService:
    """Per-request service over the request-scoped session."""
    return GoodsReceiptService(db)


@router.post(
    "",
    response_model=GoodsReceiptOut,
    status_code=status.HTTP_201_CREATED,
    summary="Record a goods receipt (stock arriving from a supplier)",
)
def record_receipt(
    payload: GoodsReceiptCreate,
    service: GoodsReceiptService = Depends(get_service),
) -> GoodsReceiptOut:
    """Record one supplier invoice: supplier, header, batches and lines, atomically.

    The response carries the totals the SERVER computed. Nothing in the request
    body can influence them -- there is no field to do it with.
    """
    try:
        return service.record_receipt(payload)
    except (MedicineNotFoundError, SupplierNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BatchConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidGoodsReceiptError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )


@router.get(
    "",
    response_model=list[PurchaseSummary],
    summary="Recent goods receipts, newest first",
)
def list_receipts(
    limit: int = Query(default=20, ge=1, le=50),
    service: GoodsReceiptService = Depends(get_service),
) -> list[PurchaseSummary]:
    """The recent-activity list. Bounded by design -- this is not an archive."""
    return service.recent_receipts(limit=limit)


@router.get(
    "/suppliers",
    response_model=list[SupplierOut],
    summary="Every supplier, for the receipt form picker",
)
def list_suppliers(
    service: GoodsReceiptService = Depends(get_service),
) -> list[SupplierOut]:
    """Declared BEFORE ``/{purchase_id}``.

    FastAPI matches routes in declaration order. With the parameterised route
    first, a GET of ``/suppliers`` would try to parse "suppliers" as an int and
    return 422 instead of the list -- a genuinely confusing bug to chase.
    """
    return service.list_suppliers()


@router.get(
    "/{purchase_id}",
    response_model=GoodsReceiptOut,
    summary="One recorded receipt with its lines",
)
def get_receipt(
    purchase_id: int,
    service: GoodsReceiptService = Depends(get_service),
) -> GoodsReceiptOut:
    """Return the receipt with this id, or 404."""
    result = service.receipt_detail(purchase_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Purchase {purchase_id} not found",
        )
    return result
