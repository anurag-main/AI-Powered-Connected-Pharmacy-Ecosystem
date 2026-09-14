import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import InventoryFilters from "@/components/inventory/InventoryFilters";
import InventorySummaryCards, {
    InventorySummaryCardsSkeleton,
} from "@/components/inventory/InventorySummaryCards";
import InventoryRiskTable, {
    InventoryRiskEmpty,
    InventoryRiskTableSkeleton,
} from "@/components/inventory/InventoryRiskTable";
import InventoryAiSummary from "@/components/inventory/InventoryAiSummary";
import { useInventoryRisk } from "@/hooks/useInventoryRisk";

const DEFAULT_FILTERS = {
    targetCoverDays: 60,
    riskLevel: "",
    sort: "risk",
    limit: 10,
};

const rupee = (n) =>
    `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function ErrorState({ error, onRetry }) {
    return (
        <Card className="items-center justify-center py-16 text-center">
            <Icon name="error" size={40} className="text-rose-400" />
            <p className="mt-3 text-sm font-medium">
                Unable to load the inventory analysis.
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{error.message}</p>
            <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
                <Icon name="refresh" size={16} /> Try again
            </Button>
            {/* The backend stamps this on every response; quoting it makes a report traceable. */}
            {error.requestId && (
                <p className="mt-3 font-mono text-[10px] text-muted-foreground/70">
                    ref {error.requestId}
                </p>
            )}
        </Card>
    );
}

function InventoryPage() {
    const [filters, setFilters] = useState(DEFAULT_FILTERS);
    const {
        report,
        loading,
        error,
        explanation,
        explaining,
        explainError,
        analyze,
    } = useInventoryRisk();

    // Load once on mount with the defaults, then only when Analyze is pressed.
    // Not keyed on `filters`: changing a dropdown should not fire a request, or a
    // pharmacist adjusting three filters pays for three reports.
    useEffect(() => {
        analyze(DEFAULT_FILTERS);
    }, [analyze]);

    const isEmpty = report && report.items.length === 0;

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight sm:text-3xl">
                        <Icon name="savings" size={30} className="text-primary" />
                        Inventory Risk
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Holding stock is not the problem. This is the stock holding
                        cash that could be working — ranked by how much.
                    </p>
                </div>

                {report && (
                    <div className="hidden shrink-0 text-right sm:block">
                        <p className="text-xs text-muted-foreground">Assessed for</p>
                        <p className="text-sm font-medium">{report.generated_for}</p>
                    </div>
                )}
            </div>

            <InventoryFilters
                filters={filters}
                onChange={setFilters}
                onAnalyze={() => analyze(filters)}
                loading={loading}
            />

            {loading && (
                <div className="space-y-6">
                    <InventorySummaryCardsSkeleton />
                    <InventoryRiskTableSkeleton />
                </div>
            )}

            {!loading && error && (
                <ErrorState error={error} onRetry={() => analyze(filters)} />
            )}

            {!loading && !error && report && (
                <div className="space-y-6">
                    <InventorySummaryCards report={report} />

                    {isEmpty ? (
                        <InventoryRiskEmpty
                            targetCoverDays={report.target_cover_days}
                            riskLevel={filters.riskLevel}
                        />
                    ) : (
                        <>
                            <InventoryAiSummary
                                explanation={explanation}
                                explaining={explaining}
                                error={explainError}
                                notes={report.notes}
                            />
                            <InventoryRiskTable items={report.items} />

                            {/* Both subtotals, stated separately. The cards above are
                                shop-wide; this line is the filtered view, and
                                conflating them is the exact mistake the AI made
                                during the backend round trip. */}
                            <p className="text-center text-xs text-muted-foreground">
                                Showing {report.items.length} of{" "}
                                {report.items_matching_filter} matching medicine(s) ·
                                this view holds{" "}
                                {rupee(report.capital_at_risk_in_view)} at risk ·
                                velocity over {report.demand_lookback_days} days ·
                                computed in {report.execution_time_ms} ms
                            </p>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

InventoryPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default InventoryPage;
