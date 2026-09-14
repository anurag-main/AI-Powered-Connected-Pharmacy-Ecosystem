"""Integration tests for the goods receipt API.

These go through the real router, the real service and a real database session.
What they add over the unit tests is the part the unit tests cannot see: whether
each domain error reaches the client as the right STATUS CODE, and whether the
route ordering actually works.

Status codes are asserted deliberately rather than incidentally. A client cannot
tell "you sent a medicine that does not exist" (fix your request) from "the shelf
disagrees with your invoice" (go and look at the carton) unless the codes differ,
and a 500 for either would send someone hunting a server bug that is not there.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time_range import today
from app.models.batch import Batch
from app.models.medicine import Medicine
from app.models.purchase import Purchase
from app.models.supplier import Supplier

ENDPOINT = "/api/v1/purchases"


@pytest.fixture
def catalogue(db_session):
    """Two medicines and one supplier, committed so the request sees them."""
    crocin = Medicine(
        name="Crocin 500",
        normalized_name="crocin 500",
        mrp=Decimal("20.00"),
        hsn_code="30049099",
        manufacturer="GSK",
    )
    dolo = Medicine(
        name="Dolo 650",
        normalized_name="dolo 650",
        mrp=Decimal("30.00"),
        hsn_code="30049099",
        manufacturer="Micro Labs",
    )
    supplier = Supplier(name="Sun Pharma", phone="022000000")
    db_session.add_all([crocin, dolo, supplier])
    db_session.commit()
    return {"crocin": crocin.id, "dolo": dolo.id, "supplier": supplier.id}


def body(catalogue, **overrides) -> dict:
    payload = {
        "supplier_name": "Sun Pharma",
        "lines": [
            {
                "medicine_id": catalogue["crocin"],
                "batch_number": "B-001",
                "expiry_date": (today() + timedelta(days=365)).isoformat(),
                "quantity": 100,
                "unit_cost": 10.00,
            }
        ],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Success
# ---------------------------------------------------------------------------


def test_post_returns_201_and_the_recorded_receipt(client, catalogue):
    response = client.post(ENDPOINT, json=body(catalogue))

    assert response.status_code == 201
    data = response.json()
    assert data["total_amount"] == 1000.00
    assert data["total_units"] == 100
    assert data["lines"][0]["batch_created"] is True
    assert data["lines"][0]["medicine_name"] == "Crocin 500"


def test_stock_actually_exists_afterwards(client, catalogue, db_session):
    """The point of the whole feature: a batch is on the shelf that was not before."""
    assert db_session.scalar(select(func.count()).select_from(Batch)) == 0

    client.post(ENDPOINT, json=body(catalogue))

    batch = db_session.scalars(select(Batch)).one()
    assert batch.quantity == 100


def test_response_carries_a_request_id(client, catalogue):
    """Every response is correlatable back to a line in the log."""
    response = client.post(ENDPOINT, json=body(catalogue))
    assert response.headers.get("X-Request-ID")


# ---------------------------------------------------------------------------
# Error mapping -- the reason these tests exist
# ---------------------------------------------------------------------------


def test_unknown_medicine_is_404(client, catalogue):
    payload = body(catalogue)
    payload["lines"][0]["medicine_id"] = 999_999
    assert client.post(ENDPOINT, json=payload).status_code == 404


def test_unknown_supplier_id_is_404(client, catalogue):
    payload = body(catalogue, supplier_name=None, supplier_id=999_999)
    assert client.post(ENDPOINT, json=payload).status_code == 404


def test_expired_stock_is_422(client, catalogue):
    payload = body(catalogue)
    payload["lines"][0]["expiry_date"] = (today() - timedelta(days=1)).isoformat()

    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 422
    assert "not in the future" in response.json()["detail"]


def test_cost_above_mrp_is_422(client, catalogue):
    payload = body(catalogue)
    payload["lines"][0]["unit_cost"] = 5000.00

    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 422
    assert "MRP" in response.json()["detail"]


def test_batch_conflict_is_409_not_422(client, catalogue):
    """409 says "the shelf disagrees with you", which is a different action.

    A 422 would tell the pharmacist to fix their typing. A 409 tells them to go
    and look at the physical carton, which is what this case actually requires.
    """
    client.post(ENDPOINT, json=body(catalogue))

    payload = body(catalogue)
    payload["lines"][0]["unit_cost"] = 12.00

    response = client.post(ENDPOINT, json=payload)
    assert response.status_code == 409


def test_missing_supplier_is_422(client, catalogue):
    payload = body(catalogue, supplier_name=None)
    assert client.post(ENDPOINT, json=payload).status_code == 422


def test_empty_lines_is_422_from_pydantic(client, catalogue):
    assert client.post(ENDPOINT, json=body(catalogue, lines=[])).status_code == 422


def test_negative_quantity_is_422_from_pydantic(client, catalogue):
    payload = body(catalogue)
    payload["lines"][0]["quantity"] = -5
    assert client.post(ENDPOINT, json=payload).status_code == 422


def test_a_rejected_receipt_leaves_no_trace(client, catalogue, db_session):
    """The failure path must not half-write anything, over HTTP as well."""
    payload = body(catalogue)
    payload["lines"].append(
        {
            "medicine_id": catalogue["dolo"],
            "batch_number": "BAD",
            "expiry_date": (today() - timedelta(days=1)).isoformat(),
            "quantity": 10,
            "unit_cost": 10.00,
        }
    )

    assert client.post(ENDPOINT, json=payload).status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Batch)) == 0
    assert db_session.scalar(select(func.count()).select_from(Purchase)) == 0


def test_error_bodies_do_not_leak_internals(client, catalogue):
    """A refused receipt explains the rule, never the plumbing."""
    payload = body(catalogue)
    payload["lines"][0]["expiry_date"] = (today() - timedelta(days=1)).isoformat()

    detail = client.post(ENDPOINT, json=payload).json()["detail"].lower()
    for leak in ("select ", "traceback", "sqlalchemy", "pymysql", "password"):
        assert leak not in detail


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


def test_suppliers_route_is_not_shadowed_by_the_id_route(client, catalogue):
    """``/suppliers`` must not be parsed as a ``purchase_id``.

    FastAPI matches in declaration order, so this passing depends entirely on
    ``/suppliers`` being declared above ``/{purchase_id}`` in the router. Moving
    it would turn this into a 422 and the test exists to catch that edit.
    """
    response = client.get(f"{ENDPOINT}/suppliers")

    assert response.status_code == 200
    assert [s["name"] for s in response.json()] == ["Sun Pharma"]


def test_list_returns_newest_first(client, catalogue):
    first = client.post(ENDPOINT, json=body(catalogue)).json()

    second_payload = body(catalogue)
    second_payload["lines"][0]["batch_number"] = "B-002"
    second = client.post(ENDPOINT, json=second_payload).json()

    rows = client.get(ENDPOINT, params={"limit": 10}).json()
    assert [r["purchase_id"] for r in rows] == [
        second["purchase_id"],
        first["purchase_id"],
    ]


def test_list_limit_is_bounded_by_the_router(client, catalogue):
    """Over the cap is a 422 from Query(le=50), not a silent full-table read."""
    assert client.get(ENDPOINT, params={"limit": 10_000}).status_code == 422


def test_detail_returns_the_lines(client, catalogue):
    created = client.post(ENDPOINT, json=body(catalogue)).json()

    response = client.get(f"{ENDPOINT}/{created['purchase_id']}")
    assert response.status_code == 200
    assert response.json()["lines"][0]["batch_number"] == "B-001"


def test_detail_of_a_missing_id_is_404(client, catalogue):
    assert client.get(f"{ENDPOINT}/999999").status_code == 404
