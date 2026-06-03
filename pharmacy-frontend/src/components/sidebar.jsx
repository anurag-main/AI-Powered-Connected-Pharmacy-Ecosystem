import React, { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/router";
import { motion, AnimatePresence } from "framer-motion";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import Icon from "@/components/ui/icon";
import Logo from "@/components/Logo";

// ─── Navigation map ─────────────────────────────────────────────────────────
// Single source of truth for sidebar entries. Icons are Material Symbols
// Outlined names — see https://fonts.google.com/icons for the full set.
const navSections = [
    {
        label: "Workspace",
        items: [
            { href: "/", label: "New Bill", icon: "point_of_sale" },
            { href: "/medicines", label: "Medicines", icon: "medication" },
        ],
    },
    {
        label: "Operations",
        items: [
            { href: "/sales", label: "Sales History", icon: "receipt_long" },
        ],
    },
];

export default function DashboardSidebar() {
    const router = useRouter();
    const pathname = router.pathname;
    const [mobileOpen, setMobileOpen] = useState(false);

    // ── A single nav row (active state = left accent bar + bold + indigo) ───
    const NavRow = ({ item }) => {
        const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href));

        return (
            <Link href={item.href} onClick={() => setMobileOpen(false)} className="block">
                <div className="relative group">
                    {/* Active accent bar */}
                    {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-7 rounded-r-full bg-primary" />
                    )}
                    <div
                        className={`flex items-center gap-3 mx-3 px-3 py-2.5 rounded-lg transition-colors duration-150 ${
                            isActive
                                ? "text-primary"
                                : "text-muted-foreground hover:text-foreground hover:bg-muted/60"
                        }`}
                    >
                        <Icon
                            name={item.icon}
                            filled={isActive}
                            size={22}
                            className={`shrink-0 ${isActive ? "text-primary" : "text-muted-foreground/80 group-hover:text-foreground"}`}
                        />
                        <span className={`flex-1 text-sm tracking-tight truncate ${isActive ? "font-semibold" : "font-medium"}`}>
                            {item.label}
                        </span>
                    </div>
                </div>
            </Link>
        );
    };

    // ── Sidebar body (shared between desktop + mobile) ──────────────────────
    const SidebarContent = () => (
        <div className="flex flex-col h-full bg-white dark:bg-card">
            {/* Brand */}
            <div className="px-6 pt-7 pb-5">
                <Logo size={36} withWordmark />
            </div>
            <div className="mx-6 border-t border-border/60" />

            {/* Navigation — grouped sections */}
            <nav className="flex-1 overflow-y-auto py-5 space-y-6">
                {navSections.map((section) => (
                    <div key={section.label}>
                        <p className="px-6 pb-2 text-[10px] uppercase tracking-[0.12em] font-semibold text-muted-foreground/60">
                            {section.label}
                        </p>
                        <div className="space-y-0.5">
                            {section.items.map((item) => (
                                <NavRow key={item.href} item={item} />
                            ))}
                        </div>
                    </div>
                ))}
            </nav>

            {/* Profile (static placeholder — real auth lands in Phase 5) */}
            <div className="border-t border-border/60 p-3 flex items-center gap-3">
                <Avatar className="w-9 h-9 shrink-0">
                    <AvatarFallback className="bg-primary/10 text-primary text-xs font-semibold">PO</AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate leading-tight">Pharmacy Owner</p>
                    <p className="text-xs text-muted-foreground capitalize leading-tight mt-0.5">owner</p>
                </div>
                <button
                    title="Sign out (Phase 5)"
                    className="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-rose-600 hover:bg-rose-500/10 transition-colors"
                >
                    <Icon name="logout" size={20} />
                </button>
            </div>
        </div>
    );

    return (
        <>
            {/* Mobile toggle */}
            <Button
                variant="ghost"
                size="icon"
                className="fixed top-4 left-4 z-50 lg:hidden"
                onClick={() => setMobileOpen(!mobileOpen)}
                aria-label="Toggle navigation"
            >
                <Icon name={mobileOpen ? "close" : "menu"} size={22} />
            </Button>

            {/* Mobile overlay */}
            <AnimatePresence>
                {mobileOpen && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-black/40 z-40 lg:hidden backdrop-blur-sm"
                        onClick={() => setMobileOpen(false)}
                    />
                )}
            </AnimatePresence>

            {/* Mobile sidebar */}
            <AnimatePresence>
                {mobileOpen && (
                    <motion.aside
                        initial={{ x: -280 }}
                        animate={{ x: 0 }}
                        exit={{ x: -280 }}
                        transition={{ type: "spring", damping: 25, stiffness: 300 }}
                        className="fixed left-0 top-0 bottom-0 w-[260px] z-50 lg:hidden overflow-hidden"
                    >
                        <SidebarContent />
                    </motion.aside>
                )}
            </AnimatePresence>

            {/* Desktop sidebar — fixed 260px */}
            <aside className="hidden lg:flex flex-col fixed left-0 top-0 bottom-0 w-[260px] bg-white dark:bg-card z-30">
                <SidebarContent />
            </aside>
        </>
    );
}
