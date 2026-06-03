import Icon from "@/components/ui/icon";

/**
 * NotFoundWarnings — shows the meaningful errors from a /quote response so the
 * owner knows which spoken names didn't match the catalog (and can fix the text
 * and re-quote). We filter out the internal node-cascade noise.
 */
export default function NotFoundWarnings({ errors = [] }) {
    const meaningful = errors.filter(
        (e) => e.includes("Medicine not found") || e.includes("Insufficient stock")
    );
    if (meaningful.length === 0) return null;

    return (
        <div className="rounded-xl border border-amber-300 bg-amber-50 dark:bg-amber-950/20 p-4">
            <div className="flex items-center gap-2 text-amber-700 dark:text-amber-300 font-semibold text-sm mb-2">
                <Icon name="warning" size={18} />
                Some items need attention
            </div>
            <ul className="space-y-1">
                {meaningful.map((e, i) => (
                    <li key={i} className="text-sm text-amber-800 dark:text-amber-200">• {e}</li>
                ))}
            </ul>
            <p className="text-xs text-amber-700/70 dark:text-amber-300/70 mt-2">
                Fix the spelling in the order text above and press “Get Prices” again.
            </p>
        </div>
    );
}
