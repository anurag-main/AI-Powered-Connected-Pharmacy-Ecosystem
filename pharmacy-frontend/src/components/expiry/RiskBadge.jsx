import Icon from "@/components/ui/icon";

/**
 * Colour and wording for one risk level.
 *
 * Levels come from the backend's RiskLevel enum. `expired` is slate rather than a
 * hotter red than `critical`: the money is already gone, so it is a write-off to
 * process, not an emergency to trade out of.
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

const FALLBACK = {
    label: "Unknown",
    icon: "help",
    badge: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
};

/** Never throws on an unrecognised level — a new backend level degrades, not crashes. */
export function riskStyle(level) {
    return RISK_STYLES[level] || FALLBACK;
}

export default function RiskBadge({ level }) {
    const style = riskStyle(level);

    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${style.badge}`}
        >
            <Icon name={style.icon} size={13} />
            {style.label}
        </span>
    );
}
