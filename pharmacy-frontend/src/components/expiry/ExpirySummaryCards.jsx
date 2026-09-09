import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";

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

export function ExpirySummaryCardsSkeleton() {
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
 * Every figure comes from the backend, counted over the whole filtered result
 * BEFORE `limit` was applied. That is why they are read from `counts_by_risk` and
 * `total_*` rather than derived from `report.items` — asking for the top 5 would
 * otherwise make every card top out at 5.
 */
export default function ExpirySummaryCards({ report }) {
    const counts = report.counts_by_risk || {};

    return (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard
                icon="inventory_2"
                tone="bg-primary/10 text-primary"
                label="Batches reviewed"
                value={report.total_batches_reviewed}
                hint={`Expiring within ${report.window_days} days`}
            />
            <StatCard
                icon="e911_emergency"
                tone="bg-rose-500/10 text-rose-600"
                label="Critical"
                value={counts.critical ?? 0}
                hint="Excess stock, under a week left"
            />
            <StatCard
                icon="warning"
                tone="bg-orange-500/10 text-orange-600"
                label="High risk"
                value={counts.high ?? 0}
                hint={`${counts.expired ?? 0} already expired`}
            />
            <StatCard
                icon="currency_rupee"
                tone="bg-violet-500/10 text-violet-600"
                label="Value at risk"
                value={rupee(report.total_value_at_risk)}
                hint={`Across ${report.total_at_risk} batch(es) with excess`}
            />
        </div>
    );
}
