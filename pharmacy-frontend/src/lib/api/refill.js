/**
 * Refill Intelligence API (M6.2).
 *
 * Read-only. There is no send endpoint because M6.2 sends nothing — it decides
 * WHO should be contacted, and the communication layer that acts on that is
 * M6.3. Nothing in this module or on /refills knows what WhatsApp is.
 */
import { getJSON, postJSON } from "./client";

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

/**
 * Reminder lifecycle values, mirroring NotificationStatus.
 *
 * `pending` and `sending` are transient; the dashboard shows them so a stuck
 * reminder is visible rather than looking like it was never created.
 */
export const NOTIFICATION_STATUS = {
    PENDING: "pending",
    SENDING: "sending",
    SENT: "sent",
    DELIVERED: "delivered",
    READ: "read",
    FAILED: "failed",
    CANCELLED: "cancelled",
};

/**
 * Ask the backend to send the reminder for one refill opportunity.
 *
 * Takes the OPPORTUNITY's identity, not a message. The browser cannot assert
 * that someone is due or that they consented — the server re-derives the
 * candidate and re-checks consent before anything is sent. There is deliberately
 * no path from this app to Meta.
 *
 * Always resolves; a refusal ("customer opted out") is a business answer the
 * screen displays, not an error.
 */
export function sendRefillReminder(candidate) {
    return postJSON("/api/v1/notifications/refill-reminder", {
        source_sale_item_id: candidate.source_sale_item_id,
        expected_refill_date: candidate.expected_refill_date,
    });
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
            // Keyed by source_sale_item_id (as a string — JSON object keys
            // always are). The table looks each row up rather than the frontend
            // joining two lists itself.
            notifications:
                data.notifications && typeof data.notifications === "object"
                    ? data.notifications
                    : {},
        },
    };
}
