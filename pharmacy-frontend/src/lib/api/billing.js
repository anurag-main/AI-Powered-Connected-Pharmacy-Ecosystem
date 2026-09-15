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

/**
 * Finalize the reviewed bill. Writes the sale and decrements stock. 201 on success.
 *
 * M6.1 adds two facts the future refill engine needs, and nothing that acts on
 * them: how long each line is expected to last, and whether the customer agreed
 * to WhatsApp reminders. Nothing here sends a message.
 */
export function confirmSale(items, customerName, customerPhone, whatsappOptIn = false) {
    return postJSON("/api/v1/billing/confirm", {
        items: items.map((it) => ({
            name: it.name,
            quantity: it.quantity,
            unit: it.unit,
            medicine_id: it.medicine_id,
            batch_id: it.batch_id,
            batch_number: it.batch_number,
            expiry_date: it.expiry_date,
            // null means "the pharmacist does not know how long this lasts", and
            // the backend stores that NULL rather than guessing. An empty string
            // or 0 would both be wrong: 0 fails validation, "" is not an int.
            days_supply: toDaysSupply(it.days_supply),
        })),
        customer_name: customerName || null,
        customer_phone: customerPhone || null,
        // Consent is never implied by the customer giving a phone number.
        whatsapp_opt_in: Boolean(whatsappOptIn),
    });
}

/**
 * Coerce the days-supply input to what the API expects.
 *
 * An <input type="number"> yields a STRING, and an emptied one yields "". Both
 * have to become either a real integer or an explicit null, because the backend
 * distinguishes them: null is recorded as "unknown, do not remind", while a
 * number schedules a future reminder. Sending "" would be a 422; sending 0 is
 * rejected by design so that unknown has exactly one spelling.
 */
export function toDaysSupply(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number(value);
    if (!Number.isInteger(parsed) || parsed < 1) return null;
    return parsed;
}
