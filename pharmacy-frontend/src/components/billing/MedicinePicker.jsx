import { useEffect, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import Icon from "@/components/ui/icon";

const MAX_RESULTS = 8;

/**
 * Searchable medicine selector — the thing that replaced the microphone.
 *
 * Type a few letters, arrow down, Enter. Designed for a counter: the keyboard
 * alone is enough, because a pharmacist billing a queue should not have to reach
 * for the mouse.
 *
 * Matching is a plain case-insensitive substring over name and manufacturer.
 * Fuzzy matching is what made the voice flow need a "did you mean?" step, and a
 * typed search does not have that problem — the user can see what they typed.
 */
export default function MedicinePicker({ medicines, loading, value, onSelect, disabled }) {
    const [query, setQuery] = useState("");
    const [open, setOpen] = useState(false);
    const [active, setActive] = useState(0);
    const boxRef = useRef(null);

    const results = useMemo(() => {
        const q = query.trim().toLowerCase();
        if (!q) return [];
        return medicines
            .filter(
                (m) =>
                    m.name.toLowerCase().includes(q) ||
                    (m.manufacturer || "").toLowerCase().includes(q)
            )
            .slice(0, MAX_RESULTS);
    }, [medicines, query]);

    // Reset the highlight whenever the result set changes, or Enter could pick a
    // row the user never saw.
    useEffect(() => setActive(0), [query]);

    // Click-away closes the list.
    useEffect(() => {
        function onDocClick(event) {
            if (boxRef.current && !boxRef.current.contains(event.target)) setOpen(false);
        }
        document.addEventListener("mousedown", onDocClick);
        return () => document.removeEventListener("mousedown", onDocClick);
    }, []);

    function choose(medicine) {
        onSelect(medicine);
        setQuery("");
        setOpen(false);
    }

    function onKeyDown(event) {
        if (!open || results.length === 0) return;

        if (event.key === "ArrowDown") {
            event.preventDefault();
            setActive((i) => (i + 1) % results.length);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            setActive((i) => (i - 1 + results.length) % results.length);
        } else if (event.key === "Enter") {
            event.preventDefault();
            choose(results[active]);
        } else if (event.key === "Escape") {
            setOpen(false);
        }
    }

    return (
        <div ref={boxRef} className="relative">
            {/* The chosen medicine, shown instead of the search box until cleared. */}
            {value ? (
                <div className="flex h-9 items-center gap-2 rounded-lg border border-input bg-background px-3">
                    <Icon name="medication" size={16} className="shrink-0 text-primary" />
                    <span className="flex-1 truncate text-sm font-medium">{value.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                        ₹{Number(value.mrp).toFixed(2)}
                    </span>
                    <button
                        type="button"
                        onClick={() => onSelect(null)}
                        aria-label="Clear selected medicine"
                        className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
                    >
                        <Icon name="close" size={16} />
                    </button>
                </div>
            ) : (
                <div className="relative">
                    <Icon
                        name="search"
                        size={16}
                        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                    />
                    <Input
                        value={query}
                        disabled={disabled || loading}
                        onChange={(e) => {
                            setQuery(e.target.value);
                            setOpen(true);
                        }}
                        onFocus={() => setOpen(true)}
                        onKeyDown={onKeyDown}
                        placeholder={loading ? "Loading medicines…" : "Search medicine…"}
                        className="h-9 pl-9"
                        role="combobox"
                        aria-expanded={open}
                        aria-controls="medicine-results"
                        aria-autocomplete="list"
                    />
                </div>
            )}

            {open && !value && query.trim() && (
                <ul
                    id="medicine-results"
                    role="listbox"
                    className="absolute z-20 mt-1 max-h-72 w-full overflow-y-auto rounded-lg border border-border bg-popover p-1 shadow-lg"
                >
                    {results.length === 0 ? (
                        <li className="px-3 py-2 text-sm text-muted-foreground">
                            Nothing matches “{query}”.
                        </li>
                    ) : (
                        results.map((medicine, i) => (
                            <li key={medicine.id} role="option" aria-selected={i === active}>
                                <button
                                    type="button"
                                    onMouseEnter={() => setActive(i)}
                                    onClick={() => choose(medicine)}
                                    className={`flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors ${
                                        i === active ? "bg-accent text-accent-foreground" : ""
                                    }`}
                                >
                                    <div className="min-w-0 flex-1">
                                        <p className="truncate text-sm font-medium">
                                            {medicine.name}
                                        </p>
                                        {medicine.manufacturer && (
                                            <p className="truncate text-xs text-muted-foreground">
                                                {medicine.manufacturer}
                                            </p>
                                        )}
                                    </div>
                                    <span className="shrink-0 text-sm tabular-nums text-muted-foreground">
                                        ₹{Number(medicine.mrp).toFixed(2)}
                                    </span>
                                </button>
                            </li>
                        ))
                    )}
                </ul>
            )}
        </div>
    );
}
