"""End-to-end HTTP smoke test for the billing endpoint (Step 3.10).

Uses FastAPI's TestClient — runs the REAL app in-process: real router,
real BillingService, real compiled graph, real OpenAI call, real MySQL write.
No separate uvicorn server needed (avoids the background-process hang).

This is a TRUE end-to-end test: HTTP request in → invoice in the DB → HTTP
response out.

WARNING: actually writes sales to MySQL and decrements batch stock on the
happy-path test. Re-runs keep decrementing — watch your seeded batch qty.

Run with:
    cd c:\\ai-pharmacy-ecosystem\\pharmacy-core-backend
    .\\venv\\Scripts\\Activate.ps1
    python -u -m scripts.http_smoke_billing
"""
import json

from fastapi.testclient import TestClient

from app.core.database import SessionLocal
from app.main import app
from app.repositories.sqlalchemy_medicine_repository import SQLAlchemyMedicineRepository

client = TestClient(app)


def _print_response(label: str, resp) -> None:
    print(f"\n========== {label} ==========")
    print(f"HTTP {resp.status_code}")
    try:
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except Exception:  # noqa: BLE001
        print(resp.text)


def main() -> int:
    # Discover a real medicine name so the happy-path test matches your data.
    with SessionLocal() as db:
        meds = SQLAlchemyMedicineRepository(db).list_all()
    if not meds:
        print("!! No medicines in DB. Seed one first.")
        return 1
    known = meds[0].name
    print(f"Using known medicine: {known!r}")

    # ---- Test 1: happy path — should create a sale (201) ----
    r1 = client.post(
        "/api/v1/billing/sale",
        json={"pharmacist_input": f"1 strip {known} for Anurag 9876543210"},
    )
    _print_response("Test 1: valid order (expect 201 + sale_id)", r1)
    assert r1.status_code == 201, f"expected 201, got {r1.status_code}"
    assert r1.json()["sale_id"] is not None, "expected a sale_id"

    # ---- Test 2: unknown medicine — should fail to bill (422) ----
    r2 = client.post(
        "/api/v1/billing/sale",
        json={"pharmacist_input": "5 strips Unicorn Dust 999mg for Ghost 1112223334"},
    )
    _print_response("Test 2: unknown medicine (expect 422 + errors)", r2)
    assert r2.status_code == 422, f"expected 422, got {r2.status_code}"

    # ---- Test 3: empty input — Pydantic rejects before the graph runs (422) ----
    r3 = client.post("/api/v1/billing/sale", json={"pharmacist_input": ""})
    _print_response("Test 3: empty input (expect 422 from validation)", r3)
    assert r3.status_code == 422, f"expected 422, got {r3.status_code}"

    # ---- Test 4: malformed body — missing the required field (422) ----
    r4 = client.post("/api/v1/billing/sale", json={"wrong_field": "oops"})
    _print_response("Test 4: missing field (expect 422 from validation)", r4)
    assert r4.status_code == 422, f"expected 422, got {r4.status_code}"

    print("\n\nALL HTTP TESTS PASSED -- the billing endpoint is live end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
