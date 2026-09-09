import { useCallback, useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import { getSale, listSales, SALES_PAGE_SIZE } from "@/lib/api/sales";

const rupee = (n) =>
    `₹${Number(n || 0).toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;

const when = (iso) =>
    new Date(iso).toLocaleString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });

/** Line items for one invoice, fetched the first time the row is opened. */
function SaleLines({ saleId }) {
    const [state, setState] = useState({ loading: true, error: null, lines: [] });

    useEffect(() => {
        let alive = true;

        getSale(saleId).then((result) => {
            if (!alive) return;
            setState(
                result.ok
                    ? { loading: false, error: null, lines: result.data.lines }
                    : { loading: false, error: result.error, lines: [] }
            );
        });

        return () => {
            alive = false;
        };
    }, [saleId]);

    if (state.loading) {
        return (
            <div className="space-y-2 px-4 py-3">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-4 w-1/2" />
            </div>
        );
    }

    if (state.error) {
        return <p className="px-4 py-3 text-xs text-rose-600">{state.error}</p>;
    }

    return (
        <table className="w-full text-xs">
            <thead>
                <tr className="text-muted-foreground">
                    <th className="px-4 py-2 text-left font-semibold">Medicine</th>
                    <th className="px-4 py-2 text-left font-semibold">Batch / Expiry</th>
                    <th className="px-4 py-2 text-right font-semibold">Qty</th>
                    <th className="px-4 py-2 text-right font-semibold">Rate</th>
                    <th className="px-4 py-2 text-right font-semibold">Amount</th>
                </tr>
            </thead>
            <tbody>
                {state.lines.map((line, i) => (
                    <tr key={i} className="border-t border-border/40">
                        <td className="px-4 py-2 font-medium">{line.medicine_name}</td>
                        <td className="px-4 py-2 text-muted-foreground">
                            {line.batch_number || "—"}
                            {line.expiry_date && (
                                <span className="ml-1 text-[11px]">
                                    exp {line.expiry_date}
                                </span>
                            )}
                        </td>
                        <td className="px-4 py-2 text-right tabular-nums">{line.quantity}</td>
                        <td className="px-4 py-2 text-right tabular-nums">
                            {rupee(line.unit_price)}
                        </td>
                        <td className="px-4 py-2 text-right font-semibold tabular-nums">
                            {rupee(line.line_total)}
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

/**
 * Sales History — every saved invoice, newest first.
 *
 * Rows come from a paged list endpoint; line items load per invoice when a row is
 * opened. Prices shown are what was charged at the time, read from `sale_items`,
 * not recomputed from today's MRP.
 */
function SalesPage() {
    const [sales, setSales] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [error, setError] = useState(null);
    const [openRow, setOpenRow] = useState(null);

    const load = useCallback(async ({ append = false } = {}) => {
        const offset = append ? sales.length : 0;
        append ? setLoadingMore(true) : setLoading(true);
        setError(null);

        const result = await listSales({ limit: SALES_PAGE_SIZE, offset });

        if (result.ok) {
            setTotal(result.data.total);
            setSales((prev) =>
                append ? [...prev, ...result.data.sales] : result.data.sales
            );
        } else {
            setError({ message: result.error, requestId: result.requestId });
            if (!append) setSales([]);
        }

        append ? setLoadingMore(false) : setLoading(false);
    }, [sales.length]);

    // Mount only. `load` changes with sales.length, which would re-fetch forever.
    useEffect(() => {
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const hasMore = sales.length < total;

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight sm:text-3xl">
                        <Icon name="receipt_long" size={30} className="text-primary" />
                        Sales History
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Every saved invoice, newest first. Open a row to see its lines.
                    </p>
                </div>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => load()}
                    disabled={loading}
                >
                    <Icon name="refresh" size={16} /> Refresh
                </Button>
            </div>

            {loading && (
                <Card className="gap-3 p-6">
                    {[...Array(6)].map((_, i) => (
                        <Skeleton key={i} className="h-9 w-full" />
                    ))}
                </Card>
            )}

            {!loading && error && (
                <Card className="items-center justify-center py-16 text-center">
                    <Icon name="error" size={40} className="text-rose-400" />
                    <p className="mt-3 text-sm font-medium">Unable to load sales history.</p>
                    <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
                    <Button variant="outline" size="sm" className="mt-4" onClick={() => load()}>
                        <Icon name="refresh" size={16} /> Try again
                    </Button>
                    {error.requestId && (
                        <p className="mt-3 font-mono text-[10px] text-muted-foreground/70">
                            ref {error.requestId}
                        </p>
                    )}
                </Card>
            )}

            {!loading && !error && sales.length === 0 && (
                <Card className="items-center justify-center py-20 text-center">
                    <Icon name="receipt_long" size={44} className="text-muted-foreground/40" />
                    <p className="mt-3 text-sm font-medium">No sales yet.</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        Bills you save on the New Bill screen will appear here.
                    </p>
                </Card>
            )}

            {!loading && !error && sales.length > 0 && (
                <>
                    <Card className="overflow-hidden p-0 gap-0">
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                                        <th className="px-4 py-3 text-left font-semibold">Invoice</th>
                                        <th className="px-4 py-3 text-left font-semibold">Date</th>
                                        <th className="px-4 py-3 text-left font-semibold">Customer</th>
                                        <th className="px-4 py-3 text-right font-semibold">Items</th>
                                        <th className="px-4 py-3 text-right font-semibold">Total</th>
                                        <th className="px-4 py-3 w-12" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {sales.map((sale) => {
                                        const open = openRow === sale.sale_id;
                                        return [
                                            <tr
                                                key={sale.sale_id}
                                                onClick={() =>
                                                    setOpenRow(open ? null : sale.sale_id)
                                                }
                                                className="cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/30"
                                            >
                                                <td className="px-4 py-3 font-semibold tabular-nums">
                                                    #{sale.sale_id}
                                                </td>
                                                <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                                                    {when(sale.sold_at)}
                                                </td>
                                                <td className="px-4 py-3">
                                                    {sale.customer_name || (
                                                        <span className="text-muted-foreground">
                                                            Walk-in
                                                        </span>
                                                    )}
                                                    {sale.customer_phone && (
                                                        <span className="ml-2 text-xs text-muted-foreground">
                                                            {sale.customer_phone}
                                                        </span>
                                                    )}
                                                </td>
                                                <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                                                    {sale.item_count}
                                                </td>
                                                <td className="px-4 py-3 text-right font-semibold tabular-nums">
                                                    {rupee(sale.total_amount)}
                                                </td>
                                                <td className="px-4 py-3 text-center text-muted-foreground">
                                                    <Icon
                                                        name={open ? "expand_less" : "expand_more"}
                                                        size={18}
                                                    />
                                                </td>
                                            </tr>,

                                            open && (
                                                <tr
                                                    key={`${sale.sale_id}-lines`}
                                                    className="border-b border-border/60 bg-muted/20"
                                                >
                                                    <td colSpan={6} className="p-0">
                                                        <SaleLines saleId={sale.sale_id} />
                                                    </td>
                                                </tr>
                                            ),
                                        ];
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Card>

                    <div className="flex items-center justify-center gap-4">
                        <p className="text-xs text-muted-foreground">
                            Showing {sales.length} of {total}
                        </p>
                        {hasMore && (
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={() => load({ append: true })}
                                disabled={loadingMore}
                            >
                                {loadingMore ? "Loading…" : "Load more"}
                            </Button>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

SalesPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default SalesPage;
