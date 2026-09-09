import { useRef, useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Icon from "@/components/ui/icon";
import MedicinePicker from "@/components/billing/MedicinePicker";
import BillTable from "@/components/billing/BillTable";
import Receipt from "@/components/billing/Receipt";
import { useMedicineCatalog } from "@/hooks/useMedicineCatalog";
import { confirmSale, priceLine, UNIT_OPTIONS } from "@/lib/api/billing";

/**
 * New Bill — manual, line-by-line billing.
 *
 * Pick a medicine, set a quantity, add it. The SERVER prices every line: it picks
 * the FEFO batch and reads the MRP from the database, so no price is ever chosen
 * in the browser. `confirm` recomputes the whole bill again before writing it.
 *
 * No speech recognition and no LLM anywhere in this screen.
 */
function NewBillPage() {
    const { medicines, loading: catalogLoading, error: catalogError, reload } =
        useMedicineCatalog();

    const [selected, setSelected] = useState(null);
    const [quantity, setQuantity] = useState(1);
    const [unit, setUnit] = useState("strip");
    const [adding, setAdding] = useState(false);

    const [items, setItems] = useState([]);
    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [confirming, setConfirming] = useState(false);
    const [confirmedSale, setConfirmedSale] = useState(null);
    const [banner, setBanner] = useState(null); // { kind: "error" | "success", text }

    // Row ids are local to the bill being built; the server assigns nothing until
    // confirm, so a counter is enough and is stable across quantity edits.
    const nextId = useRef(0);

    async function handleAdd() {
        // A saved invoice is closed. Anything else goes on a new bill.
        if (!selected || adding || confirmedSale) return;

        setAdding(true);
        setBanner(null);

        const result = await priceLine({
            medicineId: selected.id,
            quantity: Number(quantity) || 1,
            name: selected.name,
            unit,
        });

        setAdding(false);

        if (!result.ok) {
            // 422 here is a real business answer: no unexpired, in-stock batch.
            const text =
                result.status === 422
                    ? `${selected.name} has no stock available.`
                    : result.error;
            setBanner({ kind: "error", text });
            return;
        }

        const line = result.data;

        setItems((prev) => {
            // Same medicine scanned twice is one line with a bigger quantity, the
            // way a counter actually works — not two identical rows to reconcile.
            const existing = prev.find((it) => it.medicine_id === line.medicine_id);
            if (existing) {
                return prev.map((it) =>
                    it.medicine_id === line.medicine_id
                        ? { ...it, quantity: it.quantity + line.quantity }
                        : it
                );
            }
            return [...prev, { ...line, _id: nextId.current++ }];
        });

        setSelected(null);
        setQuantity(1);
    }

    // After saving, the bill is a written invoice. Editing the rows on screen would
    // show one thing and have persisted another, so the table locks.
    const handleQtyChange = (id, qty) =>
        !confirmedSale &&
        setItems((prev) => prev.map((it) => (it._id === id ? { ...it, quantity: qty } : it)));

    const handleRemove = (id) =>
        !confirmedSale && setItems((prev) => prev.filter((it) => it._id !== id));

    // Saving and printing are separate on purpose. Saving writes the sale and
    // decrements stock; printing is a piece of paper. Bundling them meant a
    // cancelled print dialog looked like a failed sale, and a reprint was
    // impossible without billing the customer twice.
    async function handleSaveBill() {
        if (items.length === 0 || confirming || confirmedSale) return;

        setConfirming(true);
        setBanner(null);

        const result = await confirmSale(items, customerName, customerPhone);

        setConfirming(false);

        if (!result.ok) {
            setBanner({
                kind: "error",
                text:
                    result.status === 422
                        ? "Sale could not be saved — stock may have changed since you added a line."
                        : result.error,
            });
            return;
        }

        setConfirmedSale(result.data);
        setBanner({
            kind: "success",
            text: `Invoice #${result.data.sale_id} saved — total ₹${Number(
                result.data.total_amount
            ).toFixed(2)}. You can print it now, or find it later in Sales History.`,
        });
    }

    // Print as many times as needed; it changes nothing in the database.
    function handlePrint() {
        if (!confirmedSale) return;
        window.print();
    }

    function handleNewBill() {
        setItems([]);
        setSelected(null);
        setQuantity(1);
        setCustomerName("");
        setCustomerPhone("");
        setConfirmedSale(null);
        setBanner(null);
    }

    return (
        <div className="space-y-6">
            <div className="no-print flex items-start justify-between gap-4">
                <div>
                    <h1 className="flex items-center gap-3 text-2xl font-bold tracking-tight sm:text-3xl">
                        <Icon name="point_of_sale" size={30} className="text-primary" />
                        New Bill
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        Search a medicine, set the quantity, add it. Prices and batches
                        come from the server.
                    </p>
                </div>

                {items.length > 0 && (
                    <Button variant="outline" size="sm" onClick={handleNewBill}>
                        <Icon name="refresh" size={16} /> Clear bill
                    </Button>
                )}
            </div>

            {banner && (
                <div
                    className={`no-print rounded-xl border px-4 py-3 text-sm font-medium ${
                        banner.kind === "success"
                            ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/20 dark:text-emerald-300"
                            : "border-rose-200 bg-rose-50 text-rose-700 dark:bg-rose-950/20 dark:text-rose-300"
                    }`}
                >
                    {banner.text}
                </div>
            )}

            {catalogError && (
                <div className="no-print flex items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-950/20 dark:text-rose-300">
                    <Icon name="error" size={18} />
                    <span className="flex-1">{catalogError}</span>
                    <Button variant="outline" size="sm" onClick={reload}>
                        Try again
                    </Button>
                </div>
            )}

            {/* Add a line */}
            <Card className="no-print p-4 gap-0">
                <div className="flex flex-wrap items-end gap-4">
                    <div className="min-w-[16rem] flex-1">
                        <Label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                            Medicine
                        </Label>
                        <MedicinePicker
                            medicines={medicines}
                            loading={catalogLoading}
                            value={selected}
                            onSelect={setSelected}
                            disabled={adding || Boolean(confirmedSale)}
                        />
                    </div>

                    <div>
                        <Label
                            htmlFor="qty"
                            className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                        >
                            Qty
                        </Label>
                        <Input
                            id="qty"
                            type="number"
                            min={1}
                            value={quantity}
                            disabled={adding || Boolean(confirmedSale)}
                            onChange={(e) =>
                                setQuantity(Math.max(1, parseInt(e.target.value || "1", 10)))
                            }
                            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                            className="h-9 w-24 text-center"
                        />
                    </div>

                    <div>
                        <Label
                            htmlFor="unit"
                            className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                        >
                            Unit
                        </Label>
                        <select
                            id="unit"
                            value={unit}
                            disabled={adding || Boolean(confirmedSale)}
                            onChange={(e) => setUnit(e.target.value)}
                            className="h-9 w-32 rounded-lg border border-input bg-background px-3 text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/40 disabled:opacity-60"
                        >
                            {UNIT_OPTIONS.map((u) => (
                                <option key={u} value={u}>
                                    {u}
                                </option>
                            ))}
                        </select>
                    </div>

                    <Button
                        onClick={handleAdd}
                        disabled={!selected || adding || Boolean(confirmedSale)}
                        className="h-9"
                    >
                        <Icon
                            name={adding ? "progress_activity" : "add"}
                            size={18}
                            className={adding ? "animate-spin" : ""}
                        />
                        {adding ? "Pricing…" : "Add to bill"}
                    </Button>
                </div>
            </Card>

            <div className="no-print">
                <BillTable items={items} onQtyChange={handleQtyChange} onRemove={handleRemove} />
            </div>

            {items.length > 0 && (
                <Card className="no-print">
                    <CardContent className="space-y-4">
                        <div className="grid gap-4 sm:grid-cols-2">
                            <div className="space-y-1.5">
                                <Label htmlFor="cname">Customer name (optional)</Label>
                                <Input
                                    id="cname"
                                    value={customerName}
                                    onChange={(e) => setCustomerName(e.target.value)}
                                    placeholder="Anurag"
                                />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="cphone">Phone (optional)</Label>
                                <Input
                                    id="cphone"
                                    value={customerPhone}
                                    onChange={(e) => setCustomerPhone(e.target.value)}
                                    placeholder="9876543210"
                                />
                            </div>
                        </div>

                        <div className="flex flex-wrap gap-3">
                            <Button
                                size="lg"
                                onClick={handleSaveBill}
                                disabled={confirming || Boolean(confirmedSale)}
                            >
                                <Icon
                                    name={
                                        confirmedSale
                                            ? "check_circle"
                                            : confirming
                                              ? "progress_activity"
                                              : "save"
                                    }
                                    size={20}
                                    className={confirming ? "animate-spin" : ""}
                                />
                                {confirmedSale
                                    ? `Saved · #${confirmedSale.sale_id}`
                                    : confirming
                                      ? "Saving…"
                                      : "Save Bill"}
                            </Button>

                            {/* Disabled until saved: printing an unsaved bill hands the
                                customer a receipt for an invoice that does not exist. */}
                            <Button
                                size="lg"
                                variant={confirmedSale ? "default" : "outline"}
                                onClick={handlePrint}
                                disabled={!confirmedSale}
                                title={confirmedSale ? undefined : "Save the bill first"}
                            >
                                <Icon name="print" size={20} />
                                Print Receipt
                            </Button>

                            {confirmedSale && (
                                <Button size="lg" variant="outline" onClick={handleNewBill}>
                                    <Icon name="add" size={20} />
                                    New Bill
                                </Button>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            <Receipt sale={confirmedSale} />
        </div>
    );
}

NewBillPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default NewBillPage;
