"""HTTP layer for sales history. Read-only.

Sales are created by POST /api/v1/billing/confirm. Nothing here writes — an invoice
is an audit record, and the way to correct one is a return, not an edit.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.sales_repository import SalesRepository
from app.schemas.sales import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, SaleDetailOut, SalesPageOut
from app.services.sales_service import SalesService

router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


def get_sales_service(db: Session = Depends(get_db)) -> SalesService:
    """Per-request service over a per-request session."""

    return SalesService(repository=SalesRepository(db))


@router.get(
    "",
    response_model=SalesPageOut,
    status_code=status.HTTP_200_OK,
    summary="List saved invoices, newest first",
)
def list_sales(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    service: SalesService = Depends(get_sales_service),
) -> SalesPageOut:
    """A page of sales history.

    `limit` is capped so no caller can ask for every invoice ever written in one
    request once this table has years in it.
    """

    return service.list_sales(limit=limit, offset=offset)


@router.get(
    "/{sale_id}",
    response_model=SaleDetailOut,
    status_code=status.HTTP_200_OK,
    summary="One invoice with its line items",
)
def get_sale(
    sale_id: int,
    service: SalesService = Depends(get_sales_service),
) -> SaleDetailOut:
    """One invoice, priced exactly as it was charged at the time."""

    sale = service.get_sale(sale_id)
    if sale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No sale with id {sale_id}",
        )
    return sale
