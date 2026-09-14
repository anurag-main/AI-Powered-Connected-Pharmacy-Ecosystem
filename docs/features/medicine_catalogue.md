# Medicine Catalogue

> Last verified against the source, real MySQL and a real browser: **2026-09-14**.

The catalogue of what the shop sells. Names and prices — **not** stock.

---

## 1. The distinction that matters

A medicine row is a **name**, not a quantity.

```
POST /api/v1/medicines   -> "we sell Shelcal 500"   ZERO units exist
POST /api/v1/purchases   -> "200 units arrived"     stock now exists
```

A medicine with no batch has zero quantity. The inventory query's
`HAVING stock_quantity > 0` will not even return it, and no expiry or reorder
report will mention it. This trips people up often enough that the page itself
says so, above the table and again inside the form.

See [`goods_receipt.md`](goods_receipt.md) for the second step.

---

## 2. What existed, and what was missing

`POST /api/v1/medicines` has existed since Phase 1. What did not exist was any
way to reach it: no `lib/api/medicines.js`, no form, no button. The `/medicines`
page was read-only, so in practice the catalogue was as unwritable as stock was.

This feature is the form in front of the endpoint. **No backend change was
needed** — the endpoint, its validation and its 409 were already correct.

---

## 3. Contract

```json
POST /api/v1/medicines        -> 201
{
  "name": "Shelcal 500",
  "mrp": 145.00,
  "hsn_code": "30049099",
  "manufacturer": "Torrent"
}
```

| Field | Rule |
|---|---|
| `name` | 1–200 chars, required |
| `mrp` | > 0, required |
| `hsn_code` | **exactly 8 characters**, required |
| `manufacturer` | optional, ≤ 200 chars |

**409** when the normalised name already exists. The server lowercases and
normalises before comparing, so "Shelcal 500" and "shelcal 500" are one medicine
— which is the same de-duplication rule suppliers get in goods receipt.

---

## 4. Frontend

`src/components/medicines/AddMedicineForm.jsx`, opened from `/medicines`.

An **inline panel, not a modal.** There is no dialog primitive in this project,
and adding Radix plus a focus trap for one four-field form is more machinery than
the job needs.

### HSN is deliberately not pre-filled

`30049099` is the most common value in the catalogue and pre-filling it would
save typing on most entries. It is left **blank** anyway.

It is a GST tax code. A default that is right most of the time is wrong some of
the time, *silently*, and the wrongness surfaces at filing rather than at entry.
The form shows the common value as a hint below the field instead, so using it is
a choice rather than an assumption.

### Error handling

Same bounded deviation from `client.js` as `purchases.js`, for the same reason —
the useful message here is specific and authored by us:

* **409** — `detail` shown verbatim ("Medicine 'Dolo 650' already exists.").
  The shared client would have said "Something went wrong", which tells the
  pharmacist nothing about the duplicate they just tried to create.
* **422** — Pydantic returns an **array** of field objects. Rendering it would
  print `[object Object]`, so only the first is summarised:
  `hsn code: String should have at least 8 characters`.
  Only the first, because listing five field errors reads like a stack trace and
  the form already carries inline hints.
* **500** — suppressed. That is the text that leaks internals.

### After a successful create

The table is **re-read from the server**, not appended to optimistically. The id
and timestamps come from MySQL anyway, and a row the table cannot prove is there
is a row that might not be.

Everything typed survives a failure. The usual failure is a duplicate name or a
wrong HSN length, and clearing the form to punish that is how people stop using a
system.

---

## 5. Testing

`pharmacy-frontend/tests/medicines-page.test.jsx` — 22 tests, mocking at the
`fetch` boundary so `lib/api/medicines.js` is real code under test.

Covered: the table, the open/close behaviour, the completeness gate (including
that a 7-digit HSN keeps submit disabled), the request body (`mrp` sent as a
**number**, manufacturer omitted rather than sent as `""`, name trimmed), the
double-submit guard, the refresh-after-create, and all five failure paths
including the leak check.

Not covered, deliberately: whether a name is a duplicate. That is a database
question, answered by the server, and a copy of the rule in the browser would be
a second definition to keep in sync.

---

## 6. Known limitations

1. **No edit or delete.** A medicine typed wrongly cannot be corrected through
   the UI. The endpoints do not exist either — `medicines.py` is POST and two
   GETs.
2. **No search or pagination.** The table renders every row. At 100 medicines
   that is fine; at 5,000 it will not be.
3. **No HSN validation beyond length.** Eight characters of anything passes.
   A real check would need the GST HSN list.
4. **No duplicate warning before submit.** The name is checked only by the server
   on submit, so a duplicate costs a round trip. Acceptable — the alternative is
   a lookup on every keystroke.
5. **No authentication.** Like every other screen.

---

## 7. Recommended next step

**Edit and deactivate.** Creating is now possible and correcting is not, which is
a worse asymmetry than having neither — a typo in a medicine name is permanent
and will follow every invoice that references it. Deactivate rather than delete:
`ON DELETE RESTRICT` on batches and sale items is there to protect the audit
trail, and removing a medicine that has ever been sold should not be possible.
