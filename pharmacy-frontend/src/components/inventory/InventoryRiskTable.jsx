import { useState } from "react";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import InventoryRiskBadge, { inventoryRiskStyle } from "./InventoryRiskBadge";

const rupee = (n) =>
    `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const dateLabel = (iso) =>
    new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });

/**
 * A backend null rendered honestly.
 *
 * This matters more here than anywhere else on the site. `days_of_cover` is null
 * when nothing is selling, and `stock_age_days` is null when a batch predates
 * purchase records. Rendering either as 0 would state a fact the backend explicitly
 * refused to state, and `Number(null) || 0` — the usual React shortcut — does
 * exactly that. So nulls get a dash and a tooltip, never a number.
 */
function Unknown({ title }) {
    return (
        <span className="text-muted-foreground" title={title}>
            —
        </span>
    );
}

function CoverCell({ days }) {
    if (days === null || days === undefined) {
        return <Unknown title="Not selling — there is no rate to divide by" />;
    }
    return <span className="tabular-nums">{days}d</span>;
}

function AgeCell({ days }) {
    if (days === null || days === undefined) {
        return <Unknown title="No purchase record for the stock held" />;
    }
    return <span className="tabular-nums">{days}d</span>;
}

export function InventoryRiskTableSkeleton() {
    return (
        <Card className="p-6 gap-3">
            {[...Array(6)].map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
            ))}
        </Card>
    );
}

export function InventoryRiskEmpty({ targetCoverDays, riskLevel }) {
    return (
        <Card className="items-center justify-center py-20 text-center">
            <Icon name="savings" size={44} className="text-emerald-400" />
            <p className="mt-3 text-sm font-medium">
                No inventory needs attention in this view.
            </p>
            <p className="mt-1 max-w-md text-xs text-muted-foreground">
                Nothing{riskLevel ? ` at ${riskLevel} risk` : ""} is holding more
                than {targetCoverDays} days of stock. Try a shorter holding target
                or a different risk level.
            </p>
        </Card>
    );
}

/**
 * The ranked medicine table.
 *
 * Row order is the backend's — it applied the sort the filter bar asked for. It is
 * not re-sorted here: the ranking is part of the answer, and a client that reorders
 * it would quietly disagree with the AI summary above it.
 *
 * Every figure is rendered as received. Nothing on this screen is computed in
 * React — not cover, not excess, not capital at risk, not the risk level. The only
 * transformations are currency grouping and date formatting.
 */
export default function InventoryRiskTable({ items }) {
    const [openRow, setOpenRow] = useState(null);

    return (
        <Card className="overflow-hidden p-0 gap-0">
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                            <th className="px-4 py-3 text-left font-semibold">Medicine</th>
                            <th className="px-4 py-3 text-right font-semibold">Stock</th>
                            <th className="px-4 py-3 text-right font-semibold">Velocity</th>
                            <th className="px-4 py-3 text-right font-semibold">Cover</th>
                            <th className="px-4 py-3 text-right font-semibold">Excess</th>
                            <th className="px-4 py-3 text-right font-semibold">
                                Capital at risk
                            </th>
                            <th className="px-4 py-3 text-right font-semibold">Age</th>
                            <th className="px-4 py-3 text-left font-semibold">Risk</th>
                            <th className="px-4 py-3 text-right font-semibold sr-only">Why</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((item, index) => {
                            const open = openRow === item.medicine_id;
                            const style = inventoryRiskStyle(item.risk_level);

                            return [
                                <tr
                                    key={item.medicine_id}
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
                                    <td className="px-4 py-3 text-right tabular-nums">
                                        {item.stock_quantity}
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums text-muted-foreground whitespace-nowrap">
                                        {item.daily_velocity}/day
                                    </td>
                                    <td className="px-4 py-3 text-right whitespace-nowrap">
                                        <CoverCell days={item.days_of_cover} />
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums font-semibold">
                                        {item.excess_units}
                                    </td>
                                    <td className="px-4 py-3 text-right tabular-nums font-semibold whitespace-nowrap">
                                        {rupee(item.capital_at_risk)}
                                    </td>
                                    <td className="px-4 py-3 text-right whitespace-nowrap">
                                        <AgeCell days={item.stock_age_days} />
                                    </td>
                                    <td className="px-4 py-3">
                                        <InventoryRiskBadge level={item.risk_level} />
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <button
                                            onClick={() =>
                                                setOpenRow(open ? null : item.medicine_id)
                                            }
                                            aria-expanded={open}
                                            aria-label={`Why ${item.medicine_name} is ${item.risk_level} risk`}
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
                                        key={`${item.medicine_id}-why`}
                                        className="border-b border-border/60 bg-muted/20"
                                    >
                                        <td colSpan={9} className="px-4 py-4">
                                            <div className="grid gap-4 md:grid-cols-2">
                                                <div>
                                                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                                        Why this level
                                                    </p>
                                                    <ul className="mt-2 space-y-1 text-xs">
                                                        {item.risk_reasons.map((reason, i) => (
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
                                                        The detail
                                                    </p>
                                                    <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
                                                        <dt className="text-muted-foreground">
                                                            Sellable stock
                                                        </dt>
                                                        <dd className="tabular-nums">
                                                            {item.sellable_quantity} of{" "}
                                                            {item.stock_quantity}
                                                        </dd>

                                                        <dt className="text-muted-foreground">
                                                            Stock value
                                                        </dt>
                                                        <dd className="tabular-nums">
                                                            {rupee(item.inventory_value)}
                                                        </dd>

                                                        <dt className="text-muted-foreground">
                                                            Unit cost (avg)
                                                        </dt>
                                                        <dd className="tabular-nums">
                                                            {rupee(item.weighted_avg_cost)}
                                                        </dd>

                                                        <dt className="text-muted-foreground">
                                                            Target stock
                                                        </dt>
                                                        <dd className="tabular-nums">
                                                            {item.target_stock}
                                                        </dd>

                                                        <dt className="text-muted-foreground">
                                                            Sold recently
                                                        </dt>
                                                        <dd className="tabular-nums">
                                                            {item.units_sold} unit(s)
                                                        </dd>

                                                        <dt className="text-muted-foreground">
                                                            Last sold
                                                        </dt>
                                                        <dd>
                                                            {item.last_sale_date ? (
                                                                dateLabel(item.last_sale_date)
                                                            ) : (
                                                                <span className="text-muted-foreground">
                                                                    never
                                                                </span>
                                                            )}
                                                        </dd>
                                                    </dl>
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
