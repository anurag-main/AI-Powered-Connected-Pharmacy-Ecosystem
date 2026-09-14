# Goods Receipt (Stock Intake)

> Last verified against the source, real MySQL and a real browser: **2026-09-14**.

The write path that lets stock enter the system.

---

## 1. Business problem

Before this feature, **stock in this system could only ever go down.**

Billing decremented batches. Expiry, inventory and reorder read them. Nothing in
the running application ever created one. Every batch in the database had been
written by a seed script, which meant the feature had been *demonstrated* but
never *built*.

A real shop running that code would have sold itself to zero within weeks, and
the Inventory Risk and Expiry Risk agents would have slowly gone blind — still
answering confidently, about a shop with no stock in it.

The gap was not obvious from the UI, because five screens all looked finished.
It was obvious from one query:

```
grep -rnE '@router\.(post|put|patch|delete)' app/routers/
```

`Batch` and `Purchase` appeared in **zero** routers.

---

## 2. What a goods receipt is

One supplier invoice arriving at the back door. It writes four tables, or none:

| Table | What it records |
|---|---|
| `suppliers` | who it came from (found or created) |
| `purchases` | the invoice header, with the server-computed total |
| `batches` | **the actual stock** — quantity, expiry, cost price |
| `purchase_items` | the frozen cost basis, per line |

The distinction that matters most: **a medicine is not stock.** `POST
/api/v1/medicines` creates a catalogue entry. It creates no units. Only this
feature does.

---

## 3. API contract

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/purchases` | Record a receipt. `201` |
| `GET` | `/api/v1/purchases?limit=` | Recent receipts, newest first. Bounded at 50 |
| `GET` | `/api/v1/purchases/suppliers` | Vendors, for the picker |
| `GET` | `/api/v1/purchases/{id}` | One receipt with its lines |

### Request

```json
{
  "supplier_name": "Medlife Distributors",
  "invoice_number": "INV-2026-114",
  "purchase_date": "2026-09-14",
  "lines": [
    { "medicine_id": 17, "batch_number": "GR-A",
      "expiry_date": "2027-06-30", "quantity": 100, "unit_cost": 12.50 }
  ]
}
```

Supplier is given by `supplier_id` **or** `supplier_name`, never both and never
neither. A name that is not on file creates the vendor; an id that is not on file
is a `404`.

**There is no `line_total` and no `total_amount` on the input.** A client that
wanted to record a ₹500 delivery as a ₹5 one has nowhere to say so. This mirrors
the rule billing already enforces: money is a server decision.

---

## 4. The rules, and why each exists

Checked in this order. Everything is validated **before** the transaction opens,
so a typo never costs row locks on `batches`.

| # | Rule | Status | Why |
|---|---|---|---|
| 1 | Exactly one supplier field | 422 | Neither is unattributable; both invites a request where the two disagree |
| 2 | `purchase_date` not in the future | 422 | Would file stock into a period that has not happened, breaking every purchase-trend window |
| 3 | No `(medicine, batch)` twice in one receipt | 422 | Ambiguous — double entry or two cartons? Refusing beats doubling someone's stock |
| 4 | Every medicine already in the catalogue | 404 | A receipt form that invents catalogue entries is how you get five spellings of Crocin |
| 5a | Expiry strictly in the future | 422 | Expired stock poisons FEFO and the expiry agent. Today counts as *not* future — it cannot be sold |
| 5b | `unit_cost` ≤ MRP | 422 | MRP is the legal maximum retail price, so wholesale is always below it. The cheapest possible catch for the misplaced decimal that would multiply recorded inventory value by 100 |
| 6 | Incoming batch must not contradict the shelf | 409 | See below |

`409` rather than `422` for rule 6 is deliberate. A 422 tells the pharmacist to
fix their typing; a 409 tells them to go and look at the physical carton. Those
are different actions.

---

## 5. Top-up vs. create

A batch number that already exists **for that medicine** is topped up, not
duplicated:

```
first receipt   GR-A  qty 100        -> batch row created, quantity 100
second receipt  GR-A  qty  60        -> SAME row, quantity 160
```

Two rows with the same batch number would both be valid to FEFO, both counted by
the inventory agent, and impossible to reconcile against one physical box.

Matching is **case-insensitive** on both batch number and supplier name.
`ab123` and `AB123` printed on one carton are one batch; "Sun Pharma" and
"sun pharma" are one vendor, and letting them split would divide every
purchase-trend report in three.

Batch numbers are unique **per medicine**, never globally — two manufacturers
using `A1` is normal.

### When a top-up is refused

If the existing batch has a different **expiry** or a different **cost price**,
the receipt is rejected with a `409`. There is no correct automatic merge:

* Averaging the cost would silently restate the value of stock already counted.
* Taking the newer expiry would extend the sellable life of tablets that do not
  have it.

Both are worse than an error message, because neither is visible afterwards.
Weighted-average costing is **not supported** — see §9.

---

## 6. Architecture

```
pages/receive.jsx
  └ useGoodsReceipt              3 reference loads + 1 write
      └ lib/api/purchases.js     toReceiptPayload()  (types only, no arithmetic)
          └ lib/api/client.js    fetch, X-Request-ID
              └ routers/purchases.py        exception -> status code, nothing else
                  └ GoodsReceiptService     ALL rules, ONE commit boundary
                      └ PurchaseRepository  SQL. flush()es, never commit()s
                          └ MySQL
```

### The commit boundary

Every other write repository in this project commits inside its own `add()`.
That is fine for a single-table insert and fatal here: a commit partway through
would leave a purchase header pointing at batches that were never created.

So `PurchaseRepository` **never** calls `commit()`. It `flush()`es where it needs
a generated id, and the service owns the single boundary. This is the Unit of
Work pattern that `sqlalchemy_medicine_repository.py`'s docstring predicted would
be needed.

> `flush()` sends the INSERT and returns the auto-increment id, but the
> transaction is still open and still reversible. `commit()` is the point of no
> return.

**Not** `with db.begin():`, which is what `persist_sale.py` uses. That form
requires a session with no transaction open, and works there because the node
opens its own `SessionLocal()` and writes immediately. Here the session arrives
from `Depends(get_db)` and validation has already read from it — implicitly
beginning a transaction — so `begin()` would raise *"a transaction is already
begun"*. The boundary is explicit instead: one `commit()` at the end, `rollback()`
on any exception.

---

## 7. Frontend

`/receive`, Pages Router, JavaScript.

**No business logic.** The page checks that fields are *filled in* and nothing
else. Whether the expiry is far enough away, whether the cost is under MRP,
whether the batch contradicts the shelf — all decided by the service and shown as
it came back.

### No running total on the form

Deliberate. A preview total would be a second implementation of money arithmetic
living in a browser, and the moment it disagreed with the server — a rounding
rule, a rejected line, a batch top-up — the pharmacist would believe the one on
the screen in front of them.

The total appears **once**, after the receipt is recorded, and it is the figure
that was actually written to the database. The panel says so, and invites a check
against the paper invoice.

### Domain errors are surfaced verbatim

This is the one module that deviates from `client.js`'s rule of replacing server
`detail` with generic wording, and the deviation is bounded:

* Only `404` / `409` / `422`. A `500`'s detail is still replaced, because that is
  exactly the text that leaks internals.
* Only when `detail` is a **string**. FastAPI returns an *array* for Pydantic
  validation errors, and rendering it would print `[object Object]`.

It is safe because these messages are authored in `goods_receipt_service.py`, not
produced by SQLAlchemy — and a backend test asserts they contain no SQL,
traceback, driver name or credential.

### The double-submit guard

Checked inside the submit function via a ref, not only by disabling the button.

On a read-only page a double click wastes a query. Here it would create the
delivery twice — and it would **not fail loudly**, because the second request is
perfectly valid: same batch, same expiry, same cost, so the service tops it up
and the shop's stock is silently doubled. A `disabled` attribute is a hint to a
mouse, not a guarantee.

On failure, **nothing the pharmacist typed is cleared.** Wiping a ten-line
invoice to punish one typo is how people stop using a system.

---

## 8. Testing

| Tier | File | Count |
|---|---|---|
| Unit | `tests/unit/test_goods_receipt_service.py` | 28 |
| Integration | `tests/integration/test_purchases_api.py` | 18 |
| Frontend | `pharmacy-frontend/tests/receive-page.test.jsx` | 30 |

Two are worth calling out.

**The race test.** The conflict check runs twice — once before the transaction,
once inside it. The pre-flight catches every ordinary case, so the in-transaction
re-check only fires when another request created the batch in between. That is
the one path where a conflict is found *after* the header was inserted, and the
only way to reach it in a test is to patch `find_batch` to report a clear shelf
the first time and the conflict every time after. Without it, a race would
silently top up a batch whose cost basis disagrees with the invoice.

**The route-ordering test.** `/suppliers` must be declared above `/{purchase_id}`
or FastAPI parses `"suppliers"` as an int and returns 422. The test exists to
catch the edit that reorders them.

Frontend tests mock at the `fetch` boundary, so `toReceiptPayload` is real code
under test — which is where a wrong request body would actually come from. They
assert the request built, the response displayed, and the failure paths; they do
**not** assert whether a receipt is valid, because that would be asserting a copy
of the backend's rules.

---

## 9. Known limitations

1. **No weighted-average costing.** A second delivery of the same batch at a
   different price is refused rather than averaged. Correct for now — silently
   restating the value of counted stock is worse — but a real pharmacy does
   receive the same batch at two prices, and this will need a proper costing
   method eventually.
2. **No edit or delete.** A receipt entered wrongly cannot be corrected through
   the API. In accounting terms the right fix is a reversing entry, not an edit,
   and neither exists yet.
3. **No purchase returns.** The `returns` model exists and this feature does not
   write to it.
4. **No authentication.** `/receive` writes stock and shows cost prices. It is
   open, like every other screen.
5. **`batch_created` is always `false` on the detail endpoint.** Whether a batch
   row was new at the moment it was written is not recorded anywhere. Reporting
   `true` would be inventing a fact; it is reported `false` and documented rather
   than hidden.
6. **No supplier management.** Vendors can be created by typing a new name, but
   not renamed, merged or given a phone number after the fact.
7. **No barcode or invoice scanning.** Every line is typed.

---

## 10. Recommended next step

**Authentication**, for the reason in §9.4 — this screen writes stock and shows
cost price, which makes it the first genuinely dangerous page in the system, not
merely the most sensitive to read.

After that, **purchase returns**, which closes the loop on the stock lifecycle:
stock can now come in (here), go out (billing), and expire (expiry agent), but
cannot go back to the supplier.
