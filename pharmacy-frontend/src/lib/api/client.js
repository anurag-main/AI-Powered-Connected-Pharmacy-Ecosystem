/**
 * Shared fetch plumbing for every API module in this folder.
 *
 * One rule: a call NEVER throws. Every path — network down, 422, 500, HTML error
 * page instead of JSON — comes back as the same shape:
 *
 *   { ok, status, data, requestId, error }
 *
 * `error` is null when ok, and otherwise a short message written for a pharmacist.
 * Backend exception text and SQL never reach it; the server's detail is useful for
 * debugging but is not something to put on a shop counter screen.
 */
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** Backend echoes this on every response; quoting it makes a bug report traceable. */
const REQUEST_ID_HEADER = "X-Request-ID";

export const ERROR_MESSAGES = {
    network: "Cannot reach the server. Check that the backend is running.",
    validation: "That request was not valid. Try different filters.",
    server: "The server could not complete this request.",
    unexpected: "Something went wrong. Try again.",
};

function classify(status) {
    if (status === 0) return "network";
    if (status === 422 || status === 400) return "validation";
    if (status >= 500) return "server";
    return "unexpected";
}

async function request(path, options) {
    let res;
    try {
        res = await fetch(`${BASE}${path}`, options);
    } catch {
        // fetch only rejects for network-level failures — DNS, refused, offline.
        return {
            ok: false,
            status: 0,
            data: {},
            requestId: null,
            error: ERROR_MESSAGES.network,
        };
    }

    // A gateway or proxy can answer with HTML, so a parse failure is not a crash.
    const data = await res.json().catch(() => ({}));
    const requestId = res.headers.get(REQUEST_ID_HEADER);

    return {
        ok: res.ok,
        status: res.status,
        data,
        requestId,
        error: res.ok ? null : ERROR_MESSAGES[classify(res.status)],
    };
}

export function getJSON(path) {
    return request(path, { method: "GET" });
}

export function postJSON(path, body) {
    return request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
}

export { BASE };
