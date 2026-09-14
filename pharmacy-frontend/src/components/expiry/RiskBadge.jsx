import RiskBadgeBase, { makeRiskStyleResolver } from "@/components/ui/risk-badge";

/**
 * Colour and wording for one EXPIRY risk level.
 *
 * Levels come from the backend's RiskLevel enum. `expired` is slate rather than a
 * hotter red than `critical`: the money is already gone, so it is a write-off to
 * process, not an emergency to trade out of.
 *
 * The pill itself is rendered by the shared base. This file owns only the map,
 * because the inventory agent has its own enum with different members.
 */
export const RISK_STYLES = {
    expired: {
        label: "Expired",
        icon: "block",
        badge: "bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100",
        dot: "bg-slate-500",
    },
    critical: {
        label: "Critical",
        icon: "e911_emergency",
        badge: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
        dot: "bg-rose-500",
    },
    high: {
        label: "High",
        icon: "warning",
        badge: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200",
        dot: "bg-orange-500",
    },
    medium: {
        label: "Medium",
        icon: "schedule",
        badge: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        dot: "bg-amber-500",
    },
    low: {
        label: "Low",
        icon: "check_circle",
        badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
        dot: "bg-emerald-500",
    },
};

export const riskStyle = makeRiskStyleResolver(RISK_STYLES);

export default function RiskBadge({ level }) {
    return <RiskBadgeBase style={riskStyle(level)} />;
}
