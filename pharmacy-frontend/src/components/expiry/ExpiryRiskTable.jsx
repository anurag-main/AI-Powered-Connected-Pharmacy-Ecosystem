import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import RiskBadge, { riskStyle } from "./RiskBadge";

const rupee = (n) =>
    `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const dateLabel = (iso) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });

/** Days remaining, with expired stock stated as such rather than as "-10 days". */
function DaysCell({ days }) {
    if (days < 0) {
        return (
            <span className="font-medium text-slate-600 dark:text-slate-300">
                {Math.abs(days)}d ago
            </span>
        );
    }
    return <span className="tabular-nums">{days}d</span>;
}

export function ExpiryRiskTableSkeleton() {
    return (
        <Card className="p-6 gap-3">
            {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
            ))}
        </Card>
    );
}

export function ExpiryRiskEmpty({ windowDays, riskLevel }) {
    return (
        <Card className="items-center justify-center py-20 text-center">
            <Icon name="task_alt" size={44} className="text-emerald-400" />
            <p className="mt-3 text-sm font-medium">
                No stock is at expiry risk in this view.
            </p>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
                Nothing expiring within {windowDays} days
                {riskLevel ? ` at ${riskLevel} risk` : ""} has more stock than is
                expected to sell. Try a longer window or a different risk level.
            </p>
        </Card>
    );
}

/**
 * The ranked batch table.
 *
 * Row order is the backend's — severity first, then value at risk per remaining
 * day. It is not re-sorted here: the ranking is part of the answer, and a client
 * that reorders it would quietly disagree with the AI summary above it.
 *
 * Every figure is rendered as received. Nothing on this screen is computed in React.
 */
export default function ExpiryRiskTable({ items }) {
    const [openRow, setOpenRow] = useState(null);

    return (
        <Card className="overflow-hidden p-0 gap-0">
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                            <th className="px-4 py-3 text-left font-semibold">Medicine</th>
                            <th className="px-4 py-3 text-left font-semibold">Batch</th>
                            <th className="px-4 py-3 text-left font-semibold">Expiry</th>
                            <th className="px-4 py-3 text-right font-semibold">Days</th>
                            <th className="px-4 py-3 text-right font-semibold">Stock</th>
                            <th className="px-4 py-3 text-right font-semibold">Est. demand</th>
                            <th className="px-4 py-3 text-right font-semibold">Excess</th>
                            <th className="px-4 py-3 text-right font-semibold">Value at risk</th>
                            <th className="px-4 py-3 text-left font-semibold">Risk</th>
                            <th className="px-4 py-3 text-right font-semibold sr-only">Why</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((item, index) => {
                            const open = openRow === item.batch_id;
                            const style = riskStyle(item.risk_level);

                            return [
                                <tr
                                    key={item.batch_id}
                                    className="border-b border-border/60 last:border-0 hover:bg-muted/30"
                                >
                                    <td className="px-4 py-3">
                                        <div className="flex items-center gap-2">
                                            {/* Rank marker: the table IS the priority order. */}
                                            <span
                                                className={`h-6 w-1 shrink-0 rounded-full ${style.dot}`}
                                                aria-hidden="true"
                                            />
                                            <div>
                                                <p className="font-medium leading-tight">
                                                    {item.medicine_name}
                                                </p>
                                                <p className="text-[11px] text-muted-foreground">
                                                    #{index + 1} by priority
                                                </p>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                                        {item.batch_number}
                                    </td>
                                    <td className="px-4 py-3 whitespace-nowrap">
                                        {dateLabel(item.expiry_date)}
                                    </td>
                                    <td className="px-4 py-3 text-right whitespace-nowrap">
                                        <DaysCell days={item.days_to_expiry} />
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums">
                                        {item.stock_quantity}
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums text-muted-foreground">
                                        {item.estimated_demand}
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums font-semibold">
                                        {item.potential_excess}
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums font-semibold whitespace-nowrap">
                                        {rupee(item.value_at_risk)}
                                    </td>
                                    <td className="px-4 py-3">
                                        <RiskBadge level={item.risk_level} />
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <button
                                            onClick={() => setOpenRow(open ? null : item.batch_id)}
                                            aria-expanded={open}
                                            aria-label={`Why ${item.batch_number} is ${item.risk_level} risk`}
                                            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                                        >
                                            <Icon
                                                name={open ? "expand_less" : "expand_more"}
                                                size={18}
                                            />
                                        </button>
                                    </td>
                                </tr>,

                                open && (
                                    <tr
                                        key={`${item.batch_id}-why`}
                                        className="border-b border-border/60 bg-muted/20"
                                    >
                                        <td colSpan={10} className="px-4 py-4">
                                            <div className="grid gap-4 md:grid-cols-2">
                                                <div>
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                                        Why this level
                                                    </p>
                                                    <ul className="mt-2 space-y-1 text-xs">
                                                        {item.reasons.map((reason, i) => (
                                                            <li
                                                                key={i}
                                                                className="flex gap-2 text-muted-foreground"
                                                            >
                                                                <Icon
                                                                    name="chevron_right"
                                                                    size={14}
                                                                    className="mt-px shrink-0"
                                                                />
                                                                <span>{reason}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                </div>
                                                <div>
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                                        Suggested action
                                                    </p>
                                                    <p className="mt-2 text-xs">
                                                        {item.recommendation}
                                                    </p>
                                                    <p className="mt-2 text-[11px] text-muted-foreground">
                                                        Advisory only — nothing is changed
                                                        automatically.
                                                    </p>
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                ),
                            ];
                        })}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}
