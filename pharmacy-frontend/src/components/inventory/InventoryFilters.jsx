import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import {
    LIMIT_OPTIONS,
    RISK_OPTIONS,
    SORT_OPTIONS,
    TARGET_COVER_OPTIONS,
} from "@/lib/api/inventory";

/**
 * The filter bar.
 *
 * The options are the backend's own bounds (InventoryRiskQuery), so the UI cannot
 * offer a filter the API would reject with a 422. Choosing here changes nothing on
 * screen until Analyze is pressed — same interaction model as the expiry page, and
 * for the same reason: the report is a deliberate act, and a table that reshuffles
 * while you are reading a dropdown is worse than one that waits.
 *
 * "Target cover" is the one filter that changes the numbers rather than narrowing
 * them. Lowering it makes more stock count as excess, so it is labelled as a
 * question ("Aim to hold") rather than as a filter.
 */
function Select({ id, label, value, onChange, options, disabled }) {
    return (
        <div className="flex flex-col gap-1.5">
            <label
                htmlFor={id}
                className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            >
                {label}
            </label>
            <select
                id={id}
                value={value}
                disabled={disabled}
                onChange={(e) => onChange(e.target.value)}
                className="h-9 min-w-[9.5rem] rounded-lg border border-input bg-background px-3 text-sm shadow-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
                {options.map((option) => (
                    <option key={String(option.value)} value={option.value}>
                        {option.label}
                    </option>
                ))}
            </select>
        </div>
    );
}

export default function InventoryFilters({ filters, onChange, onAnalyze, loading }) {
    const set = (key) => (value) => onChange({ ...filters, [key]: value });

    return (
        <Card className="p-4 gap-0">
            <div className="flex flex-wrap items-end gap-4">
                <Select
                    id="inventory-target-cover"
                    label="Aim to hold"
                    value={filters.targetCoverDays}
                    onChange={set("targetCoverDays")}
                    options={TARGET_COVER_OPTIONS}
                    disabled={loading}
                />
                <Select
                    id="inventory-risk"
                    label="Risk level"
                    value={filters.riskLevel}
                    onChange={set("riskLevel")}
                    options={RISK_OPTIONS}
                    disabled={loading}
                />
                <Select
                    id="inventory-sort"
                    label="Sort by"
                    value={filters.sort}
                    onChange={set("sort")}
                    options={SORT_OPTIONS}
                    disabled={loading}
                />
                <Select
                    id="inventory-limit"
                    label="Show"
                    value={filters.limit}
                    onChange={set("limit")}
                    options={LIMIT_OPTIONS}
                    disabled={loading}
                />

                <Button onClick={onAnalyze} disabled={loading} className="h-9">
                    <Icon
                        name={loading ? "progress_activity" : "play_arrow"}
                        size={18}
                        className={loading ? "animate-spin" : ""}
                    />
                    {loading ? "Analysing…" : "Analyze"}
                </Button>
            </div>
        </Card>
    );
}
