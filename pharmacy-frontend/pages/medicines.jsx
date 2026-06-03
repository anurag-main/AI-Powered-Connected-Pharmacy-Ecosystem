import { useEffect, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import { listMedicines } from "@/lib/api";

const rupee = (n) => `₹${Number(n).toFixed(2)}`;

function MedicinesPage() {
    const [medicines, setMedicines] = useState(null); // null = loading
    const [error, setError] = useState(false);

    useEffect(() => {
        listMedicines()
            .then(({ ok, data }) => (ok ? setMedicines(data) : setError(true)))
            .catch(() => setError(true));
    }, []);

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                    <Icon name="medication" size={30} className="text-primary" />
                    Medicines
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                    The catalog the voice billing screen draws from.
                </p>
            </div>

            {error && (
                <div className="rounded-xl bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm">
                    Could not load medicines — is the backend running on :8000?
                </div>
            )}

            {medicines === null && !error ? (
                <Card className="p-6 space-y-3">
                    {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-8 w-full" />)}
                </Card>
            ) : (
                medicines && (
                    <Card className="overflow-hidden p-0 gap-0">
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-border bg-muted/40 text-muted-foreground">
                                        <th className="text-left font-semibold px-4 py-3">#</th>
                                        <th className="text-left font-semibold px-4 py-3">Name</th>
                                        <th className="text-right font-semibold px-4 py-3">MRP</th>
                                        <th className="text-left font-semibold px-4 py-3">HSN</th>
                                        <th className="text-left font-semibold px-4 py-3">Manufacturer</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {medicines.map((m) => (
                                        <tr key={m.id} className="border-b border-border/60 last:border-0">
                                            <td className="px-4 py-3 text-muted-foreground tabular-nums">{m.id}</td>
                                            <td className="px-4 py-3 font-medium text-foreground">{m.name}</td>
                                            <td className="px-4 py-3 text-right tabular-nums">{rupee(m.mrp)}</td>
                                            <td className="px-4 py-3 text-muted-foreground">{m.hsn_code}</td>
                                            <td className="px-4 py-3 text-muted-foreground">{m.manufacturer || "—"}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </Card>
                )
            )}
        </div>
    );
}

MedicinesPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default MedicinesPage;
