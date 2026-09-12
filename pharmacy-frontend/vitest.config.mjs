import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/**
 * Vitest config for the frontend.
 *
 * Deliberately small. Next.js is not involved in the tests: pages are imported and
 * rendered as plain React components, which works because every page here keeps its
 * layout in a `getLayout` static rather than wrapping itself. That keeps the tests
 * fast and free of the router and the font loader.
 *
 * The `@` alias mirrors jsconfig.json so component imports resolve identically to
 * the way `next build` resolves them.
 */
export default defineConfig({
    plugins: [react()],
    resolve: {
        alias: {
            "@": path.resolve(import.meta.dirname, "./src"),
        },
    },
    test: {
        environment: "jsdom",
        globals: true,
        setupFiles: ["./tests/setup.js"],
        include: ["tests/**/*.test.{js,jsx}"],
        // next build output and deps are not ours to test.
        exclude: ["node_modules", ".next"],
    },
});
