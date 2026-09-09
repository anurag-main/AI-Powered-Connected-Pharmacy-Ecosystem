/**
 * Expiry Risk API.
 *
 * Two calls, and the split is deliberate — see docs/agents/expiry_risk_agent.md.
 *
 *   getExpiryReport()  deterministic, no LLM. Fast and free. Drives the cards and
 *                      the table.
 *   explainExpiryRisk() the AI paragraph, for the SAME query. Slower and costs a
 *                      model call, so it runs second and never blocks the table.
 *
 * Send the identical params to both. The backend skips its planner when it is
 * handed a query, which is what guarantees the prose describes the rows on screen
 * rather than a window the model picked for itself.
 *
 * Nothing here calculates risk. The frontend chooses filters and renders what comes
 * back; every number is computed in Python.
 */
import { postJSON } from "./client";

/** Filter values the backend will accept. Mirrors ExpiryRiskQuery. */
export const WINDOW_OPTIONS = [
    { value: 7, label: "7 days" },
    { value: 30, label: "30 days" },
    { value: 90, label: "90 days" },
    { value: 180, label: "6 months" },
    { value: 365, label: "1 year" },
];

export const RISK_OPTIONS = [
    { value: "", label: "All levels" },
    { value: "expired", label: "Expired" },
    { value: "critical", label: "Critical" },
    { value: "high", label: "High" },
    { value: "medium", label: "Medium" },
    { value: "low", label: "Low" },
];

export const LIMIT_OPTIONS = [
    { value: 10, label: "Top 10" },
    { value: 25, label: "Top 25" },
    { value: 50, label: "Top 50" },
    { value: 100, label: "Top 100" },
];

/** Risk levels worst-first — the backend's RISK_ORDER, for display only. */
export const RISK_LEVELS = ["expired", "critical", "high", "medium", "low"];

/**
 * Turn UI filter state into an ExpiryRiskQuery body.
 *
 * `risk_level` is omitted rather than sent as "" — the backend field is an enum or
 * null, and an empty string is neither.
 */
export function toQuery({ windowDays, riskLevel, limit, includeExpired = true }) {
    const query = {
        window_days: Number(windowDays),
        limit: Number(limit),
        include_expired: includeExpired,
    };
    if (riskLevel) query.risk_level = riskLevel;
    return query;
}

/** Deterministic report: counts, totals and the ranked batches. No LLM. */
export function getExpiryReport(query) {
    return postJSON("/api/v1/expiry/report", query);
}

/** AI explanation of that same report. Prose only — it carries no figures. */
export function explainExpiryRisk(query) {
    return postJSON("/api/v1/expiry/explain", query);
}
