/**
 * Goods receipt (stock intake) API.
 *
 * This is the only screen in the app that WRITES stock, which changes what the
 * error handling has to do. Every other page reads: if a read fails, "try again"
 * is genuinely all the pharmacist can do. Here the failure is usually a specific,
 * fixable thing about the delivery in front of them — a batch already on the
 * shelf at a different price, a cost above MRP, an expiry in the past — and the
 * backend already writes those messages for a person.
 *
 * So this module deliberately SURFACES the server's `detail` for domain errors,
 * where the shared client would have replaced it with "Something went wrong."
 *
 * That is safe here and nowhere else, for two reasons worth stating:
 *   1. These messages are authored by us in goods_receipt_service.py, not
 *      produced by SQLAlchemy or MySQL. A backend integration test asserts they
 *      contain no SQL, traceback, driver name or credential.
 *   2. Only 404 / 409 / 422 are unwrapped. A 500 is still replaced, because a
 *      500's detail is exactly the kind of text that leaks internals.
 */
import { getJSON, postJSON, ERROR_MESSAGES } from "./client";

/** Statuses whose `detail` is a domain message written for a pharmacist. */
const DOMAIN_ERROR_STATUSES = [404, 409, 422];

/**
 * Pull a usable message out of a failed response.
 *
 * FastAPI answers with two different shapes and they must not be confused:
 *   - our domain errors   -> detail is a STRING
 *   - Pydantic validation -> detail is an ARRAY of field error objects
 * Rendering the array would put `[object Object]` on screen, so anything that is
 * not a plain string falls back to the shared wording.
 */
function domainError(result) {
    const detail = result?.data?.detail;
    if (DOMAIN_ERROR_STATUSES.includes(result.status) && typeof detail === "string" && detail) {
        return detail;
    }
    if (result.status === 422) return ERROR_MESSAGES.validation;
    return result.error || ERROR_MESSAGES.unexpected;
}

/**
 * Record a goods receipt.
 *
 * `receipt` must already be in wire shape — see `toReceiptPayload`. This function
 * does not reshape it, so there is one place that knows the contract.
 */
export async function recordGoodsReceipt(receipt) {
    const result = await postJSON("/api/v1/purchases", receipt);
    return result.ok ? result : { ...result, error: domainError(result) };
}

/** Suppliers, for the picker. Always an array on success. */
export async function listSuppliers() {
    const result = await getJSON("/api/v1/purchases/suppliers");
    return { ...result, data: Array.isArray(result.data) ? result.data : [] };
}

/** Recent receipts, newest first. Always an array on success. */
export async function listRecentReceipts(limit = 10) {
    const result = await getJSON(`/api/v1/purchases?limit=${Number(limit)}`);
    return { ...result, data: Array.isArray(result.data) ? result.data : [] };
}

/**
 * Turn form state into the request body.
 *
 * Note what is NOT here: no line_total, no total_amount, no total_units. The
 * server computes every money figure and there is no field on the contract to
 * suggest otherwise. This function only converts types and drops blanks.
 *
 * Numbers are sent as numbers. An <input> always yields a string, and "100"
 * would fail the backend's integer validation with a 422 that looks like a
 * mystery rather than a typo.
 */
export function toReceiptPayload({ supplierId, supplierName, invoiceNumber, purchaseDate, lines }) {
    const payload = {
        lines: lines.map((line) => ({
            medicine_id: Number(line.medicineId),
            batch_number: line.batchNumber.trim(),
            expiry_date: line.expiryDate,
            quantity: Number(line.quantity),
            unit_cost: Number(line.unitCost),
        })),
    };

    // Exactly one supplier field — sending both is a 422 by design, so the form
    // must decide here rather than leave it to the server to reject.
    if (supplierId) {
        payload.supplier_id = Number(supplierId);
    } else if (supplierName && supplierName.trim()) {
        payload.supplier_name = supplierName.trim();
    }

    if (invoiceNumber && invoiceNumber.trim()) payload.invoice_number = invoiceNumber.trim();
    if (purchaseDate) payload.purchase_date = purchaseDate;

    return payload;
}

/**
 * Is this form row complete enough to send?
 *
 * Presence only. Whether the expiry is in the future, whether the cost is under
 * MRP, whether the batch contradicts the shelf — none of that is decided here.
 * Those are business rules, they live in the service, and a copy in the browser
 * would be a second definition to keep in sync and a false reassurance when it
 * drifted.
 */
export function isLineComplete(line) {
    return Boolean(
        line.medicineId &&
            line.batchNumber &&
            line.batchNumber.trim() &&
            line.expiryDate &&
            line.quantity &&
            line.unitCost,
    );
}

/** A blank form row. Exported so the page and its tests agree on the shape. */
export function emptyLine() {
    return { medicineId: "", batchNumber: "", expiryDate: "", quantity: "", unitCost: "" };
}
