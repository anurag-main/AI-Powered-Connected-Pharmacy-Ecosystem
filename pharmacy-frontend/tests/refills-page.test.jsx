import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RefillsPage from "@/../pages/refills";
import { toQuery } from "@/lib/api/refill";
import { deferred } from "./helpers";

/**
 * Tests for /refills (M6.2).
 *
 * `fetch` is the mock boundary per the project rule, so `lib/api/refill.js` —
 * including `toQuery` — is real code under test. Mocking `getRefillCandidates`
 * would skip the filter-to-query-parameter mapping, which is the one place a
 * frontend bug would actually hide on this page.
 *
 * These assert DISPLAY, never business logic. Whether someone is genuinely 4
 * days overdue belongs to the backend's 52 refill tests; these prove the screen
 * asks the right question and prints the answer it was given, unchanged.
 */

function makeCandidate(overrides = {}) {
    return {
        customer_id: 1,
        customer_name: "Anurag",
        customer_phone: "9876543210",
        medicine_id: 17,
        medicine_name: "Crocin 500",
        source_sale_id: 10,
        source_sale_item_id: 100,
        last_purchase_date: "2026-09-01",
        days_supply: 10,
        expected_refill_date: "2026-09-11",
        days_overdue: 4,
        status: "due",
        contactability: "contactable",
        reason: "Ran out 4 day(s) ago, on 2026-09-11.",
        ...overrides,
    };
}

function makeResponse(overrides = {}) {
    const candidates = overrides.candidates ?? [makeCandidate()];
    return {
        as_of: "2026-09-15",
        lookback_days: 400,
        summary: {
            customers_reviewed: 41,
            purchases_reviewed: 1139,
            due: candidates.length,
            not_due: 3,
            unknown_duration: 852,
            contactable_due: candidates.length,
        },
        notes: ["Anonymous walk-in sales are not included."],
        ...overrides,
        candidates,
    };
}

function jsonResponse(body, status = 200) {
    return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
        headers: { get: (n) => (n === "X-Request-ID" ? "test-req-id" : null) },
    };
}

function mockRefillApi({ body = makeResponse(), status = 200, networkError = false, hold = null } = {}) {
    const mock = vi.fn(async (url) => {
        if (networkError) throw new TypeError("Failed to fetch");
        if (!String(url).includes("/api/v1/refill/candidates")) {
            throw new Error(`Unexpected request in test: ${url}`);
        }
        if (hold) await hold;
        return jsonResponse(body, status);
    });
    vi.stubGlobal("fetch", mock);
    return mock;
}

/** The query string of the most recent candidates request. */
function lastQuery(mock) {
    const calls = mock.mock.calls.filter(([url]) =>
        String(url).includes("/api/v1/refill/candidates"),
    );
    return new URL(String(calls[calls.length - 1][0]), "http://x").searchParams;
}

beforeEach(() => {
    vi.unstubAllGlobals();
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// toQuery — the mapping the page depends on
// ---------------------------------------------------------------------------

describe("toQuery", () => {
    it("maps the three views to the two backend flags", () => {
        expect(toQuery("due")).toEqual({ due_only: true, contactable_only: false });
        expect(toQuery("contactable")).toEqual({ due_only: true, contactable_only: true });
        expect(toQuery("all")).toEqual({ due_only: false, contactable_only: false });
    });

    it("defaults an unknown view to due-only rather than showing everything", () => {
        // Failing open would dump every not-due row onto a screen meant to be a
        // short action list.
        expect(toQuery("nonsense")).toEqual({ due_only: true, contactable_only: false });
    });
});

// ---------------------------------------------------------------------------
// The four states
// ---------------------------------------------------------------------------

describe("states", () => {
    it("shows skeletons while loading", async () => {
        const gate = deferred();
        mockRefillApi({ hold: gate.promise });

        render(<RefillsPage />);
        expect(screen.getByTestId("refills-loading")).toBeInTheDocument();

        gate.resolve();
        await screen.findByTestId("refill-row");
    });

    it("renders candidates on success", async () => {
        mockRefillApi();
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getByText("Anurag")).toBeInTheDocument();
        expect(within(row).getByText("Crocin 500")).toBeInTheDocument();
    });

    it("shows a reassuring empty state, not an error", async () => {
        // Nobody due is good news for a pharmacy, and must not look like a fault.
        mockRefillApi({ body: makeResponse({ candidates: [] }) });
        render(<RefillsPage />);

        expect(await screen.findByTestId("refills-empty")).toBeInTheDocument();
        expect(screen.getByText(/nobody is due right now/i)).toBeInTheDocument();
    });

    it("shows an error when the request fails", async () => {
        mockRefillApi({ status: 500 });
        render(<RefillsPage />);

        expect(await screen.findByRole("alert")).toBeInTheDocument();
    });

    it("reports a network failure plainly", async () => {
        mockRefillApi({ networkError: true });
        render(<RefillsPage />);

        expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach the server/i);
    });

    it("never leaks SQL or a traceback", async () => {
        mockRefillApi({
            status: 500,
            body: { detail: "SELECT * FROM sale_items; Traceback: pymysql password=root" },
        });
        render(<RefillsPage />);

        await screen.findByRole("alert");
        const body = document.body.textContent.toLowerCase();
        for (const leak of ["select *", "traceback", "pymysql", "password="]) {
            expect(body).not.toContain(leak);
        }
    });
});

// ---------------------------------------------------------------------------
// Request parameters
// ---------------------------------------------------------------------------

describe("request parameters", () => {
    it("asks for due-only on first load", async () => {
        const mock = mockRefillApi();
        render(<RefillsPage />);
        await screen.findByTestId("refill-row");

        expect(lastQuery(mock).get("due_only")).toBe("true");
        expect(lastQuery(mock).get("contactable_only")).toBe("false");
    });

    it("re-requests with new flags when the view changes", async () => {
        const user = userEvent.setup();
        const mock = mockRefillApi();
        render(<RefillsPage />);
        await screen.findByTestId("refill-row");

        await user.selectOptions(screen.getByLabelText("Show"), "contactable");

        await waitFor(() => expect(lastQuery(mock).get("contactable_only")).toBe("true"));
    });

    it("asks for everything when the view is 'all'", async () => {
        const user = userEvent.setup();
        const mock = mockRefillApi();
        render(<RefillsPage />);
        await screen.findByTestId("refill-row");

        await user.selectOptions(screen.getByLabelText("Show"), "all");

        await waitFor(() => expect(lastQuery(mock).get("due_only")).toBe("false"));
    });
});

// ---------------------------------------------------------------------------
// Displaying backend values unchanged
// ---------------------------------------------------------------------------

describe("display", () => {
    it("prints the backend's days_overdue rather than recomputing it", async () => {
        // The dates below are deliberately inconsistent with 99 days. If the page
        // ever starts computing overdue from the dates, this fails — which is
        // the point.
        mockRefillApi({
            body: makeResponse({
                candidates: [makeCandidate({ days_overdue: 99 })],
            }),
        });
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getByText("99d")).toBeInTheDocument();
    });

    it("shows 'today' for zero overdue, never '0d'", async () => {
        // 0 is a real answer meaning "runs out today"; "0d" reads as missing data.
        mockRefillApi({
            body: makeResponse({ candidates: [makeCandidate({ days_overdue: 0 })] }),
        });
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getByText("today")).toBeInTheDocument();
        expect(within(row).queryByText("0d")).not.toBeInTheDocument();
    });

    it("shows an em-dash for an unknown refill date, never a zero", async () => {
        mockRefillApi({
            body: makeResponse({
                candidates: [
                    makeCandidate({
                        status: "unknown_duration",
                        expected_refill_date: null,
                        days_overdue: null,
                        days_supply: null,
                        reason: "No days supply was recorded on the last purchase.",
                    }),
                ],
            }),
        });
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
        expect(within(row).getByText("No duration")).toBeInTheDocument();
    });

    it("shows the reason sentence from the engine", async () => {
        mockRefillApi();
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getByText(/Ran out 4 day\(s\) ago/)).toBeInTheDocument();
    });

    it("renders status and contactability as separate badges", async () => {
        // The two are orthogonal: a customer can be due AND unreachable.
        mockRefillApi({
            body: makeResponse({
                candidates: [makeCandidate({ contactability: "opted_out" })],
            }),
        });
        render(<RefillsPage />);

        const row = await screen.findByTestId("refill-row");
        expect(within(row).getByText("Due")).toBeInTheDocument();
        expect(within(row).getByText("Opted out")).toBeInTheDocument();
    });

    it("takes the summary from the API, not from the visible rows", async () => {
        // The table is filtered and limited; summing it would under-report.
        mockRefillApi({
            body: makeResponse({
                candidates: [makeCandidate()],
                summary: {
                    customers_reviewed: 41,
                    purchases_reviewed: 1139,
                    due: 143,
                    not_due: 3,
                    unknown_duration: 852,
                    contactable_due: 90,
                },
            }),
        });
        render(<RefillsPage />);

        const card = await screen.findByTestId("summary-due");
        expect(within(card).getByText("143")).toBeInTheDocument();
        expect(screen.getByText(/Showing 1 of 143 due/)).toBeInTheDocument();
    });

    it("shows the engine's notes about what it could not see", async () => {
        mockRefillApi();
        render(<RefillsPage />);

        expect(await screen.findByText(/walk-in sales are not included/i)).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// The M6.2 boundary
// ---------------------------------------------------------------------------

describe("architectural boundary", () => {
    it("offers no way to send anything", async () => {
        // M6.2 decides WHO. If a Send button appears here, the refill domain has
        // started depending on a channel and voice can no longer reuse it.
        mockRefillApi();
        render(<RefillsPage />);
        await screen.findByTestId("refill-row");

        expect(screen.queryByRole("button", { name: /send|whatsapp|message|remind/i })).toBeNull();
        expect(document.body.textContent.toLowerCase()).not.toContain("whatsapp");
    });
});
