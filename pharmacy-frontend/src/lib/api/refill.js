/**
 * Refill Intelligence API (M6.2).
 *
 * Read-only. There is no send endpoint because M6.2 sends nothing — it decides
 * WHO should be contacted, and the communication layer that acts on that is
 * M6.3. Nothing in this module or on /refills knows what WhatsApp is.
 */
import { getJSON } from "./client";

/** Status values the backend can return, mirroring RefillStatus. */
export const REFILL_STATUS = {
    DUE: "due",
    NOT_DUE: "not_due",
    UNKNOWN_DURATION: "unknown_duration",
};

/** Contactability values, mirroring the Contactability enum. */
export const CONTACTABILITY = {
    CONTACTABLE: "contactable",
    NO_PHONE: "no_phone",
    NOT_OPTED_IN: "not_opted_in",
    OPTED_OUT: "opted_out",
};

/** What the filter bar can ask for. Mirrors the query parameters exactly. */
export const VIEW_OPTIONS = [
    { value: "due", label: "Due now" },
    { value: "contactable", label: "Due & reachable" },
    { value: "all", label: "Everything" },
];

/**
 * Turn the screen's single "view" choice into backend query parameters.
 *
 * The UI offers one dropdown; the API takes two independent booleans. Mapping
 * here keeps the page from having to know that "Due & reachable" happens to be
 * two flags, and keeps the two flags from leaking into three components.
 */
export function toQuery(view) {
    if (view === "all") return { due_only: false, contactable_only: false };
    if (view === "contactable") return { due_only: true, contactable_only: true };
    return { due_only: true, contactable_only: false };
}

/** Fetch refill candidates. Always returns a usable shape on success. */
export async function getRefillCandidates(view = "due") {
    const query = toQuery(view);
    const params = new URLSearchParams({
        due_only: String(query.due_only),
        contactable_only: String(query.contactable_only),
        limit: "100",
    });

    const result = await getJSON(`/api/v1/refill/candidates?${params}`);
    if (!result.ok) return result;

    // A malformed body must not crash the render. The page maps over
    // `candidates` and reads `summary` directly.
    const data = result.data || {};
    return {
        ...result,
        data: {
            ...data,
            candidates: Array.isArray(data.candidates) ? data.candidates : [],
            notes: Array.isArray(data.notes) ? data.notes : [],
        },
    };
}
