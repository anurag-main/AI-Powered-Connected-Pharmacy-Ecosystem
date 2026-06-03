/**
 * Receipt — the print layout. Hidden on screen except its success summary; when
 * window.print() runs, the @media print rules in globals.css show ONLY the
 * #print-receipt element. Props: sale (the confirmed BillingResponse).
 */
const rupee = (n) => `₹${Number(n).toFixed(2)}`;

export default function Receipt({ sale }) {
    if (!sale) return null;
    const now = new Date();

    return (
        <div id="print-receipt" className="bg-white text-black mx-auto max-w-md p-6">
            <div className="text-center border-b border-dashed border-gray-400 pb-3 mb-3">
                <h2 className="text-xl font-bold">PharmaBill</h2>
                <p className="text-xs text-gray-600">Voice Billing — Tax Invoice</p>
            </div>

            <div className="text-xs text-gray-700 mb-3 space-y-0.5">
                <div>Invoice #: <span className="font-semibold">{sale.sale_id}</span></div>
                <div>Date: {now.toLocaleString()}</div>
                {sale.customer_name && <div>Customer: {sale.customer_name}</div>}
                {sale.customer_phone && <div>Phone: {sale.customer_phone}</div>}
            </div>

            <table className="w-full text-xs mb-3">
                <thead>
                    <tr className="border-b border-gray-400">
                        <th className="text-left py-1">Item</th>
                        <th className="text-center py-1">Qty</th>
                        <th className="text-right py-1">Rate</th>
                        <th className="text-right py-1">Amount</th>
                    </tr>
                </thead>
                <tbody>
                    {sale.items.map((it, i) => (
                        <tr key={i} className="border-b border-dashed border-gray-300">
                            <td className="py-1">{it.name}</td>
                            <td className="text-center py-1">{it.quantity}</td>
                            <td className="text-right py-1">{rupee(it.unit_price)}</td>
                            <td className="text-right py-1">{rupee(it.line_total)}</td>
                        </tr>
                    ))}
                </tbody>
            </table>

            <div className="flex justify-between border-t-2 border-gray-500 pt-2 font-bold">
                <span>TOTAL</span>
                <span>{rupee(sale.total_amount)}</span>
            </div>

            <p className="text-center text-[10px] text-gray-500 mt-4">
                Thank you. Get well soon!
            </p>
        </div>
    );
}
