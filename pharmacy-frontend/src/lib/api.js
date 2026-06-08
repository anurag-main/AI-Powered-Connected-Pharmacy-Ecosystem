/**
 * API client for the FastAPI backend.
 *
 * Every call returns { ok, status, data } so callers can branch on HTTP status
 * without try/catch around res.json(). Base URL comes from .env.local
 * (NEXT_PUBLIC_API_BASE_URL); the NEXT_PUBLIC_ prefix exposes it to the browser.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function postJSON(path, body) {
    const res = await fetch(`${BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
}

/** Preview: price a spoken/typed order WITHOUT saving. Always 200. */
export async function quoteSale(pharmacistInput) {
    return postJSON("/api/v1/billing/quote", { pharmacist_input: pharmacistInput });
}

/** Finalize: persist the reviewed line items as a real sale. 201 on success. */
export async function confirmSale(items, customerName, customerPhone) {
    return postJSON("/api/v1/billing/confirm", {
        items,
        customer_name: customerName || null,
        customer_phone: customerPhone || null,
    });
}

/** Price one medicine by id (used when the owner switches a confirm-row candidate). */
export async function priceItem(medicineId, quantity, name, unit) {
    return postJSON("/api/v1/billing/price-item", {
        medicine_id: medicineId,
        quantity,
        name,
        unit,
    });
}

/** List the medicine catalog (for the Medicines page). */
export async function listMedicines() {
    const res = await fetch(`${BASE}/api/v1/medicines`);
    const data = await res.json().catch(() => []);
    return { ok: res.ok, status: res.status, data };
}

/** Reorder agent: run the agent (fetch → decide → judge) and return proposals. Always 200. */
export async function getReorderSuggestions() {
    const res = await fetch(`${BASE}/api/v1/reorder/suggestions`);
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
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
