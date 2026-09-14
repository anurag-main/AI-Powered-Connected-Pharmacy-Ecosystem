import Icon from "@/components/ui/icon";

const rupee = (n) => `₹${Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/**
 * The receipt as the server recorded it.
 *
 * Every figure here came back from the API. Nothing on this screen is computed
 * in the browser, which is what makes it worth checking against the paper
 * invoice: if the total shown here is wrong, the total in the database is wrong,
 * and there is no third version to reconcile.
 *
 * `batch_created` is shown per line because it is the one outcome a pharmacist
 * cannot predict from what they typed. "Topped up" means this batch number was
 * already on the shelf and the units were added to it, rather than a second
 * batch row appearing — worth seeing, because it confirms the shop has one
 * carton record and not two.
 */
export default function RecordedReceipt({ receipt, requestId, onRecordAnother }) {
    return (
        <div
            className="rounded-xl border border-emerald-200 bg-emerald-50/60 dark:bg-emerald-950/20 dark:border-emerald-900 p-5 space-y-4"
            data-testid="recorded-receipt"
        >
            <div className="flex items-start justify-between gap-4">
                <div className="flex items-start gap-3">
                    <Icon name="check_circle" filled size={24} className="text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                        <p className="font-semibold text-emerald-900 dark:text-emerald-200">
                            Stock recorded — receipt #{receipt.purchase_id}
                        </p>
                        <p className="text-sm text-emerald-800/80 dark:text-emerald-300/80 mt-0.5">
                            {receipt.supplier_name}
                            {receipt.invoice_number ? ` · invoice ${receipt.invoice_number}` : ""} ·{" "}
                            {receipt.purchase_date}
                        </p>
                    </div>
                </div>
                <button
                    type="button"
                    onClick={onRecordAnother}
                    className="shrink-0 text-sm font-medium text-emerald-800 dark:text-emerald-300 hover:underline"
                >
                    Record another
                </button>
            </div>

            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-muted-foreground border-b border-emerald-200/70 dark:border-emerald-900">
                            <th className="text-left font-semibold py-2 pr-3">Medicine</th>
                            <th className="text-left font-semibold py-2 px-3">Batch</th>
                            <th className="text-left font-semibold py-2 px-3">Expiry</th>
                            <th className="text-right font-semibold py-2 px-3">Qty</th>
                            <th className="text-right font-semibold py-2 px-3">Cost</th>
                            <th className="text-right font-semibold py-2 pl-3">Line total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {receipt.lines.map((line, index) => (
                            <tr
                                // batch_id alone is not safe as a key: the detail
                                // endpoint reports 0 for a line whose batch link
                                // is null, and two such lines would collide.
                                key={`${line.batch_id}-${index}`}
                                className="border-b border-emerald-200/40 dark:border-emerald-900/60 last:border-0"
                            >
                                <td className="py-2 pr-3 font-medium text-foreground">{line.medicine_name}</td>
                                <td className="py-2 px-3">
                                    <span className="font-mono text-xs">{line.batch_number}</span>
                                    <span className="ml-2 text-[11px] text-muted-foreground">
                                        {line.batch_created ? "new batch" : "topped up"}
                                    </span>
                                </td>
                                <td className="py-2 px-3 tabular-nums text-muted-foreground">{line.expiry_date}</td>
                                <td className="py-2 px-3 text-right tabular-nums">{line.quantity}</td>
                                <td className="py-2 px-3 text-right tabular-nums">{rupee(line.unit_cost)}</td>
                                <td className="py-2 pl-3 text-right tabular-nums font-medium">
                                    {rupee(line.line_total)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                    <tfoot>
                        <tr className="border-t-2 border-emerald-300/70 dark:border-emerald-800">
                            <td className="py-2 pr-3 font-semibold" colSpan={3}>
                                Recorded total
                            </td>
                            <td className="py-2 px-3 text-right tabular-nums font-semibold">
                                {receipt.total_units}
                            </td>
                            <td />
                            <td className="py-2 pl-3 text-right tabular-nums font-bold text-base">
                                {rupee(receipt.total_amount)}
                            </td>
                        </tr>
                    </tfoot>
                </table>
            </div>

            <p className="text-xs text-muted-foreground">
                Check this against the supplier&apos;s paper invoice. These are the figures now in the
                database.
                {requestId ? ` · ref ${requestId}` : ""}
            </p>
        </div>
    );
}
