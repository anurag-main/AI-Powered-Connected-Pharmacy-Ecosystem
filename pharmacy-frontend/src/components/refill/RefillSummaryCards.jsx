import { Card } from "@/components/ui/card";
import Icon from "@/components/ui/icon";

/**
 * Counts over the WHOLE scan, straight from the API's `summary`.
 *
 * Deliberately not derived from the visible rows: the table is filtered and
 * limited, so summing it would quietly under-report. The backend computes these
 * before any filter for exactly that reason.
 */
const CARDS = [
    {
        key: "due",
        label: "Due now",
        icon: "notifications_active",
        tone: "text-amber-600",
        hint: "Supply has run out and nothing was bought since",
    },
    {
        key: "contactable_due",
        label: "Due & reachable",
        icon: "chat",
        tone: "text-violet-600",
        hint: "Opted in with a usable number",
    },
    {
        key: "unknown_duration",
        label: "No duration",
        icon: "help",
        tone: "text-slate-500",
        hint: "Never remindable until days supply is recorded at billing",
    },
    {
        key: "customers_reviewed",
        label: "Customers scanned",
        icon: "group",
        tone: "text-muted-foreground",
        hint: "Identified customers with purchases in the window",
    },
];

export default function RefillSummaryCards({ summary }) {
    return (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            {CARDS.map((card) => (
                <Card key={card.key} className="p-4" data-testid={`summary-${card.key}`}>
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                        <Icon name={card.icon} size={16} className={card.tone} />
                        {card.label}
                    </div>
                    <p className="mt-1 text-2xl font-bold tabular-nums text-foreground">
                        {summary?.[card.key] ?? 0}
                    </p>
                    <p className="mt-1 text-[11px] text-muted-foreground leading-snug">
                        {card.hint}
                    </p>
                </Card>
            ))}
        </div>
    );
}
