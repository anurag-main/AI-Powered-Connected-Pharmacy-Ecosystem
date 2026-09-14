import { Card } from "@/components/ui/card";
import Icon from "@/components/ui/icon";

const rupee = (n) => `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * The last few receipts recorded, newest first.
 *
 * This is the answer to "did I already enter this delivery?", which is the
 * question a pharmacist actually has when they are holding a paper invoice and
 * cannot remember whether they typed it in before lunch. Recording it twice
 * would top up the batch and silently double the shop's stock, so making the
 * recent history visible on the same screen is a safeguard, not decoration.
 */
export default function RecentReceipts({ receipts }) {
    return (
        <Card className="p-5 space-y-3">
            <h2 className="text-sm font-semibold text-foreground flex items-center gap-2">
                <Icon name="history" size={18} className="text-muted-foreground" />
                Recently recorded
            </h2>

            {receipts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    No receipts recorded yet. The first one you save will appear here.
                </p>
            ) : (
                <ul className="divide-y divide-border/60 -mx-1">
                    {receipts.map((receipt) => (
                        <li key={receipt.purchase_id} className="py-2.5 px-1 flex items-baseline gap-3">
                            <div className="min-w-0 flex-1">
                                <p className="text-sm font-medium text-foreground truncate">
                                    {receipt.supplier_name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    #{receipt.purchase_id} · {receipt.purchase_date} ·{" "}
                                    {receipt.line_count} line{receipt.line_count === 1 ? "" : "s"}
                                    {receipt.invoice_number ? ` · ${receipt.invoice_number}` : ""}
                                </p>
                            </div>
                            <span className="text-sm tabular-nums font-medium shrink-0">
                                {rupee(receipt.total_amount)}
                            </span>
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    );
}
