"""HTTP smoke test for the quote -> confirm billing flow (frontend's two calls).

Runs the real app in-process (TestClient): router -> service -> graphs -> OpenAI
-> MySQL. Proves the preview/finalize split the frontend depends on.

WARNING: the confirm test writes a real sale and decrements stock on each run.

Run:
    cd c:\\ai-pharmacy-ecosystem\\pharmacy-core-backend
    .\\venv\\Scripts\\Activate.ps1
    python -u -m scripts.http_smoke_quote_confirm
"""
import json

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.repositories.sqlalchemy_batch_repository import SQLAlchemyBatchRepository

client = TestClient(app)


def _show(label, resp):
    print(f"\n========== {label} ==========")
    print(f"HTTP {resp.status_code}")
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))


def main() -> int:
    # ---- Test 1: QUOTE (preview, no save) ----
    r1 = client.post(
        "/api/v1/billing/quote",
        json={"pharmacist_input": "1 Paracetamol 500mg and 2 Crocin 500mg for Anurag 9876543210"},
    )
    _show("Test 1: /quote (expect 200, priced items, sale_id null)", r1)
    assert r1.status_code == 200, f"expected 200, got {r1.status_code}"
    quote = r1.json()
    assert quote["sale_id"] is None, "quote must NOT create a sale"
    assert len(quote["items"]) >= 1, "expected priced items"

    # Capture stock-before for the batches we're about to buy.
    before = {}
    with SessionLocal() as db:
        repo = SQLAlchemyBatchRepository(db)
        for it in quote["items"]:
            before[it["batch_id"]] = repo.get_by_id(it["batch_id"]).quantity

    # ---- Test 2: CONFIRM (finalize the quoted items) ----
    confirm_body = {
        "items": [
            {
                "name": it["name"],
                "quantity": it["quantity"],
                "unit": it["unit"],
                "medicine_id": it["medicine_id"],
                "batch_id": it["batch_id"],
                "batch_number": it["batch_number"],
                "expiry_date": it["expiry_date"],
            }
            for it in quote["items"]
        ],
        "customer_name": quote["customer_name"],
        "customer_phone": quote["customer_phone"],
    }
    r2 = client.post("/api/v1/billing/confirm", json=confirm_body)
    _show("Test 2: /confirm (expect 201 + sale_id)", r2)
    assert r2.status_code == 201, f"expected 201, got {r2.status_code}"
    confirmed = r2.json()
    assert confirmed["sale_id"] is not None, "confirm must create a sale"

    # ---- Verify stock decremented by exactly the quantities ----
    print("\n--- stock check ---")
    with SessionLocal() as db:
        repo = SQLAlchemyBatchRepository(db)
        for it in quote["items"]:
            after = repo.get_by_id(it["batch_id"]).quantity
            expected = before[it["batch_id"]] - it["quantity"]
            ok = "OK" if after == expected else "MISMATCH"
            print(f"  batch {it['batch_id']}: {before[it['batch_id']]} -> {after} (expected {expected}) [{ok}]")
            assert after == expected, "stock not decremented correctly"

    # ---- Verify server-side repricing matches quote (prices came from DB, not client) ----
    print("\n--- price check (server recomputed) ---")
    q_total = quote["total_amount"]
    c_total = confirmed["total_amount"]
    print(f"  quote total={q_total}  confirm total={c_total}")
    assert q_total == c_total, "confirm total should match quote (same DB MRP)"

    # ---- Test 3: QUOTE unknown medicine (200 with errors, empty items) ----
    r3 = client.post(
        "/api/v1/billing/quote",
        json={"pharmacist_input": "5 Unicorn Dust 999mg"},
    )
    _show("Test 3: /quote unknown medicine (expect 200, errors, no items)", r3)
    assert r3.status_code == 200, f"expected 200, got {r3.status_code}"
    assert r3.json()["sale_id"] is None
    assert len(r3.json()["errors"]) >= 1

    print("\n\nALL QUOTE/CONFIRM TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
