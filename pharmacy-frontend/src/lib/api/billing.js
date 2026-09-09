/**
 * Billing API.
 *
 * The bill is built one line at a time. For each line the SERVER picks the batch
 * (FEFO) and sets the price from the database — the browser never sends a price,
 * and `confirm` recomputes everything again before writing the sale. A tampered
 * client payload cannot change what a customer is charged.
 *
 * There is no LLM in this flow.
 */
import { getJSON, postJSON } from "./client";

/** Units a line can be sold in. The backend defaults to "strip" when unset. */
export const UNIT_OPTIONS = ["strip", "tablet", "bottle", "tube", "pack", "unit"];

/** The medicine catalog the picker searches. */
export function listCatalog() {
    return getJSON("/api/v1/medicines");
}

/**
 * Price one line: medicine + quantity -> FEFO batch, unit price, line total.
 *
 * 422 means the medicine has no usable batch — unexpired and in stock. That is a
 * normal outcome worth showing the user, not an error to swallow.
 */
export function priceLine({ medicineId, quantity, name, unit }) {
    return postJSON("/api/v1/billing/price-item", {
        medicine_id: medicineId,
        quantity,
        name,
        unit,
    });
}

/** Finalize the reviewed bill. Writes the sale and decrements stock. 201 on success. */
export function confirmSale(items, customerName, customerPhone) {
    return postJSON("/api/v1/billing/confirm", {
        items: items.map((it) => ({
            name: it.name,
            quantity: it.quantity,
            unit: it.unit,
            medicine_id: it.medicine_id,
            batch_id: it.batch_id,
            batch_number: it.batch_number,
            expiry_date: it.expiry_date,
        })),
        customer_name: customerName || null,
        customer_phone: customerPhone || null,
    });
}
