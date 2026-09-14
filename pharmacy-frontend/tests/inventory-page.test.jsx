/**
 * The Inventory Risk page, end to end inside the browser half of the stack.
 *
 * Rendered as a plain React component — `pages/inventory.jsx` keeps its shell in a
 * `getLayout` static, so no Next router or font loader is involved.
 *
 * Only `fetch` is mocked. `useInventoryRisk`, `lib/api/inventory.js` and
 * `lib/api/client.js` all run for real, which is what lets these tests catch a
 * malformed request body or a mis-mapped error message.
 *
 * What is deliberately NOT tested here: whether capital at risk, days of cover or
 * the ranking are correct. That is backend domain logic with its own 151 tests.
 * These tests prove the UI asks the right question and shows the answer it was
 * given, unchanged — and, specifically for this page, that it never turns a
 * backend `null` into a number.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import InventoryPage from "../pages/inventory.jsx";
import {
    bodyOf,
    deferred,
    initOf,
    makeInventoryExplanation,
    makeInventoryItem,
    makeInventoryReport,
    mockInventoryApi,
    urlOf,
} from "./helpers.js";

const REPORT = "/api/v1/inventory/report";
const EXPLAIN = "/api/v1/inventory/explain";

// ---------------------------------------------------------------------------
// 1. Loading
// ---------------------------------------------------------------------------

describe("loading", () => {
    it("shows skeletons while the report request is in flight", async () => {
        const gate = deferred();
        const fetchMock = mockInventoryApi({ hold: gate.promise });

        const { container } = render(<InventoryPage />);

        expect(
            container.querySelectorAll('[data-slot="skeleton"]').length
        ).toBeGreaterThan(0);
        expect(screen.queryByRole("table")).not.toBeInTheDocument();
        expect(fetchMock).toHaveBeenCalled();

        gate.resolve();

        await screen.findByRole("table");
        expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(0);
    });

    it("shows the table before the AI summary has arrived", async () => {
        // The reason the page makes two calls instead of one: the report measured
        // 44ms against the explanation's 5.5s, so a slow model must not hold up the
        // numbers.
        const slowExplain = deferred();
        const fetchMock = vi.fn(async (url) => {
            if (String(url).includes(REPORT)) {
                return {
                    ok: true,
                    status: 200,
                    json: async () => makeInventoryReport(),
                    headers: { get: () => "req-1" },
                };
            }
            await slowExplain.promise;
            return {
                ok: true,
                status: 200,
                json: async () => makeInventoryExplanation(),
                headers: { get: () => "req-2" },
            };
        });
        vi.stubGlobal("fetch", fetchMock);

        render(<InventoryPage />);

        // Table is up with real figures while the paragraph is still loading.
        const table = await screen.findByRole("table");
        expect(within(table).getByText("Paracetamol 500")).toBeInTheDocument();
        expect(screen.getByRole("status")).toBeInTheDocument();

        slowExplain.resolve();
        await screen.findByText("Rs 62,750 is at risk across the shop.");
    });

    it("disables the Analyze button while a report is loading", async () => {
        const gate = deferred();
        mockInventoryApi({ hold: gate.promise });

        render(<InventoryPage />);

        expect(screen.getByRole("button", { name: /analysing/i })).toBeDisabled();

        gate.resolve();
        await screen.findByRole("table");
        expect(screen.getByRole("button", { name: /analyze/i })).toBeEnabled();
    });
});

// ---------------------------------------------------------------------------
// 2. Success — backend values displayed unchanged
// ---------------------------------------------------------------------------

describe("success", () => {
    it("renders the backend's figures without recomputing them", async () => {
        // Deliberately inconsistent numbers: excess x cost does NOT equal
        // capital_at_risk here, and cover is not stock / velocity. If the page did
        // its own arithmetic it would "correct" these and the test would fail.
        mockInventoryApi({
            report: makeInventoryReport({
                items: [
                    makeInventoryItem({
                        medicine_name: "TEST-MEDICINE-XYZ",
                        stock_quantity: 83,
                        daily_velocity: 1.25,
                        days_of_cover: 240.0,
                        excess_units: 77,
                        capital_at_risk: 123456.78,
                        stock_age_days: 311,
                        risk_level: "high",
                    }),
                ],
            }),
        });

        render(<InventoryPage />);
        const table = await screen.findByRole("table");
        const row = within(table).getByText("TEST-MEDICINE-XYZ").closest("tr");

        expect(within(row).getByText("83")).toBeInTheDocument();
        expect(within(row).getByText("1.25/day")).toBeInTheDocument();
        expect(within(row).getByText("240d")).toBeInTheDocument();
        expect(within(row).getByText("77")).toBeInTheDocument();
        expect(within(row).getByText("₹1,23,456.78")).toBeInTheDocument();
        expect(within(row).getByText("311d")).toBeInTheDocument();
        expect(within(row).getByText("High")).toBeInTheDocument();
    });

    it("shows the KPI cards from the report's own totals, not from the rows", async () => {
        // counts_by_risk describes the whole shop; items is one truncated row. A
        // page deriving cards from items would show 1 critical and Rs 34,000.
        mockInventoryApi({
            report: makeInventoryReport({
                items: [makeInventoryItem()],
                medicines_reviewed: 96,
                total_inventory_value: 2838654.45,
                total_capital_at_risk: 2387886.26,
                counts_by_risk: {
                    dead: 4,
                    critical: 75,
                    high: 6,
                    medium: 5,
                    healthy: 6,
                },
            }),
        });

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(screen.getByText("₹28,38,654.45")).toBeInTheDocument();
        expect(screen.getByText("₹23,87,886.26")).toBeInTheDocument();
        expect(screen.getByText("Across 96 medicine(s)")).toBeInTheDocument();
        // dead + critical + high, from counts_by_risk.
        expect(screen.getByText("85")).toBeInTheDocument();
        expect(screen.getByText("75 critical · 6 high")).toBeInTheDocument();
    });

    it("states the filtered subtotal separately from the shop total", async () => {
        // The mistake the real backend round trip caught: conflating "at risk across
        // the shop" with "at risk in the rows shown".
        mockInventoryApi({
            report: makeInventoryReport({
                items: [makeInventoryItem()],
                items_matching_filter: 4,
                total_capital_at_risk: 2387886.26,
                capital_at_risk_in_view: 10045.41,
            }),
        });

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(
            screen.getByText(/Showing 1 of 4 matching medicine\(s\)/)
        ).toBeInTheDocument();
        expect(screen.getByText(/₹10,045\.41 at risk/)).toBeInTheDocument();
    });

    it("renders a null days_of_cover as unknown, never as zero", async () => {
        // The single most important display rule on this page. The backend returns
        // null when nothing is selling, and `Number(null) || 0` — the usual React
        // shortcut — would print "0d", asserting a fact the backend refused to state.
        mockInventoryApi({
            report: makeInventoryReport({
                items: [
                    makeInventoryItem({
                        medicine_name: "NEVER-SOLD-XYZ",
                        days_of_cover: null,
                        daily_velocity: 0.0,
                        ever_sold: false,
                        last_sale_date: null,
                        days_since_last_sale: null,
                        risk_level: "dead",
                    }),
                ],
            }),
        });

        render(<InventoryPage />);
        const table = await screen.findByRole("table");
        const row = within(table).getByText("NEVER-SOLD-XYZ").closest("tr");

        expect(within(row).queryByText("0d")).not.toBeInTheDocument();
        expect(within(row).queryByText("Infinityd")).not.toBeInTheDocument();
        expect(within(row).queryByText("NaNd")).not.toBeInTheDocument();
        expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
        expect(within(row).getByText("Dead")).toBeInTheDocument();
    });

    it("renders an unknown stock age as unknown, never as zero", async () => {
        mockInventoryApi({
            report: makeInventoryReport({
                items: [
                    makeInventoryItem({
                        medicine_name: "NO-RECEIPT-XYZ",
                        stock_age_days: null,
                        oldest_receipt_date: null,
                    }),
                ],
            }),
        });

        render(<InventoryPage />);
        const table = await screen.findByRole("table");
        const row = within(table).getByText("NO-RECEIPT-XYZ").closest("tr");

        expect(within(row).queryByText("0d")).not.toBeInTheDocument();
        expect(within(row).getByText("—")).toBeInTheDocument();
    });

    it("keeps the backend's row order rather than re-sorting", async () => {
        mockInventoryApi({
            report: makeInventoryReport({
                items: [
                    makeInventoryItem({
                        medicine_id: 1,
                        medicine_name: "FIRST-XYZ",
                        capital_at_risk: 100.0,
                    }),
                    makeInventoryItem({
                        medicine_id: 2,
                        medicine_name: "SECOND-XYZ",
                        capital_at_risk: 999999.0,
                    }),
                ],
            }),
        });

        render(<InventoryPage />);
        const table = await screen.findByRole("table");
        const names = within(table)
            .getAllByText(/-XYZ$/)
            .map((el) => el.textContent);

        // SECOND has far more money at risk. A client that re-sorted would flip
        // these, and then disagree with the AI summary above it.
        expect(names).toEqual(["FIRST-XYZ", "SECOND-XYZ"]);
    });

    it("shows the reasons and detail when a row is expanded", async () => {
        const user = userEvent.setup();
        mockInventoryApi({
            report: makeInventoryReport({
                items: [
                    makeInventoryItem({
                        risk_reasons: ["REASON-ALPHA", "REASON-BETA"],
                        sellable_quantity: 360,
                        target_stock: 60,
                    }),
                ],
            }),
        });

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(screen.queryByText("REASON-ALPHA")).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /why paracetamol/i }));

        expect(screen.getByText("REASON-ALPHA")).toBeInTheDocument();
        expect(screen.getByText("REASON-BETA")).toBeInTheDocument();
        expect(screen.getByText("360 of 400")).toBeInTheDocument();
    });

    it("labels the AI paragraph as generated, and the figures as calculated", async () => {
        mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByText("Rs 62,750 is at risk across the shop.");

        expect(screen.getByText(/Written by AI from the figures above/)).toBeInTheDocument();
        expect(screen.getByText(/confidence 80%/)).toBeInTheDocument();
    });

    it("does not print the model's markdown asterisks on screen", async () => {
        // Caught in a real browser against the live provider. The backend field is a
        // plain string and gpt-4o-mini writes **bold** into it; a plain <p> renders
        // the asterisks. A prompt instruction is a request, not a guarantee, so the
        // view copes with whatever arrives.
        mockInventoryApi({
            explain: makeInventoryExplanation({
                answer:
                    "Rs 100 is at risk. 1. **MEDICINE-ALPHA**: 5 units. 2. **MEDICINE-BETA**: 9 units.",
            }),
        });

        const { container } = render(<InventoryPage />);
        await screen.findByText(/Rs 100 is at risk/);

        expect(container.textContent).not.toContain("**");
        expect(screen.getByText("MEDICINE-ALPHA").tagName).toBe("STRONG");
        expect(screen.getByText("MEDICINE-BETA").tagName).toBe("STRONG");
    });

    it("leaves prose without markdown as a single unbroken sentence", async () => {
        // The formatter must not fragment ordinary text, or a caller asserting on a
        // whole sentence would stop finding it.
        mockInventoryApi({
            explain: makeInventoryExplanation({
                answer: "Nothing here is formatted and it should stay one node.",
            }),
        });

        render(<InventoryPage />);

        await screen.findByText(
            "Nothing here is formatted and it should stay one node."
        );
    });

    it("passes the report's notes through untouched", async () => {
        mockInventoryApi({
            report: makeInventoryReport({
                notes: ["NOTE-ALPHA about stock age", "NOTE-BETA about negatives"],
            }),
        });

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(screen.getByText("NOTE-ALPHA about stock age")).toBeInTheDocument();
        expect(screen.getByText("NOTE-BETA about negatives")).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// 3. Empty
// ---------------------------------------------------------------------------

describe("empty", () => {
    it("shows a business-meaningful empty state, not 'no data'", async () => {
        mockInventoryApi({
            report: makeInventoryReport({
                items: [],
                items_matching_filter: 0,
                counts_by_risk: { dead: 0, critical: 0, high: 0, medium: 0, healthy: 0 },
            }),
        });

        render(<InventoryPage />);

        await screen.findByText("No inventory needs attention in this view.");
        expect(screen.queryByRole("table")).not.toBeInTheDocument();
        expect(screen.queryByText(/no data/i)).not.toBeInTheDocument();
    });

    it("still shows the KPI cards when nothing matched the filter", async () => {
        // The shop still holds stock even if this filter matched none of it.
        mockInventoryApi({
            report: makeInventoryReport({
                items: [],
                total_inventory_value: 2838654.45,
                counts_by_risk: { dead: 4, critical: 0, high: 0, medium: 0, healthy: 0 },
            }),
        });

        render(<InventoryPage />);

        await screen.findByText("No inventory needs attention in this view.");
        expect(screen.getByText("₹28,38,654.45")).toBeInTheDocument();
    });

    it("does not ask for an AI explanation when there is nothing to explain", async () => {
        const fetchMock = mockInventoryApi({
            report: makeInventoryReport({ items: [] }),
        });

        render(<InventoryPage />);
        await screen.findByText("No inventory needs attention in this view.");

        const explainCalls = fetchMock.mock.calls.filter(([url]) =>
            String(url).includes(EXPLAIN)
        );
        expect(explainCalls).toHaveLength(0);
    });
});

// ---------------------------------------------------------------------------
// 4. Error
// ---------------------------------------------------------------------------

describe("error", () => {
    it("shows a friendly message when the network is down", async () => {
        mockInventoryApi({ networkError: true });

        render(<InventoryPage />);

        await screen.findByText("Unable to load the inventory analysis.");
        expect(
            screen.getByText("Cannot reach the server. Check that the backend is running.")
        ).toBeInTheDocument();
    });

    it("maps a 422 to the validation message", async () => {
        mockInventoryApi({ reportStatus: 422, report: { detail: "bad enum" } });

        render(<InventoryPage />);

        await screen.findByText("That request was not valid. Try different filters.");
    });

    it("maps a 500 to the server message", async () => {
        mockInventoryApi({ reportStatus: 500, report: {} });

        render(<InventoryPage />);

        await screen.findByText("The server could not complete this request.");
    });

    it("never leaks backend internals to the screen", async () => {
        mockInventoryApi({
            reportStatus: 500,
            report: {
                detail:
                    "(pymysql.err.OperationalError) SELECT batches.cost_price FROM batches",
                traceback: "File app/repositories/inventory_repository.py line 120",
            },
        });

        const { container } = render(<InventoryPage />);
        await screen.findByText("The server could not complete this request.");

        const text = container.textContent;
        expect(text).not.toMatch(/SELECT/i);
        expect(text).not.toMatch(/pymysql/i);
        expect(text).not.toMatch(/Traceback|\.py/i);
    });

    it("offers a retry that re-requests the report", async () => {
        const user = userEvent.setup();
        mockInventoryApi({ networkError: true });

        render(<InventoryPage />);
        await screen.findByText("Unable to load the inventory analysis.");

        // Second attempt succeeds.
        const fetchMock = mockInventoryApi();
        await user.click(screen.getByRole("button", { name: /try again/i }));

        await screen.findByRole("table");
        expect(fetchMock).toHaveBeenCalled();
    });

    it("keeps the table when only the AI explanation fails", async () => {
        // The point of two calls: an LLM outage costs a paragraph, not the report.
        mockInventoryApi({ explainStatus: 500, explain: {} });

        render(<InventoryPage />);
        await screen.findByRole("table");

        await screen.findByText(/The figures above are unaffected/);
        expect(screen.getByText("Paracetamol 500")).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// 5. Correct API parameters
// ---------------------------------------------------------------------------

describe("request construction", () => {
    it("posts the default query to the report endpoint on mount", async () => {
        const fetchMock = mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(urlOf(fetchMock, REPORT)).toBe(
            "http://localhost:8000/api/v1/inventory/report"
        );
        expect(initOf(fetchMock, REPORT).method).toBe("POST");
        expect(initOf(fetchMock, REPORT).headers["Content-Type"]).toBe(
            "application/json"
        );
        expect(bodyOf(fetchMock, REPORT)).toEqual({
            target_cover_days: 60,
            sort: "risk",
            limit: 10,
        });
    });

    it("omits risk_level rather than sending an empty string", async () => {
        // The backend field is an enum or null. "" is neither, and would 422.
        const fetchMock = mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByRole("table");

        expect(bodyOf(fetchMock, REPORT)).not.toHaveProperty("risk_level");
    });

    it("sends the selected filters when Analyze is pressed", async () => {
        const user = userEvent.setup();
        const fetchMock = mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByRole("table");

        await user.selectOptions(screen.getByLabelText("Risk level"), "dead");
        await user.selectOptions(screen.getByLabelText("Sort by"), "capital_at_risk");
        await user.selectOptions(screen.getByLabelText("Show"), "50");
        await user.selectOptions(screen.getByLabelText("Aim to hold"), "30");

        await user.click(screen.getByRole("button", { name: /analyze/i }));

        await waitFor(() => {
            const bodies = fetchMock.mock.calls
                .filter(([url]) => String(url).includes(REPORT))
                .map(([, init]) => JSON.parse(init.body));
            expect(bodies.at(-1)).toEqual({
                target_cover_days: 30,
                risk_level: "dead",
                sort: "capital_at_risk",
                limit: 50,
            });
        });
    });

    it("does not fire a request merely because a dropdown changed", async () => {
        const user = userEvent.setup();
        const fetchMock = mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByRole("table");

        const before = fetchMock.mock.calls.filter(([url]) =>
            String(url).includes(REPORT)
        ).length;

        await user.selectOptions(screen.getByLabelText("Risk level"), "dead");
        await user.selectOptions(screen.getByLabelText("Sort by"), "stock_age");

        const after = fetchMock.mock.calls.filter(([url]) =>
            String(url).includes(REPORT)
        ).length;
        expect(after).toBe(before);
    });

    it("sends the identical query to /explain that it sent to /report", async () => {
        // This is what makes the prose describe the rows on screen: the backend
        // skips its planner when handed a query, so the two must match exactly.
        const user = userEvent.setup();
        const fetchMock = mockInventoryApi();

        render(<InventoryPage />);
        await screen.findByRole("table");

        await user.selectOptions(screen.getByLabelText("Risk level"), "critical");
        await user.click(screen.getByRole("button", { name: /analyze/i }));

        await waitFor(() => {
            const reports = fetchMock.mock.calls
                .filter(([url]) => String(url).includes(REPORT))
                .map(([, init]) => JSON.parse(init.body));
            const explains = fetchMock.mock.calls
                .filter(([url]) => String(url).includes(EXPLAIN))
                .map(([, init]) => JSON.parse(init.body));
            expect(explains.at(-1)).toEqual(reports.at(-1));
        });
    });

    it("only offers filter values the backend will accept", async () => {
        mockInventoryApi();
        render(<InventoryPage />);
        await screen.findByRole("table");

        const levels = within(screen.getByLabelText("Risk level"))
            .getAllByRole("option")
            .map((o) => o.value)
            .filter(Boolean);

        // InventoryRiskLevel exactly — notably NOT the expiry agent's "expired"/"low".
        expect(levels).toEqual(["dead", "critical", "high", "medium", "healthy"]);
        expect(levels).not.toContain("expired");
        expect(levels).not.toContain("low");
    });
});
