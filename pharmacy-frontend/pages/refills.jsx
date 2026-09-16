import { useCallback, useEffect, useRef, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import RefillTable from "@/components/refill/RefillTable";
import RefillSummaryCards from "@/components/refill/RefillSummaryCards";
import { getRefillCandidates, sendRefillReminder, VIEW_OPTIONS } from "@/lib/api/refill";

/**
 * /refills — who looks due for a refill, why, and whether a reminder went out.
 *
 * M6.2 built the decision; M6.3 added the WhatsApp channel, so this screen now
 * has a Remind button. What it does NOT have is any knowledge of WhatsApp: it
 * posts the refill OPPORTUNITY's identity to our own API, and the server
 * re-derives the candidate and re-checks consent before anything is sent. There
 * is no path from this app to Meta, and no token ever reaches the browser.
 *
 * NO BUSINESS LOGIC HERE. Days overdue, expected dates, the reason sentence and
 * the reminder status all arrive computed. The button being enabled is a
 * convenience, never a permission — a hand-crafted click still cannot reach
 * someone who opted out.
 *
 * Statuses are never optimistic. A 200 means Meta accepted the message, which is
 * not the same as the customer receiving it; "delivered" and "read" only ever
 * come from a webhook.
 */

function RefillsPage() {
    const [view, setView] = useState("due");
    const [data, setData] = useState(null); // null = loading
    const [error, setError] = useState(null);
    // The row currently being sent, and the outcome of the last attempt.
    const [sendingId, setSendingId] = useState(null);
    const [sendResult, setSendResult] = useState(null);

    // Guards a slow response from overwriting a newer one, and a setState after
    // unmount. Same pattern as useInventoryRisk.
    const runIdRef = useRef(0);
    const mountedRef = useRef(true);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const load = useCallback(async (nextView) => {
        const runId = ++runIdRef.current;
        setData(null);
        setError(null);

        const result = await getRefillCandidates(nextView);

        // A stale response from a previous filter must not win.
        if (!mountedRef.current || runId !== runIdRef.current) return;

        if (result.ok) {
            setData(result.data);
        } else {
            setError(result.error);
        }
    }, []);

    useEffect(() => {
        load(view);
    }, [load, view]);

    /**
     * Send one reminder, then RE-READ from the server.
     *
     * Deliberately not optimistic. A 200 means Meta accepted the message, which
     * is not the same as the customer receiving it, and "delivered" can only
     * ever come from a webhook. Showing a hopeful status would have the
     * dashboard claim something it does not know.
     */
    const handleSend = useCallback(
        async (candidate) => {
            if (sendingId !== null) return;
            setSendingId(candidate.source_sale_item_id);
            setSendResult(null);

            const result = await sendRefillReminder(candidate);

            if (!mountedRef.current) return;
            setSendingId(null);
            setSendResult(
                result.ok
                    ? { ok: result.data?.sent === true, text: result.data?.reason || "Done." }
                    : { ok: false, text: result.error },
            );

            // Re-read so the Reminder column shows what the backend recorded.
            await load(view);
        },
        [load, sendingId, view],
    );

    const candidates = data?.candidates ?? [];

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                        <Icon name="event_repeat" size={30} className="text-primary" />
                        Refills
                    </h1>
                    <p className="text-sm text-muted-foreground mt-1">
                        Customers whose medicine should have run out. Reminders are sent
                        by the server, only to customers who opted in.
                    </p>
                </div>

                <div>
                    <label
                        htmlFor="refill-view"
                        className="block text-xs font-medium text-muted-foreground mb-1"
                    >
                        Show
                    </label>
                    <select
                        id="refill-view"
                        value={view}
                        onChange={(e) => setView(e.target.value)}
                        className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    >
                        {VIEW_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>
                                {option.label}
                            </option>
                        ))}
                    </select>
                </div>
            </div>

            {/* ---- outcome of the last manual send ---- */}
            {sendResult && (
                <div
                    role="status"
                    className={`rounded-xl border px-4 py-3 text-sm ${
                        sendResult.ok
                            ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                            : "bg-amber-50 text-amber-800 border-amber-200"
                    }`}
                >
                    {sendResult.text}
                </div>
            )}

            {/* ---- error ---- */}
            {error && (
                <div
                    role="alert"
                    className="rounded-xl bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm"
                >
                    {error}
                </div>
            )}

            {/* ---- loading ---- */}
            {!error && data === null && (
                <div className="space-y-4" data-testid="refills-loading">
                    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                        {[...Array(4)].map((_, i) => (
                            <Skeleton key={i} className="h-24 w-full" />
                        ))}
                    </div>
                    <Card className="p-6 space-y-3">
                        {[...Array(6)].map((_, i) => (
                            <Skeleton key={i} className="h-8 w-full" />
                        ))}
                    </Card>
                </div>
            )}

            {/* ---- success / empty ---- */}
            {!error && data !== null && (
                <>
                    <RefillSummaryCards summary={data.summary} />

                    {candidates.length === 0 ? (
                        <Card className="p-10 text-center" data-testid="refills-empty">
                            <Icon
                                name="check_circle"
                                size={40}
                                className="text-emerald-500 mx-auto"
                            />
                            <p className="mt-3 font-medium text-foreground">
                                Nobody is due right now.
                            </p>
                            <p className="mt-1 text-sm text-muted-foreground">
                                Customers appear here once their recorded days supply runs
                                out and they have not bought the medicine again.
                            </p>
                        </Card>
                    ) : (
                        <RefillTable
                            candidates={candidates}
                            notifications={data.notifications || {}}
                            onSend={handleSend}
                            sendingId={sendingId}
                        />
                    )}

                    {data.notes?.length > 0 && (
                        <Card className="p-4">
                            <h2 className="text-xs font-semibold text-muted-foreground mb-2">
                                What this scan could not see
                            </h2>
                            <ul className="space-y-1">
                                {data.notes.map((note, i) => (
                                    <li
                                        key={i}
                                        className="text-xs text-muted-foreground flex gap-2"
                                    >
                                        <Icon
                                            name="info"
                                            size={14}
                                            className="shrink-0 mt-0.5"
                                        />
                                        {note}
                                    </li>
                                ))}
                            </ul>
                        </Card>
                    )}

                    <p className="text-xs text-muted-foreground">
                        Showing {candidates.length} of {data.summary?.due ?? 0} due · scanned{" "}
                        {data.summary?.purchases_reviewed ?? 0} purchase(s) over{" "}
                        {data.lookback_days} days · as of {data.as_of}
                    </p>
                </>
            )}
        </div>
    );
}

RefillsPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default RefillsPage;
