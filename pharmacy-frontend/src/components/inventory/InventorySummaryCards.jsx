import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";

/**
 * Rupees, Indian digit grouping. Display formatting only — the value is the
 * backend's, unrounded and unaltered.
 */
const rupee = (n) =>
    `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function StatCard({ icon, tone, label, value, hint }) {
    return (
        <Card className="p-5 gap-0">
            <div className="flex items-start justify-between gap-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {label}
                </p>
                <span className={`shrink-0 rounded-lg p-1.5 ${tone}`}>
                    <Icon name={icon} size={18} />
                </span>
            </div>
            <p className="mt-3 text-2xl font-bold tabular-nums tracking-tight">{value}</p>
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        </Card>
    );
}

export function InventorySummaryCardsSkeleton() {
    return (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[...Array(4)].map((_, i) => (
                <Card key={i} className="p-5 gap-0">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="mt-4 h-7 w-20" />
                    <Skeleton className="mt-2 h-3 w-32" />
                </Card>
            ))}
        </div>
    );
}

/**
 * The four KPIs.
 *
 * Every figure comes from the backend. `counts_by_risk` and the `total_*` fields
 * are counted over the WHOLE shop, before any filter and before `limit` — which is
 * why they are read from the report rather than derived from `report.items`.
 * Filtering to dead stock must not make the shop look like it holds Rs 27,400.
 *
 * "Tied up" and "at risk" are deliberately two cards. Total inventory value is the
 * money on the shelves; capital at risk is the part that is not working. Showing
 * only the first understates the problem, and showing only the second reads as if
 * the whole shop were a write-off.
 */
export default function InventorySummaryCards({ report }) {
    const counts = report.counts_by_risk || {};
    const atRisk =
        (counts.dead ?? 0) + (counts.critical ?? 0) + (counts.high ?? 0);

    return (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
                icon="inventory_2"
                tone="bg-primary/10 text-primary"
                label="Stock on hand"
                value={rupee(report.total_inventory_value)}
                hint={`Across ${report.medicines_reviewed} medicine(s)`}
            />
            <StatCard
                icon="currency_rupee"
                tone="bg-rose-500/10 text-rose-600"
                label="Capital at risk"
                value={rupee(report.total_capital_at_risk)}
                hint="Stock held beyond the target cover"
            />
            <StatCard
                icon="do_not_disturb_on"
                tone="bg-violet-500/10 text-violet-600"
                label="Dead stock"
                value={counts.dead ?? 0}
                hint="Not selling at all"
            />
            <StatCard
                icon="warning"
                tone="bg-orange-500/10 text-orange-600"
                label="Needs attention"
                value={atRisk}
                hint={`${counts.critical ?? 0} critical · ${counts.high ?? 0} high`}
            />
        </div>
    );
}
