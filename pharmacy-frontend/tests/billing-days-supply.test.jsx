import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BillingPage from "@/../pages/index";
import { toDaysSupply } from "@/lib/api/billing";

/**
 * Frontend tests for M6.1 — days supply and WhatsApp consent on the billing page.
 *
 * The mock boundary is `fetch`, per the project rule, so `lib/api/billing.js` is
 * REAL code under test. That matters more here than usual: `toDaysSupply` is
 * where an empty input becomes an explicit `null`, and mocking `confirmSale`
 * would skip exactly the conversion most likely to be wrong.
 *
 * The load-bearing assertion is that an untouched days-supply box sends `null`
 * and not `0`, not `""`, and not the catalogue default. `null` means "unknown"
 * and tells the future refill engine to stay silent about that line.
 */

const MEDICINE = {
    id: 17,
    name: "Crocin 500",
    mrp: 20.0,
    hsn_code: "30049099",
    manufacturer: "GSK",
    default_days_supply: 5,
    created_at: "2026-01-01T00:00:00",
};

function pricedLine(overrides = {}) {
    return {
        name: "Crocin 500",
        quantity: 2,
        unit: "strip",
        medicine_id: 17,
        batch_id: 1,
        batch_number: "B1",
        expiry_date: "2027-01-01",
        unit_price: 20.0,
        line_total: 40.0,
        needs_confirm: false,
        matched_from: null,
        candidates: [],
        default_days_supply: 5,
        ...overrides,
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

/** Mocks the three calls the billing page makes: catalogue, price-item, confirm. */
function mockBillingApi({
    medicines = [MEDICINE],
    line = pricedLine(),
    confirmStatus = 201,
    confirmBody = null,
} = {}) {
    const mock = vi.fn(async (url, options) => {
        const target = String(url);
        if (target.includes("/api/v1/billing/price-item")) {
            return jsonResponse(line, 200);
        }
        if (target.includes("/api/v1/billing/confirm")) {
            return jsonResponse(
                confirmBody ?? { sale_id: 1, total_amount: 40, items: [], errors: [] },
                confirmStatus,
            );
        }
        if (target.includes("/api/v1/medicines")) {
            return jsonResponse(medicines, 200);
        }
        throw new Error(`Unexpected request in test: ${target}`);
    });
    vi.stubGlobal("fetch", mock);
    return mock;
}

function confirmBody(mock) {
    const call = mock.mock.calls.find(([url]) => String(url).includes("/billing/confirm"));
    return JSON.parse(call[1].body);
}

/** Render, pick the medicine, add it to the bill. */
async function addLine(user) {
    render(<BillingPage />);
    const picker = await screen.findByPlaceholderText(/search/i);
    await user.click(picker);
    await user.type(picker, "Crocin");
    await user.click(await screen.findByText("Crocin 500"));
    await user.click(screen.getByRole("button", { name: /add/i }));
    return screen.findByLabelText("Days supply for Crocin 500");
}

beforeEach(() => {
    vi.unstubAllGlobals();
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// toDaysSupply — the conversion that decides "unknown"
// ---------------------------------------------------------------------------

describe("toDaysSupply", () => {
    it("turns an empty box into an explicit null", () => {
        // NOT 0. Zero fails backend validation by design, so that "unknown" has
        // exactly one spelling all the way down the stack.
        expect(toDaysSupply("")).toBeNull();
        expect(toDaysSupply(null)).toBeNull();
        expect(toDaysSupply(undefined)).toBeNull();
    });

    it("parses the string an <input type=number> actually yields", () => {
        expect(toDaysSupply("5")).toBe(5);
        expect(toDaysSupply(30)).toBe(30);
    });

    it("treats junk and out-of-range low values as unknown rather than sending them", () => {
        expect(toDaysSupply("abc")).toBeNull();
        expect(toDaysSupply("0")).toBeNull();
        expect(toDaysSupply("-5")).toBeNull();
        expect(toDaysSupply("2.5")).toBeNull();
    });
});

// ---------------------------------------------------------------------------
// The days supply field
// ---------------------------------------------------------------------------

describe("days supply field", () => {
    it("pre-fills from the medicine's catalogue default", async () => {
        const user = userEvent.setup();
        mockBillingApi();
        const field = await addLine(user);

        expect(field).toHaveValue(5);
    });

    it("is empty when the medicine has no default", async () => {
        // Most of the catalogue: an as-needed painkiller has no course length.
        const user = userEvent.setup();
        mockBillingApi({ line: pricedLine({ default_days_supply: null }) });
        const field = await addLine(user);

        expect(field).toHaveValue(null);
    });

    it("shows 'unknown' as the placeholder, never a zero", async () => {
        // A 0 in the box would read as a number the pharmacist chose.
        const user = userEvent.setup();
        mockBillingApi({ line: pricedLine({ default_days_supply: null }) });
        const field = await addLine(user);

        expect(field).toHaveAttribute("placeholder", "unknown");
    });

    it("lets the pharmacist override the default", async () => {
        const user = userEvent.setup();
        const mock = mockBillingApi();
        const field = await addLine(user);

        await user.clear(field);
        await user.type(field, "30");
        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => expect(confirmBody(mock).items[0].days_supply).toBe(30));
    });

    it("sends null when the pharmacist clears the box", async () => {
        // "I do not know how long this lasts" must survive as null.
        const user = userEvent.setup();
        const mock = mockBillingApi();
        const field = await addLine(user);

        await user.clear(field);
        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => {
            const sent = confirmBody(mock).items[0];
            expect(sent.days_supply).toBeNull();
            expect(sent.days_supply).not.toBe(0);
        });
    });

    it("sends the pre-filled default when the pharmacist accepts it", async () => {
        const user = userEvent.setup();
        const mock = mockBillingApi();
        await addLine(user);

        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => expect(confirmBody(mock).items[0].days_supply).toBe(5));
    });
});

// ---------------------------------------------------------------------------
// Consent
// ---------------------------------------------------------------------------

describe("whatsapp consent", () => {
    it("is unchecked by default", async () => {
        // Consent is never implied by the customer handing over a phone number.
        const user = userEvent.setup();
        mockBillingApi();
        await addLine(user);

        expect(screen.getByRole("checkbox", { name: /whatsapp refill reminders/i })).not
            .toBeChecked();
    });

    it("is disabled until a phone number is entered", async () => {
        // Without a phone there is no customer row to attach the consent to.
        const user = userEvent.setup();
        mockBillingApi();
        await addLine(user);

        const box = screen.getByRole("checkbox", { name: /whatsapp refill reminders/i });
        expect(box).toBeDisabled();

        await user.type(screen.getByLabelText("Phone (optional)"), "9876543210");
        expect(box).toBeEnabled();
    });

    it("sends whatsapp_opt_in false when not ticked", async () => {
        const user = userEvent.setup();
        const mock = mockBillingApi();
        await addLine(user);

        await user.type(screen.getByLabelText("Phone (optional)"), "9876543210");
        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => expect(confirmBody(mock).whatsapp_opt_in).toBe(false));
    });

    it("sends whatsapp_opt_in true when ticked", async () => {
        const user = userEvent.setup();
        const mock = mockBillingApi();
        await addLine(user);

        await user.type(screen.getByLabelText("Phone (optional)"), "9876543210");
        await user.click(screen.getByRole("checkbox", { name: /whatsapp refill reminders/i }));
        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => expect(confirmBody(mock).whatsapp_opt_in).toBe(true));
    });

    it("explains why the checkbox is unavailable", async () => {
        const user = userEvent.setup();
        mockBillingApi();
        await addLine(user);

        expect(screen.getByText(/enter a phone number to enable/i)).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// Validation surfaced from the server
// ---------------------------------------------------------------------------

describe("server validation", () => {
    it("shows an error when the backend rejects the phone number", async () => {
        const user = userEvent.setup();
        mockBillingApi({
            confirmStatus: 422,
            confirmBody: { detail: "not a valid 10-digit Indian mobile number" },
        });
        await addLine(user);

        await user.type(screen.getByLabelText("Phone (optional)"), "12345");
        await user.click(screen.getByRole("button", { name: /save bill/i }));

        expect(await screen.findByText(/could not be saved|not valid/i)).toBeInTheDocument();
    });

    it("does not leak SQL or a traceback on failure", async () => {
        const user = userEvent.setup();
        mockBillingApi({
            confirmStatus: 500,
            confirmBody: { detail: "SELECT * FROM sale_items; Traceback: pymysql" },
        });
        await addLine(user);

        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => {
            const body = document.body.textContent.toLowerCase();
            expect(body).not.toContain("select *");
            expect(body).not.toContain("traceback");
            expect(body).not.toContain("pymysql");
        });
    });
});

// ---------------------------------------------------------------------------
// The rest of billing must be untouched
// ---------------------------------------------------------------------------

describe("existing billing behaviour", () => {
    it("still sends the priced line fields unchanged", async () => {
        const user = userEvent.setup();
        const mock = mockBillingApi();
        await addLine(user);

        await user.click(screen.getByRole("button", { name: /save bill/i }));

        await waitFor(() => {
            const sent = confirmBody(mock).items[0];
            expect(sent.medicine_id).toBe(17);
            expect(sent.batch_id).toBe(1);
            expect(sent.quantity).toBe(2);
            // Price is still never sent — the server recomputes it.
            expect(sent).not.toHaveProperty("unit_price");
        });
    });

    it("keeps the grand total row aligned after adding the new column", async () => {
        const user = userEvent.setup();
        mockBillingApi();
        await addLine(user);

        const table = screen.getByRole("table");
        expect(within(table).getByText("Days supply")).toBeInTheDocument();
        expect(within(table).getByText("Total")).toBeInTheDocument();
    });
});
