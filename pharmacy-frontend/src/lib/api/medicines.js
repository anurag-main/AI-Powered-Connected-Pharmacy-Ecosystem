/**
 * Medicine catalogue writes.
 *
 * WHY THIS IS A SEPARATE FILE FROM `lib/api/index.js`
 * ---------------------------------------------------
 * `listMedicines` already lives in index.js and is imported all over the app.
 * Moving it here would touch every one of those call sites for no gain, and
 * `export *`-ing this file from index.js would risk the ambiguous re-export
 * trap that expiry.js and inventory.js already hit — a duplicated name is
 * SILENTLY DROPPED rather than erroring.
 *
 * So this file holds only the write, and is imported by path:
 *
 *   import { createMedicine } from "@/lib/api/medicines";
 *
 * ERROR HANDLING
 * --------------
 * Same bounded deviation as purchases.js: a 409 from this endpoint means "a
 * medicine with this name already exists", which is specific, actionable, and
 * authored by us in medicine_service.py. The shared client would have replaced
 * it with "Something went wrong", which tells the pharmacist nothing about the
 * duplicate they just tried to create.
 *
 * A 500's detail is still suppressed — that is the text that leaks internals.
 */
import { postJSON, ERROR_MESSAGES } from "./client";

/** Field rules mirrored from app/schemas/medicine.py — used for input hints only. */
export const HSN_LENGTH = 8;

function createError(result) {
    const detail = result?.data?.detail;

    // 409 is the interesting one: a duplicate normalized name.
    if (result.status === 409 && typeof detail === "string" && detail) {
        return detail;
    }

    // 422 detail from Pydantic is an ARRAY of field objects. Rendering it would
    // print [object Object], so it is summarised rather than shown.
    if (result.status === 422) {
        return firstFieldMessage(detail) || ERROR_MESSAGES.validation;
    }

    return result.error || ERROR_MESSAGES.unexpected;
}

/**
 * Turn Pydantic's first field error into one readable sentence.
 *
 * Only the FIRST is used on purpose. Listing five field errors at once reads
 * like a stack trace; the form has inline hints for the rules, so the banner
 * only needs to say which field to look at.
 */
function firstFieldMessage(detail) {
    if (!Array.isArray(detail) || detail.length === 0) return null;
    const first = detail[0];
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : null;
    if (!field || !first?.msg) return null;
    return `${String(field).replace(/_/g, " ")}: ${first.msg}`;
}

/**
 * Create a catalogue entry.
 *
 * Note what this does NOT create: stock. A medicine with no batch has zero
 * quantity and will not appear in any inventory or expiry report. Units arrive
 * through the goods receipt screen at /receive.
 */
export async function createMedicine({ name, mrp, hsnCode, manufacturer }) {
    const body = {
        name: name.trim(),
        // An <input> yields a string; "30.00" would fail the backend's numeric
        // validation with a 422 that reads like a mystery rather than a typo.
        mrp: Number(mrp),
        hsn_code: hsnCode.trim(),
    };

    // Optional field: omitted rather than sent as "", which is a different thing
    // to the server than "not provided".
    const cleanedManufacturer = (manufacturer || "").trim();
    if (cleanedManufacturer) body.manufacturer = cleanedManufacturer;

    const result = await postJSON("/api/v1/medicines", body);
    return result.ok ? result : { ...result, error: createError(result) };
}

/**
 * Is the form complete enough to send?
 *
 * Presence and shape only — the things a browser can check without duplicating
 * a business rule. Whether the name is a duplicate is a database question and
 * is deliberately left to the server.
 */
export function isMedicineFormComplete({ name, mrp, hsnCode }) {
    return Boolean(
        name &&
            name.trim() &&
            mrp !== "" &&
            Number(mrp) > 0 &&
            hsnCode &&
            hsnCode.trim().length === HSN_LENGTH,
    );
}

/**
 * A blank form. Exported so the page and its tests agree on the shape.
 *
 * `hsnCode` is deliberately EMPTY rather than pre-filled with 30049099, even
 * though that is the most common value in the catalogue. It is a GST tax code:
 * a default that is right most of the time is wrong some of the time, silently,
 * and the wrongness surfaces at filing rather than at entry. The form shows the
 * common value as a hint instead, so it is a choice rather than an assumption.
 */
export function emptyMedicineForm() {
    return { name: "", mrp: "", hsnCode: "", manufacturer: "" };
}
