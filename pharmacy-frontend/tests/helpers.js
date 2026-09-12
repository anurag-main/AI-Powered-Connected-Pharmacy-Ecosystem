import { vi } from "vitest";

/**
 * Test helpers for the frontend suite.
 *
 * Everything here mocks at the `fetch` boundary rather than mocking our own API
 * modules. That choice matters: it means `lib/api/client.js` (status-to-message
 * mapping, X-Request-ID) and `lib/api/expiry.js` (`toQuery`) are the REAL code under
 * test. Mocking `getExpiryReport` directly would have skipped both and let a broken
 * request body pass unnoticed.
 */

/** The shape the backend actually returns for one batch. Override what a test cares about. */
export function makeItem(overrides = {}) {
    return {
        batch_id: 1,
        batch_number: "P1",
        medicine_id: 17,
        medicine_name: "Paracetamol 500",
        expiry_date: "2026-10-14",
        days_to_expiry: 5,
        stock_quantity: 30,
        estimated_demand: 10,
        potential_excess: 20,
        unit_cost: 10.0,
        value_at_risk: 200.0,
        risk_level: "critical",
        priority_score: 40.0,
        reasons: ["5 day(s) to expiry", "30 unit(s) in stock"],
        recommendation: "Act now - only 5 day(s) left.",
        ...overrides,
    };
}

/** A full /report body. Mirrors ExpiryReportResponse field for field. */
export function makeReport(overrides = {}) {
    const items = overrides.items ?? [makeItem()];
    return {
        generated_for: "2026-09-12",
        window_days: 30,
        demand_lookback_days: 90,
        total_batches_reviewed: items.length,
        total_at_risk: items.filter((i) => i.potential_excess > 0).length,
        total_value_at_risk: items.reduce((sum, i) => sum + i.value_at_risk, 0),
        counts_by_risk: { expired: 0, critical: 1, high: 0, medium: 0, low: 0 },
        notes: ["Demand is an estimate from history, not a forecast."],
        execution_time_ms: 12,
        ...overrides,
        items,
    };
}

/** A /explain body. */
export function makeExplanation(overrides = {}) {
    return {
        answer: "One batch carries excess stock.",
        confidence: 0.8,
        execution_time_ms: 900,
        agent_version: "expiry-agent-v1",
        ...overrides,
    };
}

function jsonResponse(body, status = 200, requestId = "test-req-id") {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
        headers: { get: (name) => (name === "X-Request-ID" ? requestId : null) },
    };
}

/** A promise plus its resolver, for holding a request open to observe a loading state. */
export function deferred() {
    let resolve;
    const promise = new Promise((r) => {
        resolve = r;
    });
    return { promise, resolve };
}

/**
 * Install a fetch mock that answers by path.
 *
 * @param {object} opts
 * @param {object} opts.report        body returned by /expiry/report
 * @param {number} opts.reportStatus  HTTP status for /expiry/report (default 200)
 * @param {object} opts.explain       body returned by /expiry/explain
 * @param {boolean} opts.networkError make fetch reject, as an offline browser does
 * @param {Promise} opts.hold         if given, /expiry/report waits on this promise
 * @returns the vi.fn() so a test can assert on calls
 */
export function mockApi({
    report = makeReport(),
    reportStatus = 200,
    explain = makeExplanation(),
    explainStatus = 200,
    networkError = false,
    hold = null,
} = {}) {
    const mock = vi.fn(async (url) => {
        if (networkError) throw new TypeError("Failed to fetch");

        if (String(url).includes("/api/v1/expiry/report")) {
            if (hold) await hold;
            return jsonResponse(report, reportStatus);
        }
        if (String(url).includes("/api/v1/expiry/explain")) {
            return jsonResponse(explain, explainStatus);
        }
        throw new Error(`Unexpected request in test: ${url}`);
    });

    vi.stubGlobal("fetch", mock);
    return mock;
}

/** The parsed JSON body of the first call to `path`. */
export function bodyOf(mock, path) {
    const call = mock.mock.calls.find(([url]) => String(url).includes(path));
    if (!call) throw new Error(`No request was made to ${path}`);
    return JSON.parse(call[1].body);
}

/** The full URL of the first call to `path`. */
export function urlOf(mock, path) {
    const call = mock.mock.calls.find(([url]) => String(url).includes(path));
    if (!call) throw new Error(`No request was made to ${path}`);
    return String(call[0]);
}

/** The request init (method, headers) of the first call to `path`. */
export function initOf(mock, path) {
    const call = mock.mock.calls.find(([url]) => String(url).includes(path));
    if (!call) throw new Error(`No request was made to ${path}`);
    return call[1];
}
