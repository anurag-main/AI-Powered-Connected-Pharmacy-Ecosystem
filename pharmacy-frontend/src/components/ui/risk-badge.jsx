import Icon from "@/components/ui/icon";

/**
 * The shared pill used by every risk level in the app.
 *
 * Only the rendering lives here. The level -> style map does NOT: the expiry agent
 * and the inventory agent have different enums that happen to share three member
 * names, so one shared map would either grow to hold both or quietly let an expiry
 * level render on an inventory row. Each feature owns its own map and passes the
 * resolved style in.
 */

/** Never throws on an unrecognised level — a new backend level degrades, not crashes. */
export const FALLBACK_STYLE = {
    label: "Unknown",
    icon: "help",
    badge: "bg-muted text-muted-foreground",
    dot: "bg-muted-foreground",
};

/** Build a `styleFor(level)` resolver from a feature's own level map. */
export function makeRiskStyleResolver(styles) {
    return (level) => styles[level] || FALLBACK_STYLE;
}

export default function RiskBadgeBase({ style }) {
    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${style.badge}`}
        >
            <Icon name={style.icon} size={13} />
            {style.label}
        </span>
    );
}
