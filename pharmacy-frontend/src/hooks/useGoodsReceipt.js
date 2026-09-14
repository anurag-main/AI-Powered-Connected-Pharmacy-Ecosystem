import { useCallback, useEffect, useRef, useState } from "react";
import { listMedicines } from "@/lib/api";
import {
    listRecentReceipts,
    listSuppliers,
    recordGoodsReceipt,
    toReceiptPayload,
} from "@/lib/api/purchases";

/**
 * Everything the goods receipt page needs from the network.
 *
 * Three reference loads on mount (medicines, suppliers, recent receipts) and one
 * write. They are kept in one hook so the page component stays about layout.
 *
 * WHY THE SUBMIT GUARD MATTERS MORE HERE THAN ANYWHERE ELSE
 * ---------------------------------------------------------
 * On a read-only page a double click costs a wasted query. On this page it
 * creates the delivery twice — and it would not even fail loudly, because the
 * second request is perfectly valid: the batch already exists, same expiry, same
 * cost, so the service TOPS IT UP and the shop's stock is silently doubled.
 *
 * So `submitting` is checked inside the submit function, not only used to
 * disable the button. A disabled attribute is a hint to a mouse; it is not a
 * guarantee, and Enter-key submits and fast double clicks both get past it.
 */
export function useGoodsReceipt() {
    const [medicines, setMedicines] = useState(null); // null = still loading
    const [suppliers, setSuppliers] = useState([]);
    const [recent, setRecent] = useState([]);
    const [loadError, setLoadError] = useState(null);

    const [submitting, setSubmitting] = useState(false);
    const [result, setResult] = useState(null); // the recorded receipt, from the server
    const [error, setError] = useState(null);
    const [requestId, setRequestId] = useState(null);

    // Guards an unmounted component from a setState, and the double submit above.
    const mountedRef = useRef(true);
    const submittingRef = useRef(false);

    useEffect(() => {
        mountedRef.current = true;
        return () => {
            mountedRef.current = false;
        };
    }, []);

    const loadReference = useCallback(async () => {
        const [medicineResult, supplierResult, recentResult] = await Promise.all([
            listMedicines(),
            listSuppliers(),
            listRecentReceipts(10),
        ]);

        if (!mountedRef.current) return;

        // Only the medicine catalogue is fatal. Without it there is nothing to
        // pick from and the form cannot be used at all. A missing supplier list
        // still leaves the "new supplier" path, and the recent-receipts panel is
        // context, not function — neither should block stock intake.
        if (!medicineResult.ok) {
            setLoadError("Could not load the medicine catalogue. Is the backend running?");
            setMedicines([]);
        } else {
            setLoadError(null);
            setMedicines(medicineResult.data);
        }

        setSuppliers(supplierResult.ok ? supplierResult.data : []);
        setRecent(recentResult.ok ? recentResult.data : []);
    }, []);

    useEffect(() => {
        loadReference();
    }, [loadReference]);

    const submit = useCallback(
        async (form) => {
            if (submittingRef.current) return null; // the real double-submit guard
            submittingRef.current = true;
            setSubmitting(true);
            setError(null);
            setResult(null);

            const response = await recordGoodsReceipt(toReceiptPayload(form));

            if (!mountedRef.current) return null;

            setRequestId(response.requestId || null);
            if (response.ok) {
                setResult(response.data);
                // Refresh the recent panel so what was just recorded appears in
                // it. Deliberately not optimistic: the panel shows what the
                // server has, which is the whole point of showing it.
                listRecentReceipts(10).then((r) => {
                    if (mountedRef.current && r.ok) setRecent(r.data);
                });
            } else {
                setError(response.error);
            }

            submittingRef.current = false;
            setSubmitting(false);
            return response;
        },
        [],
    );

    /** Clear the last outcome so the form can be used again for the next invoice. */
    const reset = useCallback(() => {
        setResult(null);
        setError(null);
        setRequestId(null);
    }, []);

    return {
        medicines,
        suppliers,
        recent,
        loadError,
        submitting,
        result,
        error,
        requestId,
        submit,
        reset,
    };
}
