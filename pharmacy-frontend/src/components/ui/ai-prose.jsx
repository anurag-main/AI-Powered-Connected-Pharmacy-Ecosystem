/**
 * Renders an LLM's prose field as readable text.
 *
 * WHY THIS EXISTS
 * ---------------
 * The backend's `answer` is a plain string. The model, left to itself, writes
 * markdown into it — `**Amlodipine 5mg**` — and a plain `<p>{answer}</p>` puts the
 * asterisks on screen. That was visible on /inventory against the real provider.
 *
 * The fix could have been a line in the prompt telling it not to. That is a request,
 * not a guarantee: the next model, or the next temperature, will do it again. The
 * view has to cope with whatever arrives, so it copes here.
 *
 * Deliberately NOT a markdown library. Two rules, no dependency, and no
 * `dangerouslySetInnerHTML` — this string came from a language model, and the one
 * thing it must never be able to do is inject markup.
 *
 *   **bold**        ->  <strong>
 *   " 1. " " 2. "   ->  a line break, so an inline list reads as a list
 *
 * Text with neither marker comes back as the original string, unsplit, so a caller
 * asserting on the whole sentence still finds one text node.
 */

/** Split on **bold** runs. Returns the plain string when there are none. */
function withBold(text, keyPrefix) {
    const parts = text.split(/(\*\*[^*]+\*\*)/g);
    if (parts.length === 1) return text;

    return parts.map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
            <strong key={`${keyPrefix}-b${i}`} className="font-semibold">
                {part.slice(2, -2)}
            </strong>
        ) : (
            part
        )
    );
}

/**
 * Break an inline "1. … 2. …" list onto separate lines.
 *
 * One or two digits only. Four would match a year — "sold in 2024. 5 units" — and
 * chop a sentence in half.
 */
function toLines(text) {
    return text
        .replace(/\s(\d{1,2}\.\s)/g, "\n$1")
        .split(/\n+/)
        .map((line) => line.trim())
        .filter(Boolean);
}

export default function AiProse({ text, className = "" }) {
    if (!text) return null;

    const lines = toLines(text);

    if (lines.length === 1) {
        return (
            <p className={`text-sm leading-relaxed ${className}`}>
                {withBold(lines[0], "l0")}
            </p>
        );
    }

    return (
        <div className={`space-y-1.5 text-sm leading-relaxed ${className}`}>
            {lines.map((line, i) => (
                <p key={`l${i}`}>{withBold(line, `l${i}`)}</p>
            ))}
        </div>
    );
}
