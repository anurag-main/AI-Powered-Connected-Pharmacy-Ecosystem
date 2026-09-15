import RiskBadgeBase, { makeRiskStyleResolver } from "@/components/ui/risk-badge";
import { REFILL_STATUS, CONTACTABILITY } from "@/lib/api/refill";

/**
 * Two badges, deliberately with two separate style maps.
 *
 * Status and contactability are orthogonal facts — a customer can be due AND
 * unreachable — so they must not share a colour scale. One ramp for both would
 * make "due" and "opted out" look comparable, when one is an opportunity and the
 * other is a restriction on how to act on it.
 *
 * Each map is owned here rather than in `ui/risk-badge`, following the rule that
 * file already states: features own their level maps so a new backend value
 * degrades to "Unknown" instead of rendering someone else's colour.
 */

const STATUS_STYLES = {
    [REFILL_STATUS.DUE]: {
        label: "Due",
        icon: "notifications_active",
        badge: "bg-amber-100 text-amber-800",
        dot: "bg-amber-500",
    },
    [REFILL_STATUS.NOT_DUE]: {
        label: "Not due",
        icon: "check_circle",
        badge: "bg-emerald-100 text-emerald-800",
        dot: "bg-emerald-500",
    },
    [REFILL_STATUS.UNKNOWN_DURATION]: {
        label: "No duration",
        icon: "help",
        badge: "bg-slate-100 text-slate-700",
        dot: "bg-slate-400",
    },
};

// Permission, not urgency — so a different palette. Violet for reachable,
// neutral for "we simply never asked", rose reserved for an actual refusal.
const CONTACT_STYLES = {
    [CONTACTABILITY.CONTACTABLE]: {
        label: "Reachable",
        icon: "chat",
        badge: "bg-violet-100 text-violet-800",
        dot: "bg-violet-500",
    },
    [CONTACTABILITY.NOT_OPTED_IN]: {
        label: "Not opted in",
        icon: "do_not_disturb_on",
        badge: "bg-slate-100 text-slate-600",
        dot: "bg-slate-400",
    },
    [CONTACTABILITY.NO_PHONE]: {
        label: "No usable number",
        icon: "phone_disabled",
        badge: "bg-slate-100 text-slate-600",
        dot: "bg-slate-400",
    },
    [CONTACTABILITY.OPTED_OUT]: {
        label: "Opted out",
        icon: "block",
        badge: "bg-rose-100 text-rose-800",
        dot: "bg-rose-500",
    },
};

const statusStyle = makeRiskStyleResolver(STATUS_STYLES);
const contactStyle = makeRiskStyleResolver(CONTACT_STYLES);

export function RefillStatusBadge({ status }) {
    return <RiskBadgeBase style={statusStyle(status)} />;
}

export function ContactabilityBadge({ contactability }) {
    return <RiskBadgeBase style={contactStyle(contactability)} />;
}
