import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MedicinesPage from "@/../pages/medicines";
import { deferred, makeCatalogueMedicine, mockMedicinesApi } from "./helpers";

/**
 * Tests for the medicine catalogue page and its add form.
 *
 * The mock boundary is `fetch`, so `lib/api/medicines.js` is real code under
 * test — including the type coercion in `createMedicine`, which is where a wrong
 * request body would actually come from.
 */

async function openForm(user) {
    render(<MedicinesPage />);
    await screen.findByRole("button", { name: /add medicine/i });
    await user.click(screen.getByRole("button", { name: /add medicine/i }));
    return screen.getByTestId("add-medicine-form");
}

async function fillForm(user, { name = "Shelcal 500", mrp = "145", hsn = "30049099", maker = "" } = {}) {
    await user.type(screen.getByLabelText("Name"), name);
    await user.type(screen.getByLabelText("MRP"), mrp);
    await user.type(screen.getByLabelText("HSN code"), hsn);
    if (maker) await user.type(screen.getByLabelText(/Manufacturer/), maker);
}

function postCalls(mock) {
    return mock.mock.calls.filter(([, options]) => options?.method === "POST");
}

function postBody(mock) {
    return JSON.parse(postCalls(mock)[0][1].body);
}

/** The submit button inside the form, not the one that opened it. */
function submitButton() {
    const form = screen.getByTestId("add-medicine-form");
    return within(form).getByRole("button", { name: /^add medicine$/i });
}


beforeEach(() => {
    vi.unstubAllGlobals();
});

afterEach(() => {
    vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// The existing table
// ---------------------------------------------------------------------------

describe("catalogue table", () => {
    it("lists what the server returned", async () => {
        mockMedicinesApi({
            medicines: [makeCatalogueMedicine({ id: 17, name: "Paracetamol 500mg", mrp: 30.0 })],
        });
        render(<MedicinesPage />);

        expect(await screen.findByText("Paracetamol 500mg")).toBeInTheDocument();
        expect(screen.getByText("₹30.00")).toBeInTheDocument();
    });

    it("shows an em-dash for a missing manufacturer, never 'null'", async () => {
        mockMedicinesApi({ medicines: [makeCatalogueMedicine({ manufacturer: null })] });
        render(<MedicinesPage />);

        await screen.findByText("Paracetamol 500mg");
        expect(screen.getByText("—")).toBeInTheDocument();
        expect(screen.queryByText("null")).not.toBeInTheDocument();
    });

    it("says the page does not add stock", async () => {
        // "I added it but it shows nothing in stock" is the obvious next
        // confusion, so the page answers it before it is asked.
        mockMedicinesApi();
        render(<MedicinesPage />);

        expect(await screen.findByText(/does not\s+add stock/i)).toBeInTheDocument();
    });
});

// ---------------------------------------------------------------------------
// The form
// ---------------------------------------------------------------------------

describe("add form", () => {
    it("is closed until asked for", async () => {
        mockMedicinesApi();
        render(<MedicinesPage />);

        await screen.findByRole("button", { name: /add medicine/i });
        expect(screen.queryByTestId("add-medicine-form")).not.toBeInTheDocument();
    });

    it("opens and closes", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);

        expect(screen.getByTestId("add-medicine-form")).toBeInTheDocument();
        await user.click(screen.getByRole("button", { name: /close/i }));
        expect(screen.queryByTestId("add-medicine-form")).not.toBeInTheDocument();
    });

    it("leaves the HSN code blank rather than guessing a tax code", async () => {
        // A default that is right most of the time is wrong some of the time,
        // silently, and it surfaces at GST filing rather than at entry.
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);

        expect(screen.getByLabelText("HSN code")).toHaveValue("");
    });

    it("keeps submit disabled until the required fields are valid", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);

        expect(submitButton()).toBeDisabled();

        await user.type(screen.getByLabelText("Name"), "Shelcal 500");
        await user.type(screen.getByLabelText("MRP"), "145");
        expect(submitButton()).toBeDisabled(); // HSN still missing

        await user.type(screen.getByLabelText("HSN code"), "3004909");
        expect(submitButton()).toBeDisabled(); // 7 digits, not 8

        await user.type(screen.getByLabelText("HSN code"), "9");
        expect(submitButton()).toBeEnabled();
    });

    it("rejects a zero or negative MRP before sending", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);

        await fillForm(user, { mrp: "0" });
        expect(submitButton()).toBeDisabled();
    });
});

// ---------------------------------------------------------------------------
// The request
// ---------------------------------------------------------------------------

describe("request body", () => {
    it("sends mrp as a number, not a string", async () => {
        const user = userEvent.setup();
        const mock = mockMedicinesApi();
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock).mrp).toBe(145);
        expect(postBody(mock).name).toBe("Shelcal 500");
    });

    it("omits the manufacturer rather than sending an empty string", async () => {
        const user = userEvent.setup();
        const mock = mockMedicinesApi();
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock)).not.toHaveProperty("manufacturer");
    });

    it("includes the manufacturer when given", async () => {
        const user = userEvent.setup();
        const mock = mockMedicinesApi();
        await openForm(user);

        await fillForm(user, { maker: "Torrent" });
        await user.click(submitButton());

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock).manufacturer).toBe("Torrent");
    });

    it("trims whitespace from the name", async () => {
        const user = userEvent.setup();
        const mock = mockMedicinesApi();
        await openForm(user);

        await fillForm(user, { name: "  Shelcal 500  " });
        await user.click(submitButton());

        await waitFor(() => expect(postCalls(mock)).toHaveLength(1));
        expect(postBody(mock).name).toBe("Shelcal 500");
    });

    it("does not submit twice on a double click", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);
        await fillForm(user);

        const slow = deferred();
        const mock = mockMedicinesApi({ hold: slow.promise });

        const button = submitButton();
        await user.click(button);
        await user.click(button);
        slow.resolve();

        await screen.findByRole("status");
        expect(postCalls(mock)).toHaveLength(1);
    });
});

// ---------------------------------------------------------------------------
// Outcomes
// ---------------------------------------------------------------------------

describe("success", () => {
    it("confirms the created medicine and says it has no stock", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({
            postResponse: makeCatalogueMedicine({ id: 101, name: "Shelcal 500" }),
        });
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        const status = await screen.findByRole("status");
        expect(status).toHaveTextContent(/Shelcal 500/);
        expect(status).toHaveTextContent(/#101/);
        expect(status).toHaveTextContent(/no stock yet/i);
    });

    it("refreshes the table from the server after a create", async () => {
        // Not an optimistic append: the row shown is one the server returned.
        const user = userEvent.setup();
        mockMedicinesApi({
            listSequence: [
                [makeCatalogueMedicine({ id: 17, name: "Paracetamol 500mg" })],
                [
                    makeCatalogueMedicine({ id: 17, name: "Paracetamol 500mg" }),
                    makeCatalogueMedicine({ id: 101, name: "Shelcal 500" }),
                ],
            ],
        });
        await openForm(user);

        expect(screen.queryByText("Shelcal 500")).not.toBeInTheDocument();

        await fillForm(user);
        await user.click(submitButton());

        // Scoped to the table: the success banner also names the medicine, so an
        // unscoped query matches two nodes and proves nothing about the refresh.
        await waitFor(() => {
            const table = screen.getByRole("table");
            expect(within(table).getByText("Shelcal 500")).toBeInTheDocument();
        });
    });

    it("clears the fields after a successful create", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        await screen.findByRole("status");
        expect(screen.getByLabelText("Name")).toHaveValue("");
    });
});

describe("failure", () => {
    it("shows the server's duplicate message on a 409", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({
            postStatus: 409,
            postResponse: { detail: "Medicine 'Shelcal 500' already exists." },
        });
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        expect(await screen.findByRole("alert")).toHaveTextContent(/already exists/i);
    });

    it("summarises a Pydantic 422 instead of printing the array", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({
            postStatus: 422,
            postResponse: {
                detail: [{ loc: ["body", "hsn_code"], msg: "String should have at least 8 characters" }],
            },
        });
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        const alert = await screen.findByRole("alert");
        expect(alert).not.toHaveTextContent("[object Object]");
        expect(alert).toHaveTextContent(/hsn code/i);
    });

    it("does not surface a 500's detail", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({
            postStatus: 500,
            postResponse: { detail: "IntegrityError: duplicate key on medicines.normalized_name" },
        });
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        const alert = await screen.findByRole("alert");
        expect(alert).not.toHaveTextContent(/IntegrityError/i);
        expect(alert).not.toHaveTextContent(/normalized_name/i);
    });

    it("keeps everything typed when the create fails", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({ postStatus: 409, postResponse: { detail: "Already exists." } });
        await openForm(user);

        await fillForm(user, { name: "Shelcal 500" });
        await user.click(submitButton());

        await screen.findByRole("alert");
        expect(screen.getByLabelText("Name")).toHaveValue("Shelcal 500");
    });

    it("reports a network failure plainly", async () => {
        const user = userEvent.setup();
        mockMedicinesApi();
        await openForm(user);
        await fillForm(user);

        mockMedicinesApi({ networkError: true });
        await user.click(submitButton());

        expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach the server/i);
    });

    it("never renders SQL, a traceback or credentials", async () => {
        const user = userEvent.setup();
        mockMedicinesApi({
            postStatus: 500,
            postResponse: { detail: "SELECT * FROM medicines; Traceback (most recent call last): password=root" },
        });
        await openForm(user);

        await fillForm(user);
        await user.click(submitButton());

        await screen.findByRole("alert");
        const body = document.body.textContent.toLowerCase();
        for (const leak of ["select *", "traceback", "password=", "pymysql"]) {
            expect(body).not.toContain(leak);
        }
    });
});
