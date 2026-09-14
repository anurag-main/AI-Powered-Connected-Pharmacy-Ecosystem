import { useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import Icon from "@/components/ui/icon";
import ReceiptLinesEditor from "@/components/receive/ReceiptLinesEditor";
import RecordedReceipt from "@/components/receive/RecordedReceipt";
import RecentReceipts from "@/components/receive/RecentReceipts";
import { useGoodsReceipt } from "@/hooks/useGoodsReceipt";
import { emptyLine, isLineComplete } from "@/lib/api/purchases";

/**
 * Goods receipt — the only screen that puts stock INTO the system.
 *
 * Everything else in this app either reads batches (expiry, inventory, reorder)
 * or decrements them (billing). Before this page existed, every batch in the
 * database had been written by a seed script, which meant stock could only ever
 * go down and the shop would eventually have run itself to zero.
 *
 * NO BUSINESS LOGIC LIVES HERE.
 * The page checks that fields are FILLED IN, and nothing else. Whether the
 * expiry is far enough away, whether the cost is under MRP, whether this batch
 * contradicts one already on the shelf, what the invoice totals — all of it is
 * decided by goods_receipt_service.py and shown here as it came back.
 */

const SUPPLIER_NEW = "__new__";

function ReceivePage() {
    const { medicines, suppliers, recent, loadError, submitting, result, error, requestId, submit, reset } =
        useGoodsReceipt();

    const [supplierChoice, setSupplierChoice] = useState("");
    const [supplierName, setSupplierName] = useState("");
    const [invoiceNumber, setInvoiceNumber] = useState("");
    const [purchaseDate, setPurchaseDate] = useState("");
    const [lines, setLines] = useState([emptyLine()]);

    const usingNewSupplier = supplierChoice === SUPPLIER_NEW;
    const supplierReady = usingNewSupplier ? supplierName.trim().length > 0 : Boolean(supplierChoice);
    const linesReady = lines.length > 0 && lines.every(isLineComplete);
    const canSubmit = supplierReady && linesReady && !submitting;

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (!canSubmit) return;

        const response = await submit({
            supplierId: usingNewSupplier ? "" : supplierChoice,
            supplierName: usingNewSupplier ? supplierName : "",
            invoiceNumber,
            purchaseDate,
            lines,
        });

        // Clear the form ONLY on a confirmed success. On a failure everything the
        // pharmacist typed stays exactly where it was — the usual cause is one
        // wrong field on one line, and wiping a ten-line invoice to punish a
        // typo is how people stop using a system.
        if (response?.ok) {
            setLines([emptyLine()]);
            setInvoiceNumber("");
            setPurchaseDate("");
        }
    };

    const handleRecordAnother = () => {
        reset();
        setLines([emptyLine()]);
    };

    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                    <Icon name="local_shipping" size={30} className="text-primary" />
                    Receive Stock
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                    Record a supplier delivery. This is the only way stock enters the system.
                </p>
            </div>

            {loadError && (
                <div className="rounded-xl bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm">
                    {loadError}
                </div>
            )}

            {result && (
                <RecordedReceipt
                    receipt={result}
                    requestId={requestId}
                    onRecordAnother={handleRecordAnother}
                />
            )}

            <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
                <div className="xl:col-span-2">
                    <Card className="p-5 space-y-5">
                        {medicines === null ? (
                            <div className="space-y-3" data-testid="receive-loading">
                                {[...Array(5)].map((_, i) => (
                                    <Skeleton key={i} className="h-10 w-full" />
                                ))}
                            </div>
                        ) : (
                            <form onSubmit={handleSubmit} className="space-y-5" noValidate>
                                {/* ── Who it came from ─────────────────────────── */}
                                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                    <div className={usingNewSupplier ? "sm:col-span-1" : "sm:col-span-2"}>
                                        <label
                                            htmlFor="supplier"
                                            className="block text-xs font-medium text-muted-foreground mb-1"
                                        >
                                            Supplier
                                        </label>
                                        <select
                                            id="supplier"
                                            value={supplierChoice}
                                            disabled={submitting}
                                            onChange={(e) => setSupplierChoice(e.target.value)}
                                            className="w-full h-9 rounded-md border border-input bg-background px-2 text-sm disabled:opacity-50"
                                        >
                                            <option value="">Select…</option>
                                            {suppliers.map((s) => (
                                                <option key={s.id} value={s.id}>
                                                    {s.name}
                                                </option>
                                            ))}
                                            <option value={SUPPLIER_NEW}>+ New supplier…</option>
                                        </select>
                                    </div>

                                    {usingNewSupplier && (
                                        <div className="sm:col-span-1">
                                            <label
                                                htmlFor="supplier-name"
                                                className="block text-xs font-medium text-muted-foreground mb-1"
                                            >
                                                New supplier name
                                            </label>
                                            <Input
                                                id="supplier-name"
                                                value={supplierName}
                                                disabled={submitting}
                                                onChange={(e) => setSupplierName(e.target.value)}
                                                placeholder="Medlife Distributors"
                                                className="h-9"
                                            />
                                        </div>
                                    )}

                                    <div className="sm:col-span-1">
                                        <label
                                            htmlFor="invoice-number"
                                            className="block text-xs font-medium text-muted-foreground mb-1"
                                        >
                                            Invoice no. <span className="font-normal">(optional)</span>
                                        </label>
                                        <Input
                                            id="invoice-number"
                                            value={invoiceNumber}
                                            disabled={submitting}
                                            onChange={(e) => setInvoiceNumber(e.target.value)}
                                            placeholder="INV-2026-114"
                                            className="h-9"
                                        />
                                    </div>

                                    <div className="sm:col-span-1">
                                        <label
                                            htmlFor="purchase-date"
                                            className="block text-xs font-medium text-muted-foreground mb-1"
                                        >
                                            Invoice date <span className="font-normal">(optional)</span>
                                        </label>
                                        <Input
                                            id="purchase-date"
                                            type="date"
                                            value={purchaseDate}
                                            disabled={submitting}
                                            onChange={(e) => setPurchaseDate(e.target.value)}
                                            className="h-9"
                                        />
                                    </div>
                                </div>

                                <div className="border-t border-border/60" />

                                <ReceiptLinesEditor
                                    lines={lines}
                                    medicines={medicines}
                                    onChange={setLines}
                                    disabled={submitting}
                                />

                                {error && (
                                    <div
                                        role="alert"
                                        className="rounded-lg bg-rose-50 text-rose-700 border border-rose-200 px-4 py-3 text-sm"
                                    >
                                        {error}
                                        {requestId && (
                                            <span className="block text-xs text-rose-600/70 mt-1">
                                                ref {requestId}
                                            </span>
                                        )}
                                    </div>
                                )}

                                <div className="flex items-center justify-between gap-4 pt-1">
                                    <p className="text-xs text-muted-foreground">
                                        Totals are calculated by the server when this is saved.
                                    </p>
                                    <Button type="submit" disabled={!canSubmit}>
                                        {submitting ? "Recording…" : "Record receipt"}
                                    </Button>
                                </div>
                            </form>
                        )}
                    </Card>
                </div>

                <div className="xl:col-span-1">
                    <RecentReceipts receipts={recent} />
                </div>
            </div>
        </div>
    );
}

ReceivePage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default ReceivePage;
