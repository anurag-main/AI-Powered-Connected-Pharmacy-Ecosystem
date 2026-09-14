import { useCallback, useEffect, useRef, useState } from "react";
import {
    explainInventoryRisk,
    getInventoryReport,
    toQuery,
} from "@/lib/api/inventory";

/**
 * Owns the two-step load for the Inventory Risk page.
 *
 *   1. /report  — deterministic, fast, free. The table and cards render off this.
 *   2. /explain — the AI paragraph for the SAME query, started only once the
 *                 report succeeds.
 *
 * They are separate pieces of state on purpose. The model being slow, rate-limited
 * or down must not stop a pharmacist seeing where their capital is stuck, so the
 * explanation has its own loading and error flags and its failure is never fatal.
 * The measured gap justifies it: 44ms for the report against 5.5s for the prose.
 *
 * Filters live in the page; this hook is told what to fetch. It calculates nothing.
 */
export function useInventoryRisk() {
    const [report, setReport] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const [explanation, setExplanation] = useState(null);
    const [explaining, setExplaining] = useState(false);
    const [explainError, setExplainError] = useState(null);

    // Bumped on every run. A response whose id is stale is discarded, so clicking
    // Analyze twice quickly can never render the first response over the second.
    const runIdRef = useRef(0);
    // Cleared on unmount so a late response cannot setState on a dead component.
    const mountedRef = useRef(true);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const analyze = useCallback(async (filters) => {
        const runId = ++runIdRef.current;
        const isCurrent = () => mountedRef.current && runIdRef.current === runId;

        const query = toQuery(filters);

        setLoading(true);
        setError(null);
        setExplanation(null);
        setExplainError(null);

        const result = await getInventoryReport(query);
        if (!isCurrent()) return;

        if (!result.ok) {
            setError({ message: result.error, requestId: result.requestId });
            setReport(null);
            setLoading(false);
            return;
        }

        setReport(result.data);
        setLoading(false);

        // Nothing matched the filter needs no paragraph, and asking for one wastes
        // a call on a report with no rows to describe.
        if (!result.data.items?.length) return;

        setExplaining(true);
        const explained = await explainInventoryRisk(query);
        if (!isCurrent()) return;

        if (explained.ok) {
            setExplanation(explained.data);
        } else {
            // Deliberately not fatal — the numbers above are still correct.
            setExplainError(explained.error);
        }
        setExplaining(false);
    }, []);

    return {
        report,
        loading,
        error,
        explanation,
        explaining,
        explainError,
        analyze,
    };
}
