/**
 * API entry point.
 *
 * Fetch plumbing lives in ./client.js so every feature module shares one place
 * that decides what an error looks like. Feature modules sit alongside it and are
 * re-exported here, so `@/lib/api` stays the single import path for pages.
 *
 *   client.js    fetch, error shaping, X-Request-ID
 *   billing.js   catalog, per-line pricing, confirm
 *   sales.js     invoice history
 *   expiry.js    deterministic report + AI explanation
 */
import { getJSON, postJSON } from "./client";

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
export function approveReorder(proposal) {
    return postJSON("/api/v1/reorder/approve", {
        medicine_id: proposal.medicine_id,
        quantity: proposal.reorder_qty,
        source: proposal.source,
        reason: proposal.reason || null,
    });
}

// ── Feature modules ──────────────────────────────────────────────────────────
export * from "./billing";
export * from "./expiry";
export * from "./sales";
export { ERROR_MESSAGES } from "./client";
