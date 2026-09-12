/**
 * The Expiry Risk page, end to end inside the browser half of the stack.
 *
 * Rendered as a plain React component — `pages/expiry.jsx` keeps its shell in a
 * `getLayout` static, so no Next router or font loader is involved.
 *
 * Only `fetch` is mocked. `useExpiryRisk`, `lib/api/expiry.js` and
 * `lib/api/client.js` all run for real, which is what lets these tests catch a
 * malformed request body or a mis-mapped error message.
 *
 * What is deliberately NOT tested here: whether excess, value at risk or the
 * ranking are correct. That is backend domain logic and it has its own 196 tests.
 * These tests only prove the UI asks the right question and shows the answer it
 * was given, unchanged.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import ExpiryPage from "../pages/expiry.jsx";
import {
    bodyOf,
    deferred,
    initOf,
    makeExplanation,
    makeItem,
    makeReport,
    mockApi,
    urlOf,
} from "./helpers.js";

// ---------------------------------------------------------------------------
// 1. Loading
// ---------------------------------------------------------------------------

describe("loading", () => {
    it("shows skeletons while the report request is in flight", async () => {
        const gate = deferred();
        const fetchMock = mockApi({ hold: gate.promise });

        const { container } = render(<ExpiryPage />);

        // The request is open, so the page must be showing its loading state.
        expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0);
        expect(screen.queryByRole("table")).not.toBeInTheDocument();
        expect(fetchMock).toHaveBeenCalled();

        gate.resolve();

        // ...and it must go away once the data lands.
        await screen.findByRole("table");
        expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBe(0);
    });

    it("shows the table before the AI summary has arrived", async () => {
        // The reason the page makes two calls instead of one: a slow model must not
        // hold up the numbers.
        const slowExplain = deferred();
        const fetchMock = mockApi();
        fetchMock.mockImplementation(async (url) => {
            const json = (b) => ({
                ok: true,
                status: 200,
                json: async () => b,
                headers: { get: () => "req-1" },
            });
            if (String(url).includes("/report")) return json(makeReport());
            await slowExplain.promise;
            return json(makeExplanation());
        });

        render(<ExpiryPage />);

        await screen.findByRole("table");
        expect(screen.getByText("Writing the summary…")).toBeInTheDocument();

        slowExplain.resolve();
        await screen.findByText("One batch carries excess stock.");
    });
});

// ---------------------------------------------------------------------------
// 2. Successful results
// ---------------------------------------------------------------------------

describe("successful results", () => {
    it("renders the batches the backend returned", async () => {
        mockApi({
            report: makeReport({
                items: [
                    makeItem({
                        batch_number: "P1",
                        medicine_name: "Paracetamol 500",
                        expiry_date: "2026-10-14",
                        days_to_expiry: 5,
                        stock_quantity: 30,
                        estimated_demand: 10,
                        potential_excess: 20,
                        value_at_risk: 200.0,
                        risk_level: "critical",
                    }),
                ],
            }),
        });

        render(<ExpiryPage />);

        const table = await screen.findByRole("table");
        const row = within(table).getByRole("row", { name: /Paracetamol 500/ });

        expect(within(row).getByText("P1")).toBeInTheDocument();
        expect(within(row).getByText("14 Oct 2026")).toBeInTheDocument();
        expect(within(row).getByText("5d")).toBeInTheDocument();
        expect(within(row).getByText("30")).toBeInTheDocument(); // stock
        expect(within(row).getByText("20")).toBeInTheDocument(); // excess
        expect(within(row).getByText("₹200.00")).toBeInTheDocument();
        expect(within(row).getByText("Critical")).toBeInTheDocument();
    });

    it("renders the summary cards from the backend's counts, not from the rows", async () => {
        // `limit` truncates `items`, so counting rows would under-report. The cards
        // must read counts_by_risk / total_* instead. This is the frontend half of
        // the backend's test_counts_survive_a_limit.
        mockApi({
            report: makeReport({
                items: [makeItem()], // one row on screen...
                total_batches_reviewed: 152,
                total_at_risk: 133,
                total_value_at_risk: 1302905.3,
                counts_by_risk: { expired: 34, critical: 7, high: 12, medium: 3, low: 96 },
            }),
        });

        render(<ExpiryPage />);
        await screen.findByRole("table");

        expect(screen.getByText("152")).toBeInTheDocument(); // batches reviewed
        expect(screen.getByText("7")).toBeInTheDocument(); // critical
        expect(screen.getByText("12")).toBeInTheDocument(); // high
        expect(screen.getByText("₹13,02,905.30")).toBeInTheDocument(); // value at risk
        expect(screen.getByText(/34 already expired/)).toBeInTheDocument();
        expect(screen.getByText(/Across 133 batch/)).toBeInTheDocument();
    });

    it("shows expired stock as elapsed days rather than a negative number", async () => {
        mockApi({
            report: makeReport({
                items: [makeItem({ days_to_expiry: -10, risk_level: "expired" })],
            }),
        });

        render(<ExpiryPage />);
        await screen.findByRole("table");

        expect(screen.getByText("10d ago")).toBeInTheDocument();
        expect(screen.queryByText("-10d")).not.toBeInTheDocument();
    });

    it("keeps the backend's ranking instead of re-sorting", async () => {
        // The report arrives ranked. A client that re-sorted would disagree with the
        // AI summary printed directly above it.
        mockApi({
            report: makeReport({
                items: [
                    makeItem({ batch_id: 1, batch_number: "C1", value_at_risk: 100 }),
                    makeItem({ batch_id: 2, batch_number: "A1", value_at_risk: 9999 }),
                    makeItem({ batch_id: 3, batch_number: "B1", value_at_risk: 500 }),
                ],
            }),
        });

        render(<ExpiryPage />);
        const table = await screen.findByRole("table");

        const order = within(table)
            .getAllByRole("row")
            .slice(1) // drop the header
            .map((row) => within(row).getAllByRole("cell")[1].textContent);

        expect(order).toEqual(["C1", "A1", "B1"]);
    });
});

// ---------------------------------------------------------------------------
// 3. Empty state
// ---------------------------------------------------------------------------

describe("empty state", () => {
    it("shows the empty-state message, not a headerless table", async () => {
        mockApi({
            report: makeReport({
                items: [],
                window_days: 30,
                total_batches_reviewed: 0,
                total_at_risk: 0,
                total_value_at_risk: 0,
                counts_by_risk: { expired: 0, critical: 0, high: 0, medium: 0, low: 0 },
            }),
        });

        render(<ExpiryPage />);

        expect(
            await screen.findByText("No stock is at expiry risk in this view.")
        ).toBeInTheDocument();
        expect(screen.getByText(/Nothing expiring within 30 days/)).toBeInTheDocument();
        expect(screen.queryByRole("table")).not.toBeInTheDocument();
    });

    it("does not ask the model to explain an empty report", async () => {
        // No rows means nothing to narrate, and a model call would be wasted money.
        const fetchMock = mockApi({ report: makeReport({ items: [] }) });

        render(<ExpiryPage />);
        await screen.findByText("No stock is at expiry risk in this view.");

        const explains = fetchMock.mock.calls.filter(([url]) =>
            String(url).includes("/explain")
        );
        expect(explains).toHaveLength(0);
    });
});

// ---------------------------------------------------------------------------
// 4. Error state
// ---------------------------------------------------------------------------

describe("error state", () => {
    it("shows a readable error and hides the backend's own detail", async () => {
        mockApi({
            reportStatus: 500,
            report: {
                detail:
                    'Traceback (most recent call last): sqlalchemy.exc.OperationalError: '
                    + '(pymysql.err.OperationalError) (1045, "Access denied for user '
                    + "'root'@'localhost' (using password: YES)\") "
                    + "[SQL: SELECT batches.id FROM batches]",
            },
        });

        render(<ExpiryPage />);

        expect(await screen.findByText("Unable to load expiry analysis.")).toBeInTheDocument();
        expect(
            screen.getByText("The server could not complete this request.")
        ).toBeInTheDocument();

        // None of the server's internals reach the screen.
        const shown = document.body.textContent;
        expect(shown).not.toMatch(/Traceback/);
        expect(shown).not.toMatch(/pymysql/);
        expect(shown).not.toMatch(/SELECT/);
        expect(shown).not.toMatch(/Access denied/);
        expect(shown).not.toMatch(/password/i);
    });

    it("reports an unreachable backend as a network problem", async () => {
        mockApi({ networkError: true });

        render(<ExpiryPage />);

        expect(
            await screen.findByText("Cannot reach the server. Check that the backend is running.")
        ).toBeInTheDocument();
    });

    it("surfaces the request id so a bug report is traceable", async () => {
        mockApi({ reportStatus: 500, report: {} });

        render(<ExpiryPage />);
        await screen.findByText("Unable to load expiry analysis.");

        expect(screen.getByText(/ref test-req-id/)).toBeInTheDocument();
    });

    it("retries when Try again is pressed", async () => {
        const user = userEvent.setup();
        const fetchMock = mockApi({ reportStatus: 500, report: {} });

        render(<ExpiryPage />);
        await screen.findByText("Unable to load expiry analysis.");

        // The backend comes back.
        fetchMock.mockImplementation(async (url) => ({
            ok: true,
            status: 200,
            json: async () =>
                String(url).includes("/report") ? makeReport() : makeExplanation(),
            headers: { get: () => "req-2" },
        }));

        await user.click(screen.getByRole("button", { name: /Try again/ }));

        await screen.findByRole("table");
        expect(screen.queryByText("Unable to load expiry analysis.")).not.toBeInTheDocument();
    });

    it("keeps the figures on screen when only the AI summary fails", async () => {
        // An outage costs the paragraph, never the report.
        mockApi({ explainStatus: 500, explain: { detail: "model unavailable" } });

        render(<ExpiryPage />);
        await screen.findByRole("table");

        await waitFor(() =>
            expect(
                screen.getByText(/The server could not complete this request\./)
            ).toBeInTheDocument()
        );

        // The table is untouched, and the error did not replace the page.
        expect(screen.getByRole("table")).toBeInTheDocument();
        expect(screen.queryByText("Unable to load expiry analysis.")).not.toBeInTheDocument();
        expect(screen.getByText(/figures above are unaffected/)).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// 5. Correct API parameters
// ---------------------------------------------------------------------------

describe("request parameters", () => {
    it("posts the default query to /api/v1/expiry/report on first load", async () => {
        const fetchMock = mockApi();

        render(<ExpiryPage />);
        await screen.findByRole("table");

        expect(urlOf(fetchMock, "/expiry/report")).toBe(
            "http://localhost:8000/api/v1/expiry/report"
        );
        expect(initOf(fetchMock, "/expiry/report").method).toBe("POST");
        expect(initOf(fetchMock, "/expiry/report").headers["Content-Type"]).toBe(
            "application/json"
        );
        expect(bodyOf(fetchMock, "/expiry/report")).toEqual({
            window_days: 30,
            limit: 10,
            include_expired: true,
        });
    });

    it("sends the filters the user chose", async () => {
        const user = userEvent.setup();
        const fetchMock = mockApi();

        render(<ExpiryPage />);
        await screen.findByRole("table");
        fetchMock.mockClear();

        await user.selectOptions(screen.getByLabelText("Expiring within"), "7");
        await user.selectOptions(screen.getByLabelText("Risk level"), "critical");
        await user.selectOptions(screen.getByLabelText("Show"), "50");
        await user.click(screen.getByRole("button", { name: /Analyze/ }));

        await waitFor(() => expect(fetchMock).toHaveBeenCalled());

        expect(bodyOf(fetchMock, "/expiry/report")).toEqual({
            window_days: 7,
            limit: 50,
            include_expired: true,
            risk_level: "critical",
        });
    });

    it("omits risk_level entirely when All levels is selected", async () => {
        // The backend field is an enum or null; "" is neither and would be a 422.
        const user = userEvent.setup();
        const fetchMock = mockApi();

        render(<ExpiryPage />);
        await screen.findByRole("table");
        fetchMock.mockClear();

        await user.selectOptions(screen.getByLabelText("Risk level"), "high");
        await user.selectOptions(screen.getByLabelText("Risk level"), "");
        await user.click(screen.getByRole("button", { name: /Analyze/ }));

        await waitFor(() => expect(fetchMock).toHaveBeenCalled());

        expect(bodyOf(fetchMock, "/expiry/report")).not.toHaveProperty("risk_level");
    });

    it("sends the identical query to both endpoints", async () => {
        // If these drift, the paragraph describes a different window from the table.
        const user = userEvent.setup();
        const fetchMock = mockApi();

        render(<ExpiryPage />);
        await screen.findByRole("table");
        fetchMock.mockClear();

        await user.selectOptions(screen.getByLabelText("Expiring within"), "365");
        await user.click(screen.getByRole("button", { name: /Analyze/ }));

        await waitFor(() =>
            expect(
                fetchMock.mock.calls.some(([u]) => String(u).includes("/explain"))
            ).toBe(true)
        );

        expect(bodyOf(fetchMock, "/expiry/report")).toEqual(
            bodyOf(fetchMock, "/expiry/explain")
        );
    });

    it("does not fire a request merely because a filter changed", async () => {
        // Adjusting three dropdowns should cost one report, not three.
        const user = userEvent.setup();
        const fetchMock = mockApi();

        render(<ExpiryPage />);
        await screen.findByRole("table");
        fetchMock.mockClear();

        await user.selectOptions(screen.getByLabelText("Expiring within"), "90");
        await user.selectOptions(screen.getByLabelText("Show"), "25");

        expect(fetchMock).not.toHaveBeenCalled();
    });
});

// ---------------------------------------------------------------------------
// 6. Backend values displayed unchanged
// ---------------------------------------------------------------------------

describe("backend values are displayed unchanged", () => {
    it("shows distinctive figures exactly as the API sent them", async () => {
        mockApi({
            report: makeReport({
                items: [
                    makeItem({
                        medicine_name: "TEST-MEDICINE-XYZ",
                        batch_number: "TEST-BATCH-9",
                        days_to_expiry: 17,
                        stock_quantity: 83,
                        estimated_demand: 41,
                        potential_excess: 42,
                        value_at_risk: 123456.78,
                        risk_level: "high",
                    }),
                ],
                total_batches_reviewed: 999,
                total_at_risk: 777,
                total_value_at_risk: 123456.78,
                counts_by_risk: { expired: 0, critical: 0, high: 1, medium: 0, low: 0 },
            }),
        });

        render(<ExpiryPage />);
        const table = await screen.findByRole("table");
        const row = within(table).getByRole("row", { name: /TEST-MEDICINE-XYZ/ });

        expect(within(row).getByText("TEST-BATCH-9")).toBeInTheDocument();
        expect(within(row).getByText("17d")).toBeInTheDocument();
        expect(within(row).getByText("83")).toBeInTheDocument();
        expect(within(row).getByText("41")).toBeInTheDocument();
        expect(within(row).getByText("42")).toBeInTheDocument();
        expect(within(row).getByText("₹1,23,456.78")).toBeInTheDocument();
        expect(within(row).getByText("High")).toBeInTheDocument();

        // Totals come straight off the response too.
        expect(screen.getByText("999")).toBeInTheDocument();
        expect(screen.getByText(/Across 777 batch/)).toBeInTheDocument();
    });

    it("does not recompute excess from stock minus demand", async () => {
        // 83 - 41 is 42, but the backend allocates demand in FEFO order across a
        // medicine's batches, so its excess is frequently NOT that subtraction. The
        // UI must print what it was given.
        mockApi({
            report: makeReport({
                items: [
                    makeItem({
                        medicine_name: "FEFO-CHECK",
                        stock_quantity: 200,
                        estimated_demand: 30,
                        potential_excess: 170,
                        value_at_risk: 1700.0,
                    }),
                ],
            }),
        });

        render(<ExpiryPage />);
        const table = await screen.findByRole("table");
        const row = within(table).getByRole("row", { name: /FEFO-CHECK/ });

        expect(within(row).getByText("170")).toBeInTheDocument();
        expect(within(row).getByText("₹1,700.00")).toBeInTheDocument();
    });

    it("shows the report's notes and the AI answer verbatim", async () => {
        mockApi({
            report: makeReport({
                notes: ["No sales history at all for: TEST-MEDICINE-XYZ."],
            }),
            explain: makeExplanation({
                answer: "Rs 123456.78 is at risk across one batch.",
                confidence: 0.62,
            }),
        });

        render(<ExpiryPage />);

        expect(
            await screen.findByText("Rs 123456.78 is at risk across one batch.")
        ).toBeInTheDocument();
        expect(
            screen.getByText("No sales history at all for: TEST-MEDICINE-XYZ.")
        ).toBeInTheDocument();
        expect(screen.getByText("confidence 62%")).toBeInTheDocument();
    });

    it("prints the row's reasons and recommendation from the backend", async () => {
        const user = userEvent.setup();
        mockApi({
            report: makeReport({
                items: [
                    makeItem({
                        reasons: ["UNIQUE-REASON-ONE", "UNIQUE-REASON-TWO"],
                        recommendation: "UNIQUE-RECOMMENDATION",
                    }),
                ],
            }),
        });

        render(<ExpiryPage />);
        await screen.findByRole("table");

        await user.click(screen.getByRole("button", { name: /Why P1 is critical risk/ }));

        expect(screen.getByText("UNIQUE-REASON-ONE")).toBeInTheDocument();
        expect(screen.getByText("UNIQUE-REASON-TWO")).toBeInTheDocument();
        expect(screen.getByText("UNIQUE-RECOMMENDATION")).toBeInTheDocument();
    });
});
