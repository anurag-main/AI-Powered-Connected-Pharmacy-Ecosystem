"""Business rules for recording a goods receipt (stock intake).

WHAT THIS FIXES
---------------
Before this service, stock in this system could only ever go DOWN. Billing
decremented batches; nothing in the running application ever created one. Every
batch in the database came from a seed script, which means the feature had been
demonstrated but never built. A real shop running this code would have reached
zero stock and the Inventory Risk and Expiry agents would have slowly gone blind.

THE ORDER OF WORK, AND WHY IT IS THIS ORDER
-------------------------------------------
    1. Validate everything that can be checked without writing.
    2. Open ONE transaction.
    3. Write suppliers, purchases, batches, purchase_items.
    4. Commit once, or roll back all of it.

Validation happens entirely before step 2 on purpose. A rule that fails halfway
through the writing still rolls back correctly, but it holds row locks on the
batches table while it does so, and it produces a rollback in the log for what is
really a user typo. Checking first means a bad request never opens a transaction.

WHAT THIS SERVICE REFUSES TO DECIDE
-----------------------------------
It does not invent medicines, it does not average costs, and it does not accept a
total from the client. Where two records disagree it raises rather than guessing:
silently overwriting a cost basis would corrupt every profit figure computed from
it afterwards, and nothing downstream would ever report the corruption.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.core.time_range import today
from app.exceptions import (
    BatchConflictError,
    InvalidGoodsReceiptError,
    MedicineNotFoundError,
    SupplierNotFoundError,
)
from app.repositories.purchase_repository import PurchaseRepository
from app.schemas.purchase import (
    GoodsReceiptCreate,
    GoodsReceiptLineOut,
    GoodsReceiptOut,
    PurchaseSummary,
    SupplierOut,
)

# The largest number of receipts the list endpoint will ever return. The UI shows
# a recent-activity panel, not an archive; an unbounded list is a query that gets
# slower every day the shop stays open.
MAX_RECENT_PURCHASES = 50


def _money(value: float | Decimal) -> Decimal:
    """Convert to a 2-decimal Decimal, rounding half-up.

    Money never travels as a float inside this service. ``float`` cannot
    represent 0.1 exactly, so a 3-line invoice of 0.1 each can total 0.30000000004
    and land in a DECIMAL(10,2) column as something the pharmacist did not type.
    ``str(value)`` in the constructor is deliberate -- ``Decimal(0.1)`` inherits
    the binary error, ``Decimal("0.1")`` does not.
    """
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class GoodsReceiptService:
    """Records stock arriving from a supplier. The only writer of batches."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = PurchaseRepository(db)

    # -----------------------------------------------------------------
    # Write
    # -----------------------------------------------------------------

    def record_receipt(self, payload: GoodsReceiptCreate) -> GoodsReceiptOut:
        """Validate a supplier invoice and record it, atomically.

        Raises ``InvalidGoodsReceiptError`` (422), ``MedicineNotFoundError`` (404),
        ``SupplierNotFoundError`` (404) or ``BatchConflictError`` (409). On any of
        them nothing at all is written.
        """
        as_of = today()

        # ---- Rule 1: exactly one way to name the supplier ----
        # Neither leaves the purchase unattributable. Both invites a request where
        # the id says one vendor and the name says another, and no answer to which
        # of the two the pharmacist meant.
        if payload.supplier_id is None and payload.supplier_name is None:
            raise InvalidGoodsReceiptError(
                "Provide either supplier_id or supplier_name."
            )
        if payload.supplier_id is not None and payload.supplier_name is not None:
            raise InvalidGoodsReceiptError(
                "Provide supplier_id or supplier_name, not both."
            )

        # ---- Rule 2: the invoice cannot be dated in the future ----
        # A future purchase date would put stock into a period that has not
        # happened, which quietly breaks every purchase-trend window.
        purchase_date = payload.purchase_date or as_of
        if purchase_date > as_of:
            raise InvalidGoodsReceiptError(
                f"purchase_date {purchase_date} is in the future."
            )

        # ---- Rule 3: no medicine listed twice in one receipt ----
        # Two lines for the same medicine AND batch number are ambiguous: it could
        # be a double-entry or two real cartons. Refusing is safer than doubling
        # someone's stock because they tabbed backwards.
        seen: set[tuple[int, str]] = set()
        for line in payload.lines:
            key = (line.medicine_id, line.batch_number.lower())
            if key in seen:
                raise InvalidGoodsReceiptError(
                    f"Medicine {line.medicine_id} batch {line.batch_number!r} "
                    f"appears more than once in this receipt."
                )
            seen.add(key)

        # ---- Rule 4: every medicine must already be in the catalogue ----
        medicines = self.repository.medicines_by_ids(
            [line.medicine_id for line in payload.lines]
        )
        for line in payload.lines:
            if line.medicine_id not in medicines:
                raise MedicineNotFoundError(line.medicine_id)

        # ---- Rule 5: expiry in the future, cost at or below MRP ----
        for line in payload.lines:
            if line.expiry_date <= as_of:
                raise InvalidGoodsReceiptError(
                    f"Batch {line.batch_number!r} expires {line.expiry_date}, "
                    f"which is not in the future. Expired stock cannot be received."
                )

            medicine = medicines[line.medicine_id]
            unit_cost = _money(line.unit_cost)
            mrp = _money(medicine.mrp)
            if unit_cost > mrp:
                # MRP is the legal maximum retail price, so wholesale is always
                # below it. This is a real invariant AND the cheapest catch for
                # the decimal-point typo that would otherwise multiply the shop's
                # recorded inventory value by a hundred.
                raise InvalidGoodsReceiptError(
                    f"unit_cost {unit_cost} for {medicine.name!r} exceeds its MRP "
                    f"{mrp}. Check the decimal point."
                )

        # ---- Rule 6: an incoming batch must not contradict the shelf ----
        # Checked before the transaction so a conflict costs no locks. Re-read
        # inside the transaction below, because between here and there another
        # request could have created the same batch.
        for line in payload.lines:
            existing = self.repository.find_batch(
                medicine_id=line.medicine_id, batch_number=line.batch_number
            )
            if existing is not None:
                self._assert_batch_matches(existing, line, medicines)

        # =================================================================
        # TRANSACTION -- everything below commits together or not at all.
        #
        # NOT ``with self.db.begin():``, which is what persist_sale.py uses. That
        # form requires a session with no transaction open, and it works there
        # because the node opens its own ``SessionLocal()`` and writes
        # immediately. Here the session arrives from ``Depends(get_db)`` and the
        # validation above has already read from it, which implicitly began a
        # transaction -- ``begin()`` would raise "a transaction is already begun".
        # So the boundary is explicit: one commit at the end, rollback on any
        # exception. The reads and the writes share the one transaction.
        # =================================================================
        try:
            supplier = self._resolve_supplier(payload)

            # The total is summed from the lines the server priced, never read
            # from the request. Same rule billing already enforces: money is a
            # server decision.
            line_plans = []
            total_amount = Decimal("0.00")
            total_units = 0
            for line in payload.lines:
                unit_cost = _money(line.unit_cost)
                line_total = _money(unit_cost * line.quantity)
                total_amount += line_total
                total_units += line.quantity
                line_plans.append((line, unit_cost, line_total))

            purchase = self.repository.create_purchase(
                supplier_id=supplier.id,
                purchase_date=purchase_date,
                invoice_number=payload.invoice_number,
                total_amount=total_amount,
            )

            out_lines: list[GoodsReceiptLineOut] = []
            for line, unit_cost, line_total in line_plans:
                batch, created = self._upsert_batch(line, unit_cost, medicines)

                self.repository.create_purchase_item(
                    purchase_id=purchase.id,
                    medicine_id=line.medicine_id,
                    batch_id=batch.id,
                    quantity=line.quantity,
                    unit_cost=unit_cost,
                    line_total=line_total,
                )

                out_lines.append(
                    GoodsReceiptLineOut(
                        medicine_id=line.medicine_id,
                        medicine_name=medicines[line.medicine_id].name,
                        batch_id=batch.id,
                        batch_number=batch.batch_number,
                        expiry_date=batch.expiry_date,
                        quantity=line.quantity,
                        unit_cost=float(unit_cost),
                        line_total=float(line_total),
                        batch_created=created,
                    )
                )

            # Read every attribute we need for the response BEFORE leaving the
            # block. After commit these instances are expired, and touching them
            # would fire a fresh SELECT per attribute -- or fail outright if the
            # session has been closed by then.
            result = GoodsReceiptOut(
                purchase_id=purchase.id,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                invoice_number=purchase.invoice_number,
                purchase_date=purchase.purchase_date,
                total_amount=float(total_amount),
                total_units=total_units,
                lines=out_lines,
                created_at=purchase.created_at,
            )

            self.db.commit()

        except Exception:
            # Covers the domain errors raised by _upsert_batch inside the
            # transaction as well as any database failure. Re-raised unchanged so
            # the router still maps BatchConflictError to 409 rather than 500.
            self.db.rollback()
            raise

        return result

    # -----------------------------------------------------------------
    # Write helpers
    # -----------------------------------------------------------------

    def _resolve_supplier(self, payload: GoodsReceiptCreate):
        """Find the vendor by id, or find-or-create it by name."""
        if payload.supplier_id is not None:
            supplier = self.repository.get_supplier(payload.supplier_id)
            if supplier is None:
                raise SupplierNotFoundError(payload.supplier_id)
            return supplier

        assert payload.supplier_name is not None  # guaranteed by Rule 1
        existing = self.repository.find_supplier_by_name(payload.supplier_name)
        if existing is not None:
            return existing
        return self.repository.create_supplier(name=payload.supplier_name)

    def _upsert_batch(self, line, unit_cost: Decimal, medicines: dict):
        """Top up the existing batch, or create it. Returns ``(batch, created)``.

        Topping up rather than inserting a second row is the important half. Two
        rows with the same batch number would both be valid to FEFO, both counted
        by the inventory agent, and impossible to reconcile against one physical
        carton on the shelf.
        """
        existing = self.repository.find_batch(
            medicine_id=line.medicine_id, batch_number=line.batch_number
        )
        if existing is not None:
            # Re-checked inside the transaction: another request may have created
            # this batch since the pre-flight check above.
            self._assert_batch_matches(existing, line, medicines)
            existing.quantity += line.quantity
            return existing, False

        batch = self.repository.create_batch(
            medicine_id=line.medicine_id,
            batch_number=line.batch_number,
            expiry_date=line.expiry_date,
            quantity=line.quantity,
            cost_price=unit_cost,
        )
        return batch, True

    @staticmethod
    def _assert_batch_matches(existing, line, medicines) -> None:
        """Refuse a top-up whose expiry or cost contradicts the shelf record.

        There is no correct way to merge these automatically. Averaging the cost
        would silently restate the value of stock already counted, and taking the
        newer expiry would extend the sellable life of tablets that do not have
        it. Both are worse than an error message, because neither is visible
        afterwards.
        """
        name = medicines[line.medicine_id].name

        if existing.expiry_date != line.expiry_date:
            raise BatchConflictError(
                f"Batch {line.batch_number!r} of {name!r} is already on the shelf "
                f"expiring {existing.expiry_date}, but this receipt says "
                f"{line.expiry_date}. One of the two is wrong."
            )

        incoming_cost = _money(line.unit_cost)
        shelf_cost = _money(existing.cost_price)
        if shelf_cost != incoming_cost:
            raise BatchConflictError(
                f"Batch {line.batch_number!r} of {name!r} is already on the shelf "
                f"at cost {shelf_cost}, but this receipt says {incoming_cost}. "
                f"Weighted-average costing is not supported -- use a different "
                f"batch number if this is genuinely a different price."
            )

    # -----------------------------------------------------------------
    # Read
    # -----------------------------------------------------------------

    def list_suppliers(self) -> list[SupplierOut]:
        """Every vendor, for the picker on the receipt form."""
        return [
            SupplierOut(id=s.id, name=s.name, phone=s.phone)
            for s in self.repository.list_suppliers()
        ]

    def recent_receipts(self, *, limit: int = 20) -> list[PurchaseSummary]:
        """The most recent receipts, newest first, without their lines."""
        bounded = max(1, min(limit, MAX_RECENT_PURCHASES))
        return [
            PurchaseSummary(
                purchase_id=purchase.id,
                supplier_id=purchase.supplier_id,
                supplier_name=supplier_name,
                invoice_number=purchase.invoice_number,
                purchase_date=purchase.purchase_date,
                total_amount=float(purchase.total_amount),
                line_count=line_count,
            )
            for purchase, supplier_name, line_count in self.repository.recent_purchases(
                limit=bounded
            )
        ]

    def receipt_detail(self, purchase_id: int) -> GoodsReceiptOut | None:
        """One recorded receipt with its lines, or ``None`` if there is no such id.

        ``batch_created`` is reported as ``False`` here for every line. This
        endpoint reads history, and whether a batch row was new at the moment it
        was written is not recorded anywhere -- reporting it as ``True`` would be
        inventing a fact. Noted in the schema rather than hidden.
        """
        found = self.repository.purchase_detail(purchase_id)
        if found is None:
            return None

        header, supplier_name, rows = found
        lines = [
            GoodsReceiptLineOut(
                medicine_id=item.medicine_id,
                medicine_name=medicine.name,
                batch_id=item.batch_id if item.batch_id is not None else 0,
                batch_number=batch.batch_number if batch is not None else "(no batch)",
                expiry_date=batch.expiry_date if batch is not None else header.purchase_date,
                quantity=item.quantity,
                unit_cost=float(item.unit_cost),
                line_total=float(item.line_total),
                batch_created=False,
            )
            for item, medicine, batch in rows
        ]

        return GoodsReceiptOut(
            purchase_id=header.id,
            supplier_id=header.supplier_id,
            supplier_name=supplier_name,
            invoice_number=header.invoice_number,
            purchase_date=header.purchase_date,
            total_amount=float(header.total_amount),
            total_units=sum(line.quantity for line in lines),
            lines=lines,
            created_at=header.created_at,
        )
