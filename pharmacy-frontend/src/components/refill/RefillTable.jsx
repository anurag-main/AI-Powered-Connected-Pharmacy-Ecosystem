import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import { RefillStatusBadge, ContactabilityBadge } from "./RefillStatusBadge";
import NotificationStatusBadge from "./NotificationStatusBadge";
import { CONTACTABILITY, NOTIFICATION_STATUS } from "@/lib/api/refill";

/**
 * The ranked list of refill candidates.
 *
 * Presentational only. It does no arithmetic: `days_overdue`,
 * `expected_refill_date` and the reason sentence all arrive computed from the
 * engine. Recomputing "days overdue" in the browser would be a second
 * implementation of a business rule, and the two would disagree the first time
 * a timezone or a boundary changed.
 */

/** Null-safe: a candidate with no known duration has no date to show. */
function DateCell({ value }) {
    if (!value) {
        return (
            <span className="text-muted-foreground" title="No duration was recorded">
                —
            </span>
        );
    }
    return <span className="tabular-nums">{value}</span>;
}

/**
 * Overdue days. `0` is a real answer meaning "runs out today" and is shown as
 * "today" rather than "0d", which would read as missing data.
 */
function OverdueCell({ days }) {
    if (days === null || days === undefined) {
        return <span className="text-muted-foreground">—</span>;
    }
    if (days === 0) return <span className="text-muted-foreground">today</span>;
    return <span className="tabular-nums font-medium text-amber-700">{days}d</span>;
}

/**
 * Can this candidate be reminded right now?
 *
 * PRESENCE and STATE only, never a rule. The button being enabled is a
 * convenience; the server re-derives the candidate and re-checks consent on
 * every request, so a stale or hand-crafted click still cannot send to someone
 * who opted out.
 */
function canSend(candidate, notification) {
    if (candidate.contactability !== CONTACTABILITY.CONTACTABLE) return false;
    if (!notification) return true;
    return [NOTIFICATION_STATUS.PENDING, NOTIFICATION_STATUS.FAILED].includes(
        notification.status,
    );
}

export default function RefillTable({ candidates, notifications = {}, onSend, sendingId }) {
    return (
        <Card className="overflow-hidden p-0 gap-0">
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                            <th className="text-left font-semibold px-4 py-3">Customer</th>
                            <th className="text-left font-semibold px-4 py-3">Medicine</th>
                            <th className="text-left font-semibold px-4 py-3">Last bought</th>
                            <th className="text-left font-semibold px-4 py-3">Runs out</th>
                            <th className="text-right font-semibold px-4 py-3">Overdue</th>
                            <th className="text-left font-semibold px-4 py-3">Status</th>
                            <th className="text-left font-semibold px-4 py-3">Contact</th>
                            <th className="text-left font-semibold px-4 py-3">Reminder</th>
                            <th className="text-left font-semibold px-4 py-3">Why</th>
                            <th className="px-4 py-3"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {candidates.map((c) => (
                            <tr
                                key={`${c.source_sale_item_id}-${c.expected_refill_date}`}
                                className="border-b border-border/60 last:border-0"
                                data-testid="refill-row"
                            >
                                <td className="px-4 py-3">
                                    <div className="font-medium text-foreground">
                                        {c.customer_name || "—"}
                                    </div>
                                    <div className="text-xs text-muted-foreground tabular-nums">
                                        {c.customer_phone}
                                    </div>
                                </td>
                                <td className="px-4 py-3 text-foreground">{c.medicine_name}</td>
                                <td className="px-4 py-3 text-muted-foreground">
                                    <DateCell value={c.last_purchase_date} />
                                </td>
                                <td className="px-4 py-3 text-muted-foreground">
                                    <DateCell value={c.expected_refill_date} />
                                </td>
                                <td className="px-4 py-3 text-right">
                                    <OverdueCell days={c.days_overdue} />
                                </td>
                                <td className="px-4 py-3">
                                    <RefillStatusBadge status={c.status} />
                                </td>
                                <td className="px-4 py-3">
                                    <ContactabilityBadge contactability={c.contactability} />
                                </td>
                                <td className="px-4 py-3">
                                    <NotificationStatusBadge
                                        notification={notifications[String(c.source_sale_item_id)]}
                                    />
                                </td>
                                <td className="px-4 py-3 text-xs text-muted-foreground max-w-xs">
                                    {c.reason}
                                </td>
                                <td className="px-4 py-3 text-right">
                                    {canSend(c, notifications[String(c.source_sale_item_id)]) && (
                                        <Button
                                            size="sm"
                                            variant="outline"
                                            disabled={sendingId === c.source_sale_item_id}
                                            onClick={() => onSend?.(c)}
                                        >
                                            <Icon name="send" size={16} />
                                            {sendingId === c.source_sale_item_id
                                                ? "Sending…"
                                                : "Remind"}
                                        </Button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </Card>
    );
}
