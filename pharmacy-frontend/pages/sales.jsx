import DashboardLayout from "@/components/DashboardLayout";
import { Card } from "@/components/ui/card";
import Icon from "@/components/ui/icon";

function SalesPage() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight flex items-center gap-3">
                    <Icon name="receipt_long" size={30} className="text-primary" />
                    Sales History
                </h1>
                <p className="text-sm text-muted-foreground mt-1">Past invoices will appear here.</p>
            </div>
            <Card className="items-center justify-center py-20 text-muted-foreground">
                <Icon name="construction" size={40} className="text-muted-foreground/40" />
                <p className="text-sm mt-2">Coming soon — a future step will list saved sales.</p>
            </Card>
        </div>
    );
}

SalesPage.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;

export default SalesPage;
