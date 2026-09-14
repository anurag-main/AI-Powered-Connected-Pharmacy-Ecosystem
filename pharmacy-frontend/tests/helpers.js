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

// ---------------------------------------------------------------------------
// Inventory Risk
//
// Separate factories rather than parameterising the expiry ones: the two reports
// share almost no fields, and a single "make a report" helper covering both would
// need every field optional, which is how a test ends up asserting against a shape
// the backend never returns.
// ---------------------------------------------------------------------------

/** The shape the backend actually returns for one medicine. Override what a test cares about. */
export function makeInventoryItem(overrides = {}) {
    return {
        medicine_id: 1,
        medicine_name: "Paracetamol 500",
        stock_quantity: 400,
        inventory_value: 40000.0,
        sellable_quantity: 400,
        weighted_avg_cost: 100.0,
        units_sold: 90,
        daily_velocity: 1.0,
        days_of_cover: 400.0,
        last_sale_date: "2026-08-14",
        days_since_last_sale: 30,
        ever_sold: true,
        target_stock: 60,
        excess_units: 340,
        excess_value: 34000.0,
        capital_at_risk: 34000.0,
        oldest_receipt_date: "2026-05-16",
        stock_age_days: 120,
        risk_level: "critical",
        risk_reasons: ["400 unit(s) in stock", "400 day(s) of cover"],
        ...overrides,
    };
}

/** A full /inventory/report body. Mirrors InventoryReportResponse field for field. */
export function makeInventoryReport(overrides = {}) {
    const items = overrides.items ?? [makeInventoryItem()];
    return {
        generated_for: "2026-09-14",
        demand_lookback_days: 90,
        target_cover_days: 60,
        medicines_reviewed: items.length,
        medicines_without_stock: 0,
        items_matching_filter: items.length,
        total_inventory_value: 72650.0,
        total_capital_at_risk: 62750.0,
        capital_at_risk_in_view: 62750.0,
        counts_by_risk: { dead: 0, critical: 1, high: 0, medium: 0, healthy: 0 },
        notes: ["Velocity is an estimate from history, not a forecast."],
        execution_time_ms: 44,
        ...overrides,
        items,
    };
}

/** An /inventory/explain body. */
export function makeInventoryExplanation(overrides = {}) {
    return {
        answer: "Rs 62,750 is at risk across the shop.",
        confidence: 0.8,
        execution_time_ms: 5492,
        agent_version: "inventory-agent-v1",
        ...overrides,
    };
}

/**
 * Install a fetch mock answering the two inventory paths.
 *
 * Same contract as `mockApi`, and the same reason for existing: mocking at `fetch`
 * means `lib/api/inventory.js` (`toQuery`) and `lib/api/client.js` (status-to-message
 * mapping) are the REAL code under test.
 */
export function mockInventoryApi({
    report = makeInventoryReport(),
    reportStatus = 200,
    explain = makeInventoryExplanation(),
    explainStatus = 200,
    networkError = false,
    hold = null,
} = {}) {
    const mock = vi.fn(async (url) => {
        if (networkError) throw new TypeError("Failed to fetch");

        if (String(url).includes("/api/v1/inventory/report")) {
            if (hold) await hold;
            return jsonResponse(report, reportStatus);
        }
        if (String(url).includes("/api/v1/inventory/explain")) {
            return jsonResponse(explain, explainStatus);
        }
        throw new Error(`Unexpected request in test: ${url}`);
    });

    vi.stubGlobal("fetch", mock);
    return mock;
}

// ── Goods receipt (stock intake) ─────────────────────────────────────────────

/** One medicine in the catalogue picker. */
export function makeCatalogueMedicine(overrides = {}) {
    return {
        id: 17,
        name: "Paracetamol 500mg",
        mrp: 30.0,
        hsn_code: "30049099",
        manufacturer: "GSK",
        created_at: "2026-01-01T00:00:00",
        ...overrides,
    };
}

/** One line on a recorded receipt, as the SERVER returns it. */
export function makeReceiptLine(overrides = {}) {
    return {
        medicine_id: 17,
        medicine_name: "Paracetamol 500mg",
        batch_id: 280,
        batch_number: "GR-A",
        expiry_date: "2027-06-30",
        quantity: 100,
        unit_cost: 12.5,
        line_total: 1250.0,
        batch_created: true,
        ...overrides,
    };
}

/** A full 201 body from POST /api/v1/purchases. */
export function makeRecordedReceipt(overrides = {}) {
    const lines = overrides.lines ?? [makeReceiptLine()];
    return {
        purchase_id: 81,
        supplier_id: 11,
        supplier_name: "Medlife Distributors",
        invoice_number: "INV-001",
        purchase_date: "2026-09-14",
        total_amount: lines.reduce((sum, l) => sum + l.line_total, 0),
        total_units: lines.reduce((sum, l) => sum + l.quantity, 0),
        created_at: "2026-09-14T19:57:10",
        ...overrides,
        lines,
    };
}

/** A row in the recent-receipts panel. */
export function makeReceiptSummary(overrides = {}) {
    return {
        purchase_id: 81,
        supplier_id: 11,
        supplier_name: "Medlife Distributors",
        invoice_number: "INV-001",
        purchase_date: "2026-09-14",
        total_amount: 1960.0,
        line_count: 2,
        ...overrides,
    };
}

/**
 * Mock the four calls the goods receipt page makes.
 *
 * `postResponse` and `postStatus` drive the write. A test that wants to prove a
 * 409 reaches the screen sets both, exactly as the backend would answer.
 */
export function mockPurchasesApi({
    medicines = [makeCatalogueMedicine()],
    suppliers = [{ id: 1, name: "Sun Pharma", phone: "022000000" }],
    recent = [],
    postResponse = makeRecordedReceipt(),
    postStatus = 201,
    medicinesStatus = 200,
    networkError = false,
    hold = null,
} = {}) {
    const mock = vi.fn(async (url, options) => {
        if (networkError) throw new TypeError("Failed to fetch");
        const target = String(url);

        if (options?.method === "POST" && target.includes("/api/v1/purchases")) {
            if (hold) await hold;
            return jsonResponse(postResponse, postStatus);
        }
        if (target.includes("/api/v1/purchases/suppliers")) {
            return jsonResponse(suppliers, 200);
        }
        if (target.includes("/api/v1/purchases")) {
            return jsonResponse(recent, 200);
        }
        if (target.includes("/api/v1/medicines")) {
            if (hold) await hold;
            return jsonResponse(medicines, medicinesStatus);
        }
        throw new Error(`Unexpected request in test: ${target}`);
    });

    vi.stubGlobal("fetch", mock);
    return mock;
}

// ── Medicine catalogue writes ────────────────────────────────────────────────

/**
 * Mock the two calls the medicines page makes: the list, and the create.
 *
 * `listSequence` lets a test give a different body to the second GET, which is
 * how the "table refreshes after a create" assertion is made without mocking our
 * own API module.
 */
export function mockMedicinesApi({
    medicines = [makeCatalogueMedicine()],
    listSequence = null,
    postResponse = makeCatalogueMedicine({ id: 101, name: "Shelcal 500" }),
    postStatus = 201,
    listStatus = 200,
    networkError = false,
    hold = null,
} = {}) {
    let listCall = 0;

    const mock = vi.fn(async (url, options) => {
        if (networkError) throw new TypeError("Failed to fetch");

        if (options?.method === "POST") {
            if (hold) await hold;
            return jsonResponse(postResponse, postStatus);
        }

        const body = listSequence ? listSequence[Math.min(listCall, listSequence.length - 1)] : medicines;
        listCall += 1;
        return jsonResponse(body, listStatus);
    });

    vi.stubGlobal("fetch", mock);
    return mock;
}
