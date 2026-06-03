import DashboardSidebar from "@/components/sidebar";

/**
 * DashboardLayout — the app shell: fixed 260px sidebar + flexible main content.
 * Same structure/classes as the reference, minus the NextAuth session guard
 * (auth arrives in Phase 5). Pages opt in via:
 *
 *   Page.getLayout = (page) => <DashboardLayout>{page}</DashboardLayout>;
 */
export default function DashboardLayout({ children }) {
    return (
        <div className="flex min-h-screen bg-[#f7faff] dark:bg-background">
            <DashboardSidebar />
            <main className="flex-1 lg:ml-[260px]">
                <div className="p-6 lg:p-8 max-w-350 mx-auto">
                    {children}
                </div>
            </main>
        </div>
    );
}
