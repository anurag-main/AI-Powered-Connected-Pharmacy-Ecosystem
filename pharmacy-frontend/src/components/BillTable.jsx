import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";

const rupee = (n) => `₹${Number(n).toFixed(2)}`;

/**
 * BillTable — the editable preview of priced line items.
 * Props:
 *   items: [{ name, quantity, unit, unit_price, batch_number, expiry_date, ... }]
 *   onQtyChange(index, newQty)
 *   onRemove(index)
 * Line totals + grand total are computed live (quantity × unit_price) so edits
 * reflect instantly; the server recomputes authoritatively on confirm.
 */
export default function BillTable({ items = [], onQtyChange, onRemove }) {
    const grandTotal = items.reduce((sum, it) => sum + it.quantity * it.unit_price, 0);

    if (items.length === 0) {
        return (
            <Card className="items-center justify-center py-16 text-muted-foreground">
                <Icon name="receipt_long" size={40} className="text-muted-foreground/40" />
                <p className="text-sm mt-2">No items yet. Speak or type an order, then press “Get Prices”.</p>
            </Card>
        );
    }

    return (
        <Card className="overflow-hidden p-0 gap-0">
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                            <th className="text-left font-semibold px-4 py-3">Medicine</th>
                            <th className="text-left font-semibold px-4 py-3">Batch / Expiry</th>
                            <th className="text-right font-semibold px-4 py-3">Price</th>
                            <th className="text-center font-semibold px-4 py-3 w-28">Qty</th>
                            <th className="text-right font-semibold px-4 py-3">Line Total</th>
                            <th className="px-4 py-3 w-12"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((it) => (
                            <tr key={it._id} className="border-b border-border/60 last:border-0">
                                <td className="px-4 py-3">
                                    <div className="font-medium text-foreground">{it.name}</div>
                                    <div className="text-xs text-muted-foreground">{it.unit}</div>
                                </td>
                                <td className="px-4 py-3 text-muted-foreground">
                                    <div>{it.batch_number}</div>
                                    <div className="text-xs">exp {it.expiry_date}</div>
                                </td>
                                <td className="px-4 py-3 text-right tabular-nums">{rupee(it.unit_price)}</td>
                                <td className="px-4 py-3">
                                    <Input
                                        type="number"
                                        min={1}
                                        value={it.quantity}
                                        onChange={(e) => onQtyChange(it._id, Math.max(1, parseInt(e.target.value || "1", 10)))}
                                        className="h-8 text-center"
                                    />
                                </td>
                                <td className="px-4 py-3 text-right font-semibold tabular-nums">
                                    {rupee(it.quantity * it.unit_price)}
                                </td>
                                <td className="px-4 py-3 text-center">
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon-sm"
                                        onClick={() => onRemove(it._id)}
                                        aria-label="Remove row"
                                        className="text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10"
                                    >
                                        <Icon name="delete" size={18} />
                                    </Button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr className="bg-muted/30">
                            <td colSpan={4} className="px-4 py-4 text-right font-semibold text-foreground">Total</td>
                            <td className="px-4 py-4 text-right text-lg font-bold text-primary tabular-nums">{rupee(grandTotal)}</td>
                            <td></td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </Card>
    );
}
