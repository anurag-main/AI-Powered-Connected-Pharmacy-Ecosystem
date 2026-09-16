import RiskBadgeBase, { makeRiskStyleResolver } from "@/components/ui/risk-badge";
import { NOTIFICATION_STATUS } from "@/lib/api/refill";

/**
 * The reminder's delivery state, straight from the backend.
 *
 * The frontend NEVER fabricates this. It does not optimistically show "sent"
 * after clicking, and it does not infer delivery from a 200 response — a 200
 * means Meta accepted the message, which is not the same as the customer
 * receiving it. Delivered and read only ever come from a webhook.
 */
const STYLES = {
    [NOTIFICATION_STATUS.PENDING]: {
        label: "Queued",
        icon: "schedule",
        badge: "bg-slate-100 text-slate-700",
        dot: "bg-slate-400",
    },
    [NOTIFICATION_STATUS.SENDING]: {
        label: "Sending",
        icon: "sync",
        badge: "bg-slate-100 text-slate-700",
        dot: "bg-slate-400",
    },
    [NOTIFICATION_STATUS.SENT]: {
        label: "Sent",
        icon: "done",
        badge: "bg-sky-100 text-sky-800",
        dot: "bg-sky-500",
    },
    [NOTIFICATION_STATUS.DELIVERED]: {
        label: "Delivered",
        icon: "done_all",
        badge: "bg-violet-100 text-violet-800",
        dot: "bg-violet-500",
    },
    [NOTIFICATION_STATUS.READ]: {
        label: "Read",
        icon: "mark_chat_read",
        badge: "bg-emerald-100 text-emerald-800",
        dot: "bg-emerald-500",
    },
    [NOTIFICATION_STATUS.FAILED]: {
        label: "Failed",
        icon: "error",
        badge: "bg-rose-100 text-rose-800",
        dot: "bg-rose-500",
    },
    [NOTIFICATION_STATUS.CANCELLED]: {
        label: "Cancelled",
        icon: "block",
        badge: "bg-slate-100 text-slate-600",
        dot: "bg-slate-400",
    },
};

const styleFor = makeRiskStyleResolver(STYLES);

export default function NotificationStatusBadge({ notification }) {
    if (!notification) {
        // No reminder exists yet. An em-dash rather than a "not sent" badge:
        // nothing has happened, which is different from something failing.
        return <span className="text-muted-foreground text-xs">—</span>;
    }
    return <RiskBadgeBase style={styleFor(notification.status)} />;
}
