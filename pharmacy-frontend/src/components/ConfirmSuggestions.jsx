import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";

const rupee = (n) => `₹${Number(n).toFixed(2)}`;

/**
 * ConfirmSuggestions — the "did you hear this right?" section.
 * Uncertain voice matches land here instead of the bill. The owner can:
 *   - pick the right medicine from a dropdown of close candidates (reprices), then
 *   - Accept (move it onto the bill), or Dismiss (drop it).
 *
 * Props:
 *   items: pending line items (needs_confirm=true) — each has _id, matched_from,
 *          name, unit_price, quantity, candidates: [{medicine_id, name}]
 *   onPick(_id, candidate)   — owner chose a different candidate (parent reprices)
 *   onAccept(_id)            — confirm this row onto the bill
 *   onDismiss(_id)           — discard this row
 */
export default function ConfirmSuggestions({ items = [], onPick, onAccept, onDismiss }) {
    if (items.length === 0) return null;

    return (
        <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-4 space-y-3">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300 font-semibold text-sm">
                <Icon name="help" size={18} />
                Did I hear these right? Confirm before billing.
            </div>

            {items.map((it) => (
                <Card key={it._id} className="p-3 gap-0 flex-row items-center flex-wrap sm:flex-nowrap gap-3">
                    <div className="text-xs text-muted-foreground shrink-0">
                        heard <span className="font-medium text-foreground">“{it.matched_from}”</span> →
                    </div>

                    {/* Candidate picker (defaults to the suggested medicine) */}
                    <select
                        value={it.medicine_id}
                        onChange={(e) => {
                            const cand = it.candidates.find((c) => String(c.medicine_id) === e.target.value);
                            if (cand) onPick(it._id, cand);
                        }}
                        className="h-9 rounded-md border border-input bg-background px-3 text-sm flex-1 min-w-40"
                    >
                        {it.candidates.map((c) => (
                            <option key={c.medicine_id} value={c.medicine_id}>{c.name}</option>
                        ))}
                    </select>

                    <div className="text-sm tabular-nums shrink-0">
                        {it.quantity} × {rupee(it.unit_price)}
                    </div>

                    <div className="flex gap-2 shrink-0">
                        <Button size="sm" onClick={() => onAccept(it._id)}>
                            <Icon name="check" size={16} /> Accept
                        </Button>
                        <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => onDismiss(it._id)}
                            className="text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10"
                        >
                            <Icon name="close" size={16} /> Dismiss
                        </Button>
                    </div>
                </Card>
            ))}
        </div>
    );
}
