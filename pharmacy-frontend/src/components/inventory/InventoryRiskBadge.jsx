import RiskBadgeBase, { makeRiskStyleResolver } from "@/components/ui/risk-badge";

/**
 * Colour and wording for one INVENTORY risk level.
 *
 * Levels come from the backend's InventoryRiskLevel enum. Three names are shared
 * with the expiry enum and two are not, which is exactly why this map is separate
 * rather than merged into the expiry one.
 *
 * The severity ramp matches the rest of the app — rose, orange, amber, emerald —
 * so a colour means the same thing on every screen.
 *
 * `dead` sits outside that ramp in violet on purpose. It is not "worse overstock";
 * it is a different kind of problem. Overstock is stock moving too slowly for its
 * volume, and you can trade out of it. Dead stock is not moving at all. The expiry
 * page makes the same distinction with slate for `expired`.
 */
export const INVENTORY_RISK_STYLES = {
    dead: {
        label: "Dead",
        icon: "do_not_disturb_on",
        badge: "bg-violet-100 text-violet-900 dark:bg-violet-950 dark:text-violet-200",
        dot: "bg-violet-500",
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
        icon: "trending_down",
        badge: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
        dot: "bg-amber-500",
    },
    healthy: {
        label: "Healthy",
        icon: "check_circle",
        badge: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
        dot: "bg-emerald-500",
    },
};

export const inventoryRiskStyle = makeRiskStyleResolver(INVENTORY_RISK_STYLES);

export default function InventoryRiskBadge({ level }) {
    return <RiskBadgeBase style={inventoryRiskStyle(level)} />;
}
