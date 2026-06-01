# Phase 3 / Step 3.6 — In Plain Words

> **What we just built:** 3 new database tables — `customers`, `sales`, `sale_items` — plus the migration that creates them in MySQL.
>
> **Why we needed it:** Up to now, our LangGraph nodes can extract, look up, pick batches, and compute prices — but they have **nowhere to write the result**. These 3 tables are the home for every sale we'll ever record.

---

## 1. Why we do this (the whole step)

Imagine you've cooked a meal. You have the ingredients (medicine, batch), the recipe (the math nodes), and you know the price. But you have **no plate to serve it on**.

The 3 new tables are the plates.

- **customers** = the people who buy
- **sales** = each shopping bill (the "header" of an invoice)
- **sale_items** = the rows on each bill (the "lines")

Without these tables, all the work the previous nodes did would just **vanish at the end of every request**.

---

## 2. The "header + lines" pattern

Think of a restaurant bill:

```
========================================
   Table #5     Server: Riya     2:30 PM     ← HEADER (one)
========================================
   1  Veg Pizza         ₹250                  ← LINE
   2  Cold Coffee       ₹120 each = ₹240     ← LINE
   1  Brownie           ₹80                   ← LINE
----------------------------------------
                 TOTAL  ₹570                  ← total on the header
========================================
```

There is **ONE header** (table number, server, time, grand total).
There are **MANY lines** (one row per dish, with its quantity and price).

You DON'T write the table number on every line. You DON'T write the grand total on every line. The header holds the "shared" info; the lines hold the "repeated" info.

In our code:

| Restaurant bill | Pharmacy code |
|---|---|
| Bill header | `Sale` row |
| Lines | `SaleItem` rows |
| "Same bill" connection | `sale_items.sale_id` = `sales.id` |

This pattern appears EVERYWHERE in business apps: orders + order_lines, invoices + invoice_items, journals + journal_entries, receipts + receipt_items. **Learn it once, recognize it forever.**

---

## 3. Foreign keys + relationships

A **foreign key** is just "I am pointing to another row".

Like an address book entry that says *"Mom's address — see entry #5"*. The address itself isn't repeated. The pointer is the foreign key.

In our code:

```
sale_items
├── id = 1
├── sale_id = 42         ← "I belong to Sale #42"
├── medicine_id = 5       ← "I am about Medicine #5 (Crocin)"
├── batch_id = 6          ← "I came out of Batch #6 (SEED-EARLY)"
├── quantity = 2
├── unit_price = 25.50
└── line_total = 51.00
```

Three foreign keys = three pointers to three other tables.

### What `ON DELETE …` rules mean

A foreign key needs a rule for: *"what happens if the row I point to disappears?"*

| Rule | Plain words | Example we use it for |
|---|---|---|
| **CASCADE** | "I die with my parent." | `sale_items.sale_id` — if you delete a Sale, its lines die with it (lines without a header are nonsense) |
| **RESTRICT** | "Don't you dare delete that — I'm still here." | `sale_items.medicine_id` — refuses to delete a Medicine that has sale history (keeps audit trail safe) |
| **SET NULL** | "Wipe my pointer, but I survive." | `sales.customer_id` — if a customer is deleted, the sale row stays but customer link clears |

We picked each rule deliberately. **They're not interchangeable** — getting them wrong corrupts audit history.

---

## 4. Why we DUPLICATE (the "frozen price" pattern)

A real scenario:

> 🛒 **Yesterday** you bought a chocolate for ₹10.
> 💰 **Today** the shopkeeper raised the price to ₹15.
> 📜 **Should yesterday's bill change to ₹15?** NO. It should still say ₹10.

If our code computed the price by reading `Medicine.mrp` LIVE every time someone looks at an old bill — that bill would **silently change as MRP changes**. That's wrong, and tax law forbids it.

### The fix: freeze the price at sale time

`sale_items.unit_price` and `sale_items.line_total` are **stored, not computed**. We write the actual price the customer paid into those columns at sale time. Next year, even if MRP doubles, those rows still show what was charged.

### "But that's duplication?"

Yes. And it's CORRECT here.

Normalization rules say "don't store the same data twice". But there's an exception called **denormalization for audit/snapshot needs**. Money math is the textbook example.

We **denormalize** `unit_price` into `sale_items` for two reasons:

1. **Historical truth** — what the customer paid is not the same as what MRP is today
2. **Performance** — totaling reports doesn't need to JOIN with `medicines` every time

This is interview gold. *"Why does sale_items have a unit_price when Medicine already has mrp?"* — answer: "It's the frozen price pattern — required for audit trails and historic reporting."

---

## 5. Alembic autogenerate + review

You drew new floor plans (3 ORM model files). The contractor (Alembic) looks at:
- the existing house (the live MySQL schema)
- your new floor plans (your ORM models)

…and writes a **TODO list** of construction work needed to make them match. That TODO list is the migration file.

### The exact 3 steps

```powershell
# 1. Generate the TODO list (writes a new file to migrations/versions/)
alembic revision --autogenerate -m "create customers sales sale_items tables"

# 2. READ the file. Never trust autogenerate blindly. Look for:
#    - Tables created in the right order (parents before children)
#    - FK directions and ondelete rules match what you intended
#    - No surprise drops (autogenerate sometimes proposes destructive changes)

# 3. Apply it to the live DB
alembic upgrade head
```

### Why "review before apply" matters

Alembic is smart but not perfect. It can:
- Mistake a rename for a (drop + add)
- Miss indexes you forgot to declare
- Generate FKs without your intended ondelete rule (defaults to nothing)

Reading the file takes 30 seconds. Recovering from a destructive migration takes hours. **Always review.**

---

## 6. The `quantity` decrement (preview of step 3.7)

Right now, `select_batch` PICKS a batch. But it doesn't **subtract** the sold quantity from `batch.quantity`. That decrement is the job of the next node, `persist_sale`.

So a complete sale write involves FOUR things:

1. **INSERT** into `customers` (if customer is new — else find by phone)
2. **INSERT** into `sales` (the header)
3. **INSERT** into `sale_items` (one INSERT per line)
4. **UPDATE** `batches SET quantity = quantity - X` (one UPDATE per line)

### The danger: partial writes

What if the program crashes between step 2 and step 4?
- Sale is recorded → money taken
- Stock NOT decremented → other customers might buy from "phantom" stock

OR:

- Stock decremented
- Sale row creation failed → stock is "consumed" but no record of who bought it

Both scenarios = **inventory chaos + financial loss**.

### The fix: a TRANSACTION

A transaction is a wrapper around multiple writes that guarantees:

> **All of them succeed, or none of them succeed.** Never partial.

We'll learn this in **Step 3.7** when we build `persist_sale`. For now, just understand:

> Writing a sale is **not one INSERT** — it's a coordinated set of INSERTs + UPDATEs that must happen atomically.

That's why `persist_sale` is the most complex node of all 5. The rest are pure compute; this one touches state.

---

## What we achieve after Step 3.6

### Concrete new capabilities

| Capability | Why it matters |
|---|---|
| **Record a sale** | We now have the tables to actually store an invoice |
| **Recognize returning customers** | The unique index on `customers.phone` lets us "find or create" |
| **Answer "how much did Anurag spend last month?"** | Index on `sold_at` + `customer_id` makes this query fast |
| **Answer "which medicines sell the most?"** | Index on `sale_items.medicine_id` |
| **Show an old sale with its ORIGINAL prices** | Frozen `unit_price`/`line_total` make historic reports honest |
| **Hard-stop deletion of a medicine that has history** | `RESTRICT` rule on `sale_items.medicine_id` |
| **Auto-clean lines when a sale is deleted** | `CASCADE` rule on `sale_items.sale_id` |

### Where we are in Phase 3

```
✅ Step 3.1 — LLM provider factory
✅ Step 3.2 — extract_intent  (free text → structured)
✅ Step 3.3 — resolve_medicine (name → DB ID)
✅ Step 3.4 — select_batch    (DB ID → FEFO batch)
✅ Step 3.5 — compute_pricing (batch → prices + total)
✅ Step 3.6 — Customer/Sale/SaleItem tables (this step)   ← STORAGE READY

🔜 Step 3.7 — persist_sale     (write everything in one transaction)
🔜 Step 3.8 — compile the LangGraph (wire all 5 nodes)
🔜 Step 3.9 — billing service + router (POST /v1/billing/sale)
🔜 Step 3.10 — end-to-end HTTP test
```

### Interview talking points unlocked

1. **"Why does sale_items have a unit_price column when Medicine has mrp?"** → frozen price for audit
2. **"Why ON DELETE CASCADE on sale_id but RESTRICT on medicine_id?"** → lines need their header; history can't lose a medicine reference
3. **"Why duplicate total_amount on the Sale row when SaleItems already have line_total?"** → denormalization for fast report queries; trade-off vs strict normalization
4. **"Why is the customer_id nullable?"** → walk-in sales without captured info
5. **"What if the server crashes mid-sale write?"** → transaction; either all or nothing (step 3.7 detail)

---

## One-line summary

> **Step 3.6 doesn't add behavior — it adds STORAGE.** Every previous node produced data; now there's a place to put that data permanently, with the right shape, constraints, and indexes for both correctness and reporting speed.
