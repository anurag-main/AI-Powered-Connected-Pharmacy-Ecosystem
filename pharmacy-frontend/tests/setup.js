import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

/**
 * Global test setup.
 *
 * `fetch` is stubbed for every test and never restored to the real one. That is the
 * safety rule for this suite: a test must not be able to reach the FastAPI server,
 * MySQL, or OpenAI even by accident. A test that forgets to script a response gets
 * an explicit failure rather than a silent live call.
 */
beforeEach(() => {
    vi.stubGlobal(
        "fetch",
        vi.fn(() => {
            throw new Error(
                "Unmocked fetch. Script it with mockFetchOnce() from tests/helpers.js."
            );
        })
    );
});

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
});

// jsdom implements neither, and the dashboard components use both.
window.matchMedia ??= (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
});

window.scrollTo ??= () => {};
