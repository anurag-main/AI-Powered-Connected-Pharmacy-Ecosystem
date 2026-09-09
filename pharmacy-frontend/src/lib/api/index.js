/**
 * Billing / medicines / reorder API calls.
 *
 * Fetch plumbing lives in ./client.js so every feature module shares one place
 * that decides what an error looks like. Feature modules sit alongside this file
 * (./expiry.js) and are re-exported at the bottom, so `@/lib/api` stays the single
 * import path for pages.
 */
import { getJSON, postJSON } from "./client";

/** Preview: price a spoken/typed order WITHOUT saving. Always 200. */
export function quoteSale(pharmacistInput) {
    return postJSON("/api/v1/billing/quote", { pharmacist_input: pharmacistInput });
}

/** Finalize: persist the reviewed line items as a real sale. 201 on success. */
export function confirmSale(items, customerName, customerPhone) {
    return postJSON("/api/v1/billing/confirm", {
        items,
        customer_name: customerName || null,
        customer_phone: customerPhone || null,
    });
}

/** Price one medicine by id (used when the owner switches a confirm-row candidate). */
export function priceItem(medicineId, quantity, name, unit) {
    return postJSON("/api/v1/billing/price-item", {
        medicine_id: medicineId,
        quantity,
        name,
        unit,
    });
}

/** List the medicine catalog (for the Medicines page). Always an array on success. */
export async function listMedicines() {
    const result = await getJSON("/api/v1/medicines");
    // The page maps straight over `data`; a non-array body must not crash the render.
    return { ...result, data: Array.isArray(result.data) ? result.data : [] };
}

/** Reorder agent: run the agent (fetch → decide → judge) and return proposals. Always 200. */
export function getReorderSuggestions() {
    return getJSON("/api/v1/reorder/suggestions");
}

/** Approve one proposal → persists a pending reorder request. Idempotent. */
export async function approveReorder(proposal) {
    return postJSON("/api/v1/reorder/approve", {
        medicine_id: proposal.medicine_id,
        quantity: proposal.reorder_qty,
        source: proposal.source,
        reason: proposal.reason || null,
    });
}

// ── Feature modules ──────────────────────────────────────────────────────────
// Re-exported so pages can keep importing everything from "@/lib/api".
export * from "./expiry";
export { ERROR_MESSAGES } from "./client";
