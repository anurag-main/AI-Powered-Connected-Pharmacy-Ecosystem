/**
 * Inventory Risk API.
 *
 * Two calls, same split as expiry — see docs/agents/inventory_risk_agent.md.
 *
 *   getInventoryReport()  deterministic, no LLM. Fast and free. Drives the cards
 *                         and the table. Measured at 44ms against real MySQL.
 *   explainInventoryRisk() the AI paragraph for the SAME query. ~5.5s and costs a
 *                         model call, so it runs second and never blocks the table.
 *
 * Send the identical params to both. The backend skips its planner when it is
 * handed a query, which is what guarantees the prose describes the rows on screen
 * rather than a target cover the model picked for itself.
 *
 * Nothing here calculates risk. The frontend chooses filters and renders what comes
 * back; capital at risk, days of cover, excess and risk level are all computed in
 * Python.
 */
import { postJSON } from "./client";

/**
 * Filter values the backend will accept. Mirrors InventoryRiskQuery, so the UI
 * cannot offer something the API would reject with a 422.
 */
export const RISK_OPTIONS = [
    { value: "", label: "All levels" },
    { value: "dead", label: "Dead stock" },
    { value: "critical", label: "Critical" },
    { value: "high", label: "High" },
    { value: "medium", label: "Medium" },
    { value: "healthy", label: "Healthy" },
];

export const SORT_OPTIONS = [
    { value: "risk", label: "Risk level" },
    { value: "capital_at_risk", label: "Capital at risk" },
    { value: "days_of_cover", label: "Days of cover" },
    { value: "stock_age", label: "Stock age" },
];

/** Bounded 7-365 by the backend. These are the useful holding periods, not the range. */
export const TARGET_COVER_OPTIONS = [
    { value: 14, label: "2 weeks" },
    { value: 30, label: "1 month" },
    { value: 60, label: "2 months" },
    { value: 90, label: "3 months" },
    { value: 180, label: "6 months" },
];

export const LIMIT_OPTIONS = [
    { value: 10, label: "Top 10" },
    { value: 25, label: "Top 25" },
    { value: 50, label: "Top 50" },
    { value: 100, label: "Top 100" },
];

/** Risk levels worst-first — the backend's RISK_ORDER, for display only. */
export const RISK_LEVELS = ["dead", "critical", "high", "medium", "healthy"];

/**
 * Turn UI filter state into an InventoryRiskQuery body.
 *
 * `risk_level` is omitted rather than sent as "" — the backend field is an enum or
 * null, and an empty string is neither. `min_capital_at_risk` is omitted when zero
 * for the same reason it is a default server-side: sending 0 and sending nothing
 * mean the same thing, and the shorter body is the one that reads correctly in a log.
 */
export function toQuery({ targetCoverDays, riskLevel, sort, limit, minCapital = 0 }) {
    const query = {
        target_cover_days: Number(targetCoverDays),
        sort,
        limit: Number(limit),
    };
    if (riskLevel) query.risk_level = riskLevel;
    if (Number(minCapital) > 0) query.min_capital_at_risk = Number(minCapital);
    return query;
}

/** Deterministic report: counts, totals and the ranked medicines. No LLM. */
export function getInventoryReport(query) {
    return postJSON("/api/v1/inventory/report", query);
}

/** AI explanation of that same report. Prose only — it carries no figures. */
export function explainInventoryRisk(query) {
    return postJSON("/api/v1/inventory/explain", query);
}
