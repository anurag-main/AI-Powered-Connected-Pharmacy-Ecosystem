import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import { getReorderSuggestions } from "@/lib/api";

// Small badge showing whether a proposal came from deterministic math ("Rule")
// or the LLM judgment node ("AI").
function SourceBadge({ source }) {
    const isAI = source === "llm";
    return (
        <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                isAI ? "bg-violet-100 text-violet-700" : "bg-blue-100 text-blue-700"
            }`}
        >
            <Icon name={isAI ? "smart_toy" : "calculate"} size={13} />
            {isAI ? "AI" : "Rule"}
        </span>
    );
}

function ReorderPage() {
    const [proposals, setProposals] = useState(null); // null = loading
    const [error, setError] = useState(false);
    const [status, setStatus] = useState({}); // medicine_id -> "approved" | "dismissed"

    function load() {
        setProposals(null);
        setError(false);
        setStatus({});
        getReorderSuggestions()
            .then(({ ok, data }) => (ok ? setProposals(data.proposals || []) : setError(true)))
            .catch(() => setError(true));
    }

    useEffect(() => {
        load();
    }, []);

    const setRow = (id, s) => setStatus((prev) => ({ ...prev, [id]: s }));
    const approvedCount = Object.values(status).filter((s) => s === "approved").length;

    return (
        <div className="space-y-6">
            <div className="flex items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                        <Icon name="inventory_2" size={30} className="text-primary" />
                        Reorder Suggestions
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        What to restock. Math handles the clear cases; the AI judges items with no
                        recent sales. You approve.
                    </p>
                </div>
                <Button variant="outline" size="sm" onClick={load} disabled={proposals === null}>
                    <Icon name="refresh" size={16} /> Refresh
                </Button>
            </div>

            {error && (
                <div className="rounded-xl bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm">
                    Could not load suggestions — is the backend running on :8000?
                </div>
            )}

            {approvedCount > 0 && (
                <div className="rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 px-4 py-3 text-sm flex items-center gap-2">
                    <Icon name="check_circle" size={18} />
                    {approvedCount} approved. (Saving a purchase order is the next step — for now this
                    is review-only.)
                </div>
            )}

            {proposals === null && !error ? (
                <Card className="p-6 space-y-3">
                    {[...Array(4)].map((_, i) => (
                        <Skeleton key={i} className="h-8 w-full" />
                    ))}
                </Card>
            ) : (
                proposals &&
                (proposals.length === 0 ? (
                    <Card className="items-center justify-center py-20 text-muted-foreground">
                        <Icon name="task_alt" size={40} className="text-emerald-400" />
                        <p className="text-sm mt-2">Nothing to reorder — stock looks healthy.</p>
                    </Card>
                ) : (
                    <Card className="overflow-hidden p-0 gap-0">
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                                        <th className="text-left font-semibold px-4 py-3">Medicine</th>
                                        <th className="text-right font-semibold px-4 py-3">Stock</th>
                                        <th className="text-right font-semibold px-4 py-3">Order</th>
                                        <th className="text-left font-semibold px-4 py-3">Why</th>
                                        <th className="text-right font-semibold px-4 py-3">Action</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {proposals.map((p) => {
                                        const s = status[p.medicine_id];
                                        return (
                                            <tr
                                                key={p.medicine_id}
                                                className={`border-b border-border/60 last:border-0 ${
                                                    s === "dismissed" ? "opacity-40" : ""
                                                }`}
                                            >
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-medium text-foreground">{p.name}</span>
                                                        <SourceBadge source={p.source} />
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-right tabular-nums">{p.current_stock}</td>
                                                <td className="px-4 py-3 text-right tabular-nums font-semibold">
                                                    {p.reorder_qty}
                                                </td>
                                                <td className="px-4 py-3 text-muted-foreground max-w-xs">
                                                    {p.reason
                                                        ? p.reason
                                                        : p.days_of_cover != null
                                                          ? `~${p.days_of_cover.toFixed(1)} days of stock left`
                                                          : "—"}
                                                </td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center justify-end gap-2">
                                                        {s === "approved" ? (
                                                            <span className="inline-flex items-center gap-1 text-emerald-600 text-xs font-medium">
                                                                <Icon name="check_circle" size={16} /> Approved
                                                            </span>
                                                        ) : (
                                                            <>
                                                                <Button
                                                                    size="sm"
                                                                    onClick={() => setRow(p.medicine_id, "approved")}
                                                                >
                                                                    Approve
                                                                </Button>
                                                                <Button
                                                                    size="sm"
                                                                    variant="ghost"
                                                                    onClick={() => setRow(p.medicine_id, "dismissed")}
                                                                >
                                                                    Dismiss
                                                                </Button>
                                                            </>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                ))
            )}
        </div>
    );
}

ReorderPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default ReorderPage;
