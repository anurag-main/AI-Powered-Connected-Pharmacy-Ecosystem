import Icon from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { emptyLine } from "@/lib/api/purchases";

/**
 * The editable lines of a supplier invoice.
 *
 * WHAT THIS COMPONENT DOES NOT DO
 * -------------------------------
 * It does not multiply quantity by unit cost. There is no running total on this
 * form, and that is a decision rather than an omission.
 *
 * A preview total would be a second implementation of money arithmetic living in
 * a browser, and the moment it disagreed with the server — a rounding rule, a
 * rejected line, a batch top-up — the pharmacist would believe the one on the
 * screen in front of them. The total appears once, after the receipt is
 * recorded, and it is the figure that was actually written to the database.
 *
 * It also does not check expiry dates against today, or cost against MRP. Those
 * are business rules; they live in goods_receipt_service.py and the server's
 * refusal is shown verbatim.
 */
export default function ReceiptLinesEditor({ lines, medicines, onChange, disabled }) {
    const update = (index, field, value) => {
        const next = lines.map((line, i) => (i === index ? { ...line, [field]: value } : line));
        onChange(next);
    };

    const addLine = () => onChange([...lines, emptyLine()]);

    const removeLine = (index) => {
        // Never leave the form with zero rows — an empty editor looks broken and
        // gives the pharmacist nothing to click except "add".
        const next = lines.filter((_, i) => i !== index);
        onChange(next.length ? next : [emptyLine()]);
    };

    return (
        <div className="space-y-3">
            <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">What arrived</h2>
                <button
                    type="button"
                    onClick={addLine}
                    disabled={disabled}
                    className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline disabled:opacity-50 disabled:no-underline"
                >
                    <Icon name="add" size={18} />
                    Add line
                </button>
            </div>

            <div className="space-y-3">
                {lines.map((line, index) => (
                    <div
                        key={index}
                        className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end rounded-lg border border-border/60 p-3"
                        data-testid="receipt-line"
                    >
                        <div className="sm:col-span-4">
                            <label
                                className="block text-xs font-medium text-muted-foreground mb-1"
                                htmlFor={`medicine-${index}`}
                            >
                                Medicine
                            </label>
                            <select
                                id={`medicine-${index}`}
                                value={line.medicineId}
                                disabled={disabled}
                                onChange={(e) => update(index, "medicineId", e.target.value)}
                                className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
                            >
                                <option value="">Select…</option>
                                {(medicines || []).map((m) => (
                                    <option key={m.id} value={m.id}>
                                        {m.name}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="sm:col-span-2">
                            <label
                                className="block text-xs font-medium text-muted-foreground mb-1"
                                htmlFor={`batch-${index}`}
                            >
                                Batch no.
                            </label>
                            <Input
                                id={`batch-${index}`}
                                value={line.batchNumber}
                                disabled={disabled}
                                onChange={(e) => update(index, "batchNumber", e.target.value)}
                                placeholder="AB1234"
                                className="h-9"
                            />
                        </div>

                        <div className="sm:col-span-2">
                            <label
                                className="block text-xs font-medium text-muted-foreground mb-1"
                                htmlFor={`expiry-${index}`}
                            >
                                Expiry
                            </label>
                            <Input
                                id={`expiry-${index}`}
                                type="date"
                                value={line.expiryDate}
                                disabled={disabled}
                                onChange={(e) => update(index, "expiryDate", e.target.value)}
                                className="h-9"
                            />
                        </div>

                        <div className="sm:col-span-1">
                            <label
                                className="block text-xs font-medium text-muted-foreground mb-1"
                                htmlFor={`qty-${index}`}
                            >
                                Qty
                            </label>
                            <Input
                                id={`qty-${index}`}
                                type="number"
                                min="1"
                                value={line.quantity}
                                disabled={disabled}
                                onChange={(e) => update(index, "quantity", e.target.value)}
                                className="h-9"
                            />
                        </div>

                        <div className="sm:col-span-2">
                            <label
                                className="block text-xs font-medium text-muted-foreground mb-1"
                                htmlFor={`cost-${index}`}
                            >
                                Cost / unit
                            </label>
                            <Input
                                id={`cost-${index}`}
                                type="number"
                                min="0"
                                step="0.01"
                                value={line.unitCost}
                                disabled={disabled}
                                onChange={(e) => update(index, "unitCost", e.target.value)}
                                className="h-9"
                            />
                        </div>

                        <div className="sm:col-span-1 flex justify-end">
                            <button
                                type="button"
                                onClick={() => removeLine(index)}
                                disabled={disabled}
                                aria-label={`Remove line ${index + 1}`}
                                className="h-9 w-9 rounded-md flex items-center justify-center text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 disabled:opacity-40"
                            >
                                <Icon name="delete" size={18} />
                            </button>
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}
