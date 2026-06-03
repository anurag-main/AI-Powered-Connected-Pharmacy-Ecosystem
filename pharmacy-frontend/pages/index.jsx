import { useState } from "react";
import DashboardLayout from "@/components/DashboardLayout";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import Icon from "@/components/ui/icon";
import VoiceButton from "@/components/VoiceButton";
import BillTable from "@/components/BillTable";
import NotFoundWarnings from "@/components/NotFoundWarnings";
import Receipt from "@/components/Receipt";
import { useSpeechRecognition } from "@/lib/useSpeechRecognition";
import { quoteSale, confirmSale } from "@/lib/api";

function NewBillPage() {
    const { supported, listening, transcript, setTranscript, start, stop } =
        useSpeechRecognition({ lang: "en-IN" });

    const [items, setItems] = useState([]);
    const [errors, setErrors] = useState([]);
    const [customerName, setCustomerName] = useState("");
    const [customerPhone, setCustomerPhone] = useState("");
    const [quoting, setQuoting] = useState(false);
    const [confirming, setConfirming] = useState(false);
    const [confirmedSale, setConfirmedSale] = useState(null);
    const [banner, setBanner] = useState(null); // { kind: 'error'|'success', text }

    // ── Get Prices: speak/typed text -> /quote -> priced rows ───────────────
    async function handleGetPrices() {
        if (!transcript.trim()) return;
        setQuoting(true);
        setBanner(null);
        try {
            const { ok, data } = await quoteSale(transcript);
            if (!ok) {
                setBanner({ kind: "error", text: "Could not price the order. Is the backend running?" });
                return;
            }
            setItems(data.items || []);
            setErrors(data.errors || []);
            if ((data.items || []).length === 0) {
                setBanner({ kind: "error", text: "No medicines matched. Check the spelling and try again." });
            }
        } catch {
            setBanner({ kind: "error", text: "Network error — is the backend running on :8000?" });
        } finally {
            setQuoting(false);
        }
    }

    const handleQtyChange = (i, qty) =>
        setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, quantity: qty } : it)));

    const handleRemove = (i) => setItems((prev) => prev.filter((_, idx) => idx !== i));

    // ── Print Bill: reviewed rows -> /confirm -> persist -> print ───────────
    async function handlePrintBill() {
        if (items.length === 0) return;
        setConfirming(true);
        setBanner(null);
        try {
            const confirmItems = items.map((it) => ({
                name: it.name,
                quantity: it.quantity,
                unit: it.unit,
                medicine_id: it.medicine_id,
                batch_id: it.batch_id,
                batch_number: it.batch_number,
                expiry_date: it.expiry_date,
            }));
            const { ok, data } = await confirmSale(confirmItems, customerName, customerPhone);
            if (!ok) {
                setBanner({ kind: "error", text: "Sale could not be finalized (stock may have changed). Try again." });
                return;
            }
            setConfirmedSale(data);
            setBanner({ kind: "success", text: `Invoice #${data.sale_id} saved — total ₹${Number(data.total_amount).toFixed(2)}.` });
            // Let the receipt render, then open the browser print dialog.
            setTimeout(() => window.print(), 150);
        } catch {
            setBanner({ kind: "error", text: "Network error during confirm." });
        } finally {
            setConfirming(false);
        }
    }

    function handleNewBill() {
        setItems([]);
        setErrors([]);
        setCustomerName("");
        setCustomerPhone("");
        setConfirmedSale(null);
        setBanner(null);
        setTranscript("");
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="no-print">
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                    <Icon name="point_of_sale" size={30} className="text-primary" />
                    New Bill
                </h1>
                <p className="text-sm text-muted-foreground mt-1">
                    Speak the order — medicines and prices fill in automatically. Review, then print.
                </p>
            </div>

            {/* Banner */}
            {banner && (
                <div
                    className={`no-print rounded-xl px-4 py-3 text-sm font-medium ${
                        banner.kind === "success"
                            ? "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/20 dark:text-emerald-300"
                            : "bg-rose-50 text-rose-700 border border-rose-200 dark:bg-rose-950/20 dark:text-rose-300"
                    }`}
                >
                    {banner.text}
                </div>
            )}

            {/* Voice + transcript */}
            <Card className="no-print">
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Icon name="mic" size={20} className="text-primary" />
                        Dictate the order
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    <VoiceButton supported={supported} listening={listening} onStart={start} onStop={stop} />
                    <Textarea
                        value={transcript}
                        onChange={(e) => setTranscript(e.target.value)}
                        placeholder={"e.g. 1 Paracetamol 500mg, 2 Crocin 500mg for Anurag 9876543210"}
                        className="min-h-24"
                    />
                    <div className="flex gap-3">
                        <Button onClick={handleGetPrices} disabled={!transcript.trim() || quoting}>
                            <Icon name="search" size={18} />
                            {quoting ? "Pricing…" : "Get Prices"}
                        </Button>
                        <Button variant="outline" onClick={handleNewBill}>
                            <Icon name="refresh" size={18} />
                            Clear
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Warnings */}
            <div className="no-print">
                <NotFoundWarnings errors={errors} />
            </div>

            {/* Bill table */}
            <div className="no-print">
                <BillTable items={items} onQtyChange={handleQtyChange} onRemove={handleRemove} />
            </div>

            {/* Customer (optional) + Print */}
            {items.length > 0 && (
                <Card className="no-print">
                    <CardContent className="space-y-4">
                        <div className="grid sm:grid-cols-2 gap-4">
                            <div className="space-y-1.5">
                                <Label htmlFor="cname">Customer name (optional)</Label>
                                <Input id="cname" value={customerName} onChange={(e) => setCustomerName(e.target.value)} placeholder="Anurag" />
                            </div>
                            <div className="space-y-1.5">
                                <Label htmlFor="cphone">Phone (optional)</Label>
                                <Input id="cphone" value={customerPhone} onChange={(e) => setCustomerPhone(e.target.value)} placeholder="9876543210" />
                            </div>
                        </div>
                        <div className="flex gap-3">
                            <Button size="lg" onClick={handlePrintBill} disabled={confirming}>
                                <Icon name="print" size={20} />
                                {confirming ? "Saving…" : "Print Bill"}
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

            {/* Print-only receipt (also re-printable) */}
            <Receipt sale={confirmedSale} />
        </div>
    );
}

NewBillPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default NewBillPage;
