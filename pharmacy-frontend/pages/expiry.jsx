import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import ExpiryFilters from "@/components/expiry/ExpiryFilters";
import ExpirySummaryCards, {
    ExpirySummaryCardsSkeleton,
} from "@/components/expiry/ExpirySummaryCards";
import ExpiryRiskTable, {
    ExpiryRiskEmpty,
    ExpiryRiskTableSkeleton,
} from "@/components/expiry/ExpiryRiskTable";
import ExpiryAiSummary from "@/components/expiry/ExpiryAiSummary";
import { useExpiryRisk } from "@/hooks/useExpiryRisk";

const DEFAULT_FILTERS = { windowDays: 30, riskLevel: "", limit: 10 };

function ErrorState({ error, onRetry }) {
    return (
        <Card className="items-center justify-center py-16 text-center">
            <Icon name="error" size={40} className="text-rose-400" />
            <p className="mt-3 text-sm font-medium">Unable to load expiry analysis.</p>
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

function ExpiryPage() {
    const [filters, setFilters] = useState(DEFAULT_FILTERS);
    const {
        report,
        loading,
        error,
        explanation,
        explaining,
        explainError,
        analyze,
    } = useExpiryRisk();

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
                        <Icon name="hourglass_bottom" size={30} className="text-primary" />
                        Expiry Risk
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Not everything expiring is a problem. This is the stock that
                        won&apos;t sell in time — ranked by what it costs you.
                    </p>
                </div>

                {report && (
                    <div className="hidden shrink-0 text-right sm:block">
                        <p className="text-xs text-muted-foreground">Assessed for</p>
                        <p className="text-sm font-medium">{report.generated_for}</p>
                    </div>
                )}
            </div>

            <ExpiryFilters
                filters={filters}
                onChange={setFilters}
                onAnalyze={() => analyze(filters)}
                loading={loading}
            />

            {loading && (
                <div className="space-y-6">
                    <ExpirySummaryCardsSkeleton />
                    <ExpiryRiskTableSkeleton />
                </div>
            )}

            {!loading && error && (
                <ErrorState error={error} onRetry={() => analyze(filters)} />
            )}

            {!loading && !error && report && (
                <div className="space-y-6">
                    <ExpirySummaryCards report={report} />

                    {isEmpty ? (
                        <ExpiryRiskEmpty
                            windowDays={report.window_days}
                            riskLevel={filters.riskLevel}
                        />
                    ) : (
                        <>
                            <ExpiryAiSummary
                                explanation={explanation}
                                explaining={explaining}
                                error={explainError}
                                notes={report.notes}
                            />
                            <ExpiryRiskTable items={report.items} />
                            <p className="text-center text-xs text-muted-foreground">
                                Showing {report.items.length} of{" "}
                                {report.total_batches_reviewed} batches reviewed ·
                                demand estimated over{" "}
                                {report.demand_lookback_days} days · computed in{" "}
                                {report.execution_time_ms} ms
                            </p>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}

ExpiryPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default ExpiryPage;
