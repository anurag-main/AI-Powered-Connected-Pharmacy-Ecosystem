import { useCallback, useEffect, useState } from "react";
import { listCatalog } from "@/lib/api/billing";

/**
 * Loads the medicine catalog once, for the billing picker to search.
 *
 * Fetched whole and filtered in the browser rather than querying per keystroke:
 * a pharmacy catalog is small, and a counter needs the list to respond instantly
 * while a customer is standing there. Swap to a server-side search endpoint when
 * the catalog outgrows a single request.
 */
export function useMedicineCatalog() {
    const [medicines, setMedicines] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);

        const result = await listCatalog();

        if (result.ok && Array.isArray(result.data)) {
            setMedicines(result.data);
        } else {
            setError(result.error || "Could not load the medicine list.");
            setMedicines([]);
        }
        setLoading(false);
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    return { medicines, loading, error, reload: load };
}
