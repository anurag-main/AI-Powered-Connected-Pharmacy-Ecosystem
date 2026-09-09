"""Sales history over HTTP.

History is read-only, so the properties worth protecting are about ordering,
paging and honesty about what was charged:

  * newest first, with a total ordering so paging cannot repeat or skip a row
  * prices come from sale_items, never recomputed from today's MRP
  * a walk-in sale (no customer) still appears
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

LIST = "/api/v1/sales"


def sale_ids(body) -> list[int]:
    return [s["sale_id"] for s in body["sales"]]


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_saved_sales_appear_in_history(client, seeded_app_db):
    response = client.get(LIST)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert len(body["sales"]) >= 1


def test_history_is_newest_first(client, seeded_app_db):
    body = client.get(LIST, params={"limit": 50}).json()

    stamps = [(s["sold_at"], s["sale_id"]) for s in body["sales"]]
    assert stamps == sorted(stamps, reverse=True)


def test_a_row_carries_what_the_list_needs(client, seeded_app_db):
    sale = client.get(LIST, params={"limit": 1}).json()["sales"][0]

    assert set(sale) == {
        "sale_id",
        "sold_at",
        "total_amount",
        "item_count",
        "customer_name",
        "customer_phone",
    }
    assert sale["item_count"] >= 1


def test_line_items_are_not_in_the_list(client, seeded_app_db):
    """The list is one row per invoice; lines would multiply the payload."""

    sale = client.get(LIST, params={"limit": 1}).json()["sales"][0]

    assert "lines" not in sale


def test_total_counts_every_invoice_not_just_the_page(client, seeded_app_db):
    page = client.get(LIST, params={"limit": 1}).json()

    assert len(page["sales"]) == 1
    assert page["total"] >= len(page["sales"])


# ---------------------------------------------------------------------------
# Paging
# ---------------------------------------------------------------------------


def test_paging_does_not_repeat_or_skip(client, seeded_app_db):
    """The bug this catches: ordering by timestamp alone.

    Two sales in the same second are ordinary at a counter. Without the id
    tiebreak the database may order them differently between two queries, and a
    row then shows up on both pages or on neither.
    """

    everything = sale_ids(client.get(LIST, params={"limit": 50}).json())

    first = sale_ids(client.get(LIST, params={"limit": 2, "offset": 0}).json())
    second = sale_ids(client.get(LIST, params={"limit": 2, "offset": 2}).json())

    assert first + second == everything[:4]
    assert not set(first) & set(second)


def test_offset_past_the_end_is_empty_not_an_error(client, seeded_app_db):
    response = client.get(LIST, params={"limit": 5, "offset": 10_000})

    assert response.status_code == 200
    assert response.json()["sales"] == []


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": -1},
        {"offset": -1},
        {"limit": "all"},
    ],
)
def test_bad_paging_is_rejected(client, seeded_app_db, params):
    assert client.get(LIST, params=params).status_code == 422


def test_the_page_size_is_capped(client, seeded_app_db):
    """No caller can ask for every invoice ever written in one request."""

    assert client.get(LIST, params={"limit": 100}).status_code == 200
    assert client.get(LIST, params={"limit": 1000}).status_code == 422


# ---------------------------------------------------------------------------
# One invoice
# ---------------------------------------------------------------------------


def test_one_invoice_carries_its_lines(client, seeded_app_db):
    sale_id = client.get(LIST, params={"limit": 1}).json()["sales"][0]["sale_id"]

    response = client.get(f"{LIST}/{sale_id}")

    assert response.status_code == 200
    detail = response.json()
    assert detail["sale_id"] == sale_id
    assert len(detail["lines"]) == detail["item_count"]

    line = detail["lines"][0]
    assert set(line) == {
        "medicine_id",
        "medicine_name",
        "batch_number",
        "expiry_date",
        "quantity",
        "unit_price",
        "line_total",
    }
    assert line["medicine_name"]


def test_the_lines_add_up_to_the_invoice_total(client, seeded_app_db):
    sale_id = client.get(LIST, params={"limit": 1}).json()["sales"][0]["sale_id"]
    detail = client.get(f"{LIST}/{sale_id}").json()

    assert round(sum(l["line_total"] for l in detail["lines"]), 2) == round(
        detail["total_amount"], 2
    )


def test_prices_are_what_was_charged_not_todays_mrp(client, seeded_app_db):
    """A price change today must not rewrite what a customer paid last month.

    `sale_items.unit_price` is frozen at sale time. This moves the catalogue price
    and asserts the invoice does not follow it.
    """

    from app.models.medicine import Medicine

    sale_id = client.get(LIST, params={"limit": 1}).json()["sales"][0]["sale_id"]
    before = client.get(f"{LIST}/{sale_id}").json()
    line = before["lines"][0]

    medicine = seeded_app_db.get(Medicine, line["medicine_id"])
    medicine.mrp = float(medicine.mrp) + 500
    seeded_app_db.commit()

    after = client.get(f"{LIST}/{sale_id}").json()

    assert after["lines"][0]["unit_price"] == line["unit_price"]
    assert after["total_amount"] == before["total_amount"]


def test_a_missing_invoice_is_a_404(client, seeded_app_db):
    response = client.get(f"{LIST}/99999999")

    assert response.status_code == 404
    # The message names the id and nothing else — no table names, no SQL.
    assert "99999999" in response.json()["detail"]


def test_a_non_numeric_id_is_rejected(client, seeded_app_db):
    assert client.get(f"{LIST}/not-a-number").status_code == 422
