/**
 * Sales history API. Read-only — an invoice is an audit record.
 *
 * The list is paged and carries a `total`, so the page can say "25 of 536" and
 * decide whether a Load more button belongs on screen. Line items are NOT in the
 * list response; they arrive per invoice when a row is opened, because loading
 * every line for every sale would fetch thousands of rows to draw a hundred.
 */
import { getJSON } from "./client";

export const SALES_PAGE_SIZE = 25;

/** One page of invoices, newest first. */
export function listSales({ limit = SALES_PAGE_SIZE, offset = 0 } = {}) {
    return getJSON(`/api/v1/sales?limit=${limit}&offset=${offset}`);
}

/** One invoice with its lines, priced as it was charged. 404 if it does not exist. */
export function getSale(saleId) {
    return getJSON(`/api/v1/sales/${saleId}`);
}
