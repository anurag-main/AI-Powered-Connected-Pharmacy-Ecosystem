import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ReceivePage from "@/../pages/receive";
import {
    deferred,
    makeCatalogueMedicine,
    makeReceiptLine,
    makeReceiptSummary,
    makeRecordedReceipt,
    mockPurchasesApi,
} from "./helpers";

/**
 * Tests for the goods receipt page.
 *
 * The mock boundary is `fetch`, so `lib/api/purchases.js` and `lib/api/client.js`
 * are the real code under test — including `toReceiptPayload`, which is where a
 * wrong request body would actually come from.
 *
 * These assert three things and deliberately not a fourth:
 *   - the right REQUEST is built from what was typed
 *   - the server's RESPONSE is displayed unchanged
 *   - the failure paths are safe (no double submit, nothing lost on error)
 * They do not assert whether a receipt is valid. That is the backend's job and it
 * has its own 46 tests for it; asserting it here would be asserting a copy.
 */

async function fillOneLine(user, { batch = "GR-A", expiry = "2027-06-30", qty = "100", cost = "12.50" } = {}) {
    await user.selectOptions(screen.getByLabelText("Medicine"), "17");
    await user.type(screen.getByLabelText("Batch no."), batch);
    await user.type(screen.getByLabelText("Expiry"), expiry);
    await user.type(screen.getByLabelText("Qty"), qty);
    await user.type(screen.getByLabelText("Cost / unit"), cost);
}

async function chooseExistingSupplier(user) {
    await user.selectOptions(screen.getByLabelText("Supplier"), "1");
}

/** Wait for the reference data to land so the form is rendered. */
async function renderPage() {
    render(<ReceivePage />);
    await screen.findByLabelText("Supplier");
}

function postCalls(mock) {
    return mock.mock.calls.filter(([, options]) => options?.method === "POST");
}

function postBody(mock) {
    return JSON.parse(postCalls(mock)[0][1].body);
}

beforeEach(() => {
    vi.unstubAllGlobals();
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Loading and reference data
// ---------------------------------------------------------------------------

describe("loading", () => {
    it("shows skeletons until the catalogue arrives", async () => {
        const gate = deferred();
        mockPurchasesApi({ hold: gate.promise });

        render(<ReceivePage />);
        expect(screen.getByTestId("receive-loading")).toBeInTheDocument();

        gate.resolve();
        await screen.findByLabelText("Supplier");
    });

    it("lists the medicines from the catalogue in the picker", async () => {
        mockPurchasesApi({
            medicines: [
                makeCatalogueMedicine({ id: 17, name: "Paracetamol 500mg" }),
                makeCatalogueMedicine({ id: 18, name: "Dolo 650" }),
            ],
        });
        await renderPage();

        const picker = screen.getByLabelText("Medicine");
        expect(within(picker).getByRole("option", { name: "Dolo 650" })).toBeInTheDocument();
    });

    it("lists suppliers plus a new-supplier option", async () => {
        mockPurchasesApi({ suppliers: [{ id: 1, name: "Sun Pharma", phone: null }] });
        await renderPage();

        const picker = screen.getByLabelText("Supplier");
        expect(within(picker).getByRole("option", { name: "Sun Pharma" })).toBeInTheDocument();
        expect(within(picker).getByRole("option", { name: "+ New supplier…" })).toBeInTheDocument();
    });

    it("shows an error when the catalogue cannot be loaded", async () => {
        mockPurchasesApi({ medicinesStatus: 500 });
        render(<ReceivePage />);

        expect(await screen.findByText(/Could not load the medicine catalogue/i)).toBeInTheDocument();
    });

    it("still renders the form when only the supplier list fails", async () => {
        // Suppliers failing is survivable — the new-supplier path still works.
        mockPurchasesApi({ suppliers: "not an array" });
        await renderPage();

        expect(screen.getByLabelText("Supplier")).toBeInTheDocument();
        expect(screen.queryByText(/Could not load the medicine catalogue/i)).not.toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// The request body — where a frontend bug actually hides
// ---------------------------------------------------------------------------

describe("request body", () => {
    it("sends numbers as numbers, not strings", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        const body = postBody(mock);

        // An <input> always yields a string; sending "100" would 422 on the
        // backend's integer validation and look like a mystery.
        expect(body.lines[0].quantity).toBe(100);
        expect(body.lines[0].unit_cost).toBe(12.5);
        expect(body.lines[0].medicine_id).toBe(17);
    });

    it("sends supplier_id when an existing supplier is chosen, and never both", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        const body = postBody(mock);

        expect(body.supplier_id).toBe(1);
        expect(body).not.toHaveProperty("supplier_name");
    });

    it("sends supplier_name when a new supplier is typed, and never both", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await user.selectOptions(screen.getByLabelText("Supplier"), "__new__");
        await user.type(screen.getByLabelText("New supplier name"), "Medlife Distributors");
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        const body = postBody(mock);

        expect(body.supplier_name).toBe("Medlife Distributors");
        expect(body).not.toHaveProperty("supplier_id");
    });

    it("omits optional fields rather than sending empty strings", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        const body = postBody(mock);

        // "" would fail max_length=None validation differently than absent does.
        expect(body).not.toHaveProperty("invoice_number");
        expect(body).not.toHaveProperty("purchase_date");
    });

    it("never sends a total — money is the server's decision", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        const body = postBody(mock);

        expect(body).not.toHaveProperty("total_amount");
        expect(body).not.toHaveProperty("total_units");
        expect(body.lines[0]).not.toHaveProperty("line_total");
    });

    it("trims whitespace from the batch number", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user, { batch: "  GR-A  " });
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock).lines[0].batch_number).toBe("GR-A");
    });

    it("sends every line when more than one is added", async () => {
        const user = userEvent.setup();
        const mock = mockPurchasesApi({
            medicines: [
                makeCatalogueMedicine({ id: 17, name: "Paracetamol 500mg" }),
                makeCatalogueMedicine({ id: 18, name: "Dolo 650" }),
            ],
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /add line/i }));

        const rows = screen.getAllByTestId("receipt-line");
        expect(rows).toHaveLength(2);

        const second = within(rows[1]);
        await user.selectOptions(second.getByLabelText("Medicine"), "18");
        await user.type(second.getByLabelText("Batch no."), "GR-B");
        await user.type(second.getByLabelText("Expiry"), "2027-03-31");
        await user.type(second.getByLabelText("Qty"), "50");
        await user.type(second.getByLabelText("Cost / unit"), "14.20");

        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock).lines).toHaveLength(2);
    });
});

// ---------------------------------------------------------------------------
// Submit guarding
// ---------------------------------------------------------------------------

describe("submit guarding", () => {
    it("keeps the button disabled until the form is complete", async () => {
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        const button = screen.getByRole("button", { name: /record receipt/i });
        expect(button).toBeDisabled();

        await chooseExistingSupplier(user);
        expect(button).toBeDisabled(); // supplier alone is not enough

        await fillOneLine(user);
        expect(button).toBeEnabled();
    });

    it("does not submit twice on a double click", async () => {
        // This is the important one. A second identical request would NOT fail —
        // the backend would treat it as a top-up of the same batch and silently
        // double the shop's stock.
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);

        // Re-stub only now, so the POST is the slow call rather than the
        // reference loads. `hold` in this helper gates every request it can, and
        // holding the catalogue would just stall the form before it renders.
        const slow = deferred();
        const mock = mockPurchasesApi({ hold: slow.promise });

        const button = screen.getByRole("button", { name: /record receipt/i });
        await user.click(button);
        await user.click(button);
        slow.resolve();

        await waitFor(() => expect(screen.getByTestId("recorded-receipt")).toBeInTheDocument());
        expect(postCalls(mock)).toHaveLength(1);
    });
});

// ---------------------------------------------------------------------------
// Success — displaying what the server recorded
// ---------------------------------------------------------------------------

describe("success", () => {
    it("shows the receipt the server returned, not what was typed", async () => {
        const user = userEvent.setup();
        mockPurchasesApi({
            postResponse: makeRecordedReceipt({
                purchase_id: 99,
                supplier_name: "Sun Pharma",
                // Two lines so the line total and the invoice total are
                // different numbers — otherwise the assertion below matches two
                // cells and cannot tell which one it found.
                lines: [
                    makeReceiptLine({ line_total: 1250.0, quantity: 100 }),
                    makeReceiptLine({ batch_id: 281, batch_number: "GR-B", line_total: 710.0, quantity: 50 }),
                ],
            }),
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        const panel = await screen.findByTestId("recorded-receipt");
        expect(within(panel).getByText(/receipt #99/i)).toBeInTheDocument();
        expect(within(panel).getByText("₹1,250.00")).toBeInTheDocument();
        expect(within(panel).getByText("₹1,960.00")).toBeInTheDocument(); // server total
    });

    it("displays the server total even when it differs from the line figures", async () => {
        // Pinning the no-frontend-arithmetic rule. If the page ever starts
        // summing the lines itself, this test fails — which is the point.
        const user = userEvent.setup();
        mockPurchasesApi({
            postResponse: makeRecordedReceipt({
                total_amount: 4242.42,
                lines: [makeReceiptLine({ line_total: 1250.0 })],
            }),
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        const panel = await screen.findByTestId("recorded-receipt");
        expect(within(panel).getByText("₹4,242.42")).toBeInTheDocument();
    });

    it("distinguishes a new batch from a topped-up one", async () => {
        const user = userEvent.setup();
        mockPurchasesApi({
            postResponse: makeRecordedReceipt({
                lines: [makeReceiptLine({ batch_created: false })],
            }),
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        const panel = await screen.findByTestId("recorded-receipt");
        expect(within(panel).getByText("topped up")).toBeInTheDocument();
    });

    it("clears the line fields after a successful save", async () => {
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await screen.findByTestId("recorded-receipt");
        expect(screen.getByLabelText("Batch no.")).toHaveValue("");
    });
});

// ---------------------------------------------------------------------------
// Failure — and what must survive it
// ---------------------------------------------------------------------------

describe("failure", () => {
    it("shows the server's domain message for a 409 conflict", async () => {
        const user = userEvent.setup();
        const detail =
            "Batch 'GR-A' of 'Paracetamol 500mg' is already on the shelf expiring 2027-06-30, " +
            "but this receipt says 2028-01-01. One of the two is wrong.";
        mockPurchasesApi({ postStatus: 409, postResponse: { detail } });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        expect(await screen.findByRole("alert")).toHaveTextContent(/already on the shelf/i);
    });

    it("shows the server's domain message for a 422 rule failure", async () => {
        const user = userEvent.setup();
        mockPurchasesApi({
            postStatus: 422,
            postResponse: { detail: "unit_cost 1250.00 for 'Paracetamol 500mg' exceeds its MRP 30.00." },
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        expect(await screen.findByRole("alert")).toHaveTextContent(/exceeds its MRP/i);
    });

    it("falls back to generic wording when detail is a Pydantic array", async () => {
        // Rendering the array itself would put [object Object] on the screen.
        const user = userEvent.setup();
        mockPurchasesApi({
            postStatus: 422,
            postResponse: { detail: [{ loc: ["body", "lines", 0, "quantity"], msg: "too small" }] },
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        const alert = await screen.findByRole("alert");
        expect(alert).not.toHaveTextContent("[object Object]");
        expect(alert).toHaveTextContent(/not valid/i);
    });

    it("does not surface a 500's detail", async () => {
        // A 500's detail is exactly the text that leaks internals.
        const user = userEvent.setup();
        mockPurchasesApi({
            postStatus: 500,
            postResponse: { detail: "psycopg2.errors: relation batches does not exist" },
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        const alert = await screen.findByRole("alert");
        expect(alert).not.toHaveTextContent(/psycopg2/i);
        expect(alert).not.toHaveTextContent(/relation batches/i);
    });

    it("keeps everything typed when the save fails", async () => {
        // Wiping a ten-line invoice to punish one typo is how people stop using
        // a system. The failure path must be non-destructive.
        const user = userEvent.setup();
        mockPurchasesApi({ postStatus: 409, postResponse: { detail: "Conflict on the shelf." } });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user, { batch: "GR-KEEP" });
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await screen.findByRole("alert");
        expect(screen.getByLabelText("Batch no.")).toHaveValue("GR-KEEP");
        expect(screen.getByLabelText("Qty")).toHaveValue(100);
    });

    it("shows a network failure without blaming the pharmacist", async () => {
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);

        mockPurchasesApi({ networkError: true });
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach the server/i);
    });

    it("never renders SQL, a traceback or credentials", async () => {
        const user = userEvent.setup();
        mockPurchasesApi({
            postStatus: 500,
            postResponse: { detail: "SELECT * FROM batches; Traceback (most recent call last): password=root" },
        });
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);
        await user.click(screen.getByRole("button", { name: /record receipt/i }));

        await screen.findByRole("alert");
        const body = document.body.textContent.toLowerCase();
        for (const leak of ["select *", "traceback", "password=", "pymysql"]) {
            expect(body).not.toContain(leak);
        }
    });
});

// ---------------------------------------------------------------------------
// Line editing
// ---------------------------------------------------------------------------

describe("line editing", () => {
    it("adds and removes lines", async () => {
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await user.click(screen.getByRole("button", { name: /add line/i }));
        expect(screen.getAllByTestId("receipt-line")).toHaveLength(2);

        await user.click(screen.getByRole("button", { name: /remove line 2/i }));
        expect(screen.getAllByTestId("receipt-line")).toHaveLength(1);
    });

    it("never leaves the form with zero lines", async () => {
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await user.click(screen.getByRole("button", { name: /remove line 1/i }));
        expect(screen.getAllByTestId("receipt-line")).toHaveLength(1);
    });

    it("shows no running total anywhere on the form", async () => {
        // A preview total would be a second implementation of money arithmetic
        // in a browser, and the pharmacist would believe it over the server.
        const user = userEvent.setup();
        mockPurchasesApi();
        await renderPage();

        await chooseExistingSupplier(user);
        await fillOneLine(user);

        expect(screen.queryByTestId("recorded-receipt")).not.toBeInTheDocument();
        expect(screen.queryByText("₹1,250.00")).not.toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// Recent receipts
// ---------------------------------------------------------------------------

describe("recent receipts", () => {
    it("lists what the server returned", async () => {
        mockPurchasesApi({
            recent: [makeReceiptSummary({ purchase_id: 81, supplier_name: "Abbott", total_amount: 1960.0 })],
        });
        await renderPage();

        expect(await screen.findByText("Abbott")).toBeInTheDocument();
        expect(screen.getByText("₹1,960.00")).toBeInTheDocument();
    });

    it("says so when there are none", async () => {
        mockPurchasesApi({ recent: [] });
        await renderPage();

        expect(screen.getByText(/no receipts recorded yet/i)).toBeInTheDocument();
    });
});
