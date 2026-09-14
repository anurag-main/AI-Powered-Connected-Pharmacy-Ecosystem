import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import {
    createMedicine,
    emptyMedicineForm,
    isMedicineFormComplete,
    HSN_LENGTH,
} from "@/lib/api/medicines";

/**
 * Add a catalogue entry.
 *
 * An inline panel rather than a modal dialog: there is no dialog primitive in
 * this project yet, and adding Radix plus a focus trap for one four-field form
 * is more machinery than the job needs.
 *
 * WHAT THIS FORM DOES NOT DO
 * --------------------------
 * It does not create stock. A medicine with no batch has zero quantity and will
 * not appear in any inventory or expiry report — the panel says so, because
 * "I added it but it shows nothing in stock" is the obvious next confusion.
 *
 * It also does not check whether the name is a duplicate. That is a database
 * question; the server answers it with a 409 and the message is shown as-is.
 */
export default function AddMedicineForm({ onCreated }) {
    const [open, setOpen] = useState(false);
    const [form, setForm] = useState(emptyMedicineForm());
    const [submitting, setSubmitting] = useState(false);
    const [error, setError] = useState(null);
    const [created, setCreated] = useState(null);

    const set = (field) => (event) => setForm({ ...form, [field]: event.target.value });
    const canSubmit = isMedicineFormComplete(form) && !submitting;

    const handleSubmit = async (event) => {
        event.preventDefault();
        // Checked here, not only via the disabled attribute: `disabled` is a hint
        // to a mouse and does not stop an Enter-key submit or a fast double click.
        if (!canSubmit) return;

        setSubmitting(true);
        setError(null);
        setCreated(null);

        const response = await createMedicine(form);

        setSubmitting(false);
        if (response.ok) {
            setCreated(response.data);
            setForm(emptyMedicineForm());
            onCreated?.(response.data);
        } else {
            // Everything typed stays put. The usual failure is a duplicate name
            // or a wrong HSN length, and clearing the form to punish that is how
            // people stop using a system.
            setError(response.error);
        }
    };

    const handleClose = () => {
        setOpen(false);
        setForm(emptyMedicineForm());
        setError(null);
        setCreated(null);
    };

    if (!open) {
        return (
            <div className="flex justify-end">
                <Button onClick={() => setOpen(true)}>
                    <Icon name="add" size={18} />
                    Add medicine
                </Button>
            </div>
        );
    }

    return (
        <Card className="p-5 space-y-4" data-testid="add-medicine-form">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h2 className="text-sm font-semibold text-foreground">Add a medicine</h2>
                    <p className="text-xs text-muted-foreground mt-0.5">
                        This creates a catalogue entry only. To put units on the shelf, record a
                        delivery on Receive Stock.
                    </p>
                </div>
                <button
                    type="button"
                    onClick={handleClose}
                    aria-label="Close"
                    className="shrink-0 h-8 w-8 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted"
                >
                    <Icon name="close" size={18} />
                </button>
            </div>

            {created && (
                <div
                    role="status"
                    className="rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 px-4 py-3 text-sm"
                >
                    <span className="font-medium">{created.name}</span> added as #{created.id}. It has
                    no stock yet.
                </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="sm:col-span-2">
                        <label
                            htmlFor="medicine-name"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                        >
                            Name
                        </label>
                        <Input
                            id="medicine-name"
                            value={form.name}
                            disabled={submitting}
                            onChange={set("name")}
                            placeholder="Shelcal 500"
                            className="h-9"
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="medicine-mrp"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                        >
                            MRP
                        </label>
                        <Input
                            id="medicine-mrp"
                            type="number"
                            min="0"
                            step="0.01"
                            value={form.mrp}
                            disabled={submitting}
                            onChange={set("mrp")}
                            placeholder="145.00"
                            className="h-9"
                        />
                    </div>

                    <div>
                        <label
                            htmlFor="medicine-hsn"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                        >
                            HSN code
                        </label>
                        <Input
                            id="medicine-hsn"
                            value={form.hsnCode}
                            disabled={submitting}
                            onChange={set("hsnCode")}
                            placeholder="30049099"
                            maxLength={HSN_LENGTH}
                            className="h-9"
                        />
                        <p className="text-[11px] text-muted-foreground mt-1">
                            Exactly {HSN_LENGTH} digits. Most tablets are 30049099 — check the
                            supplier invoice rather than assuming.
                        </p>
                    </div>

                    <div className="sm:col-span-2">
                        <label
                            htmlFor="medicine-manufacturer"
                            className="block text-xs font-medium text-muted-foreground mb-1"
                        >
                            Manufacturer <span className="font-normal">(optional)</span>
                        </label>
                        <Input
                            id="medicine-manufacturer"
                            value={form.manufacturer}
                            disabled={submitting}
                            onChange={set("manufacturer")}
                            placeholder="Torrent"
                            className="h-9"
                        />
                    </div>
                </div>

                {error && (
                    <div
                        role="alert"
                        className="rounded-lg bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm"
                    >
                        {error}
                    </div>
                )}

                <div className="flex items-center justify-end gap-2">
                    <Button type="button" variant="ghost" onClick={handleClose} disabled={submitting}>
                        Cancel
                    </Button>
                    <Button type="submit" disabled={!canSubmit}>
                        {submitting ? "Adding…" : "Add medicine"}
                    </Button>
                </div>
            </form>
        </Card>
    );
}
