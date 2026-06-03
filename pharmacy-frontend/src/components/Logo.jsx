/**
 * Logo — pharmacy brand mark (same visual treatment as the reference shell).
 *
 * Composition:
 *   - Rounded square tile with indigo→violet gradient (brand primary)
 *   - White medical cross (+) in the centre
 *   - Green check badge in the lower-right corner ("verified / billed")
 *
 * Optional wordmark renders "PharmaBill" beside the tile.
 * Pure SVG — sharp at any size, no font dependency.
 */
export default function Logo({
    size = 40,
    withWordmark = false,
    wordmarkClassName = "text-foreground",
    className = "",
}) {
    const tileSize = size * 0.7;
    return (
        <span className={`inline-flex items-center gap-3 ${className}`}>
            <svg
                width={tileSize}
                height={tileSize}
                viewBox="0 0 40 40"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                aria-label="PharmaBill"
            >
                <defs>
                    <linearGradient id="ph-logo-bg" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
                        <stop offset="0%" stopColor="#6366F1" />
                        <stop offset="100%" stopColor="#7C3AED" />
                    </linearGradient>
                </defs>
                {/* Tile */}
                <rect width="40" height="40" rx="11" fill="url(#ph-logo-bg)" />
                {/* Medical cross (vertical + horizontal bars) */}
                <rect x="17" y="9.5" width="6" height="21" rx="2" fill="#FFFFFF" fillOpacity="0.96" />
                <rect x="9.5" y="17" width="21" height="6" rx="2" fill="#FFFFFF" fillOpacity="0.96" />
                {/* Check badge */}
                <circle cx="29" cy="29" r="6" fill="#FFFFFF" />
                <circle cx="29" cy="29" r="5" fill="#10B981" />
                <path
                    d="m26.4 29.2 1.9 1.9 3.4-3.7"
                    stroke="#FFFFFF"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    fill="none"
                />
            </svg>
            {withWordmark && (
                <span className="inline-flex flex-col items-start leading-tight">
                    <span
                        className={`font-semibold tracking-tight ${wordmarkClassName}`}
                        style={{ fontSize: size * 0.40 }}
                    >
                        Pharma
                        <span className="bg-linear-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
                            Bill
                        </span>
                    </span>
                    <span className="text-muted-foreground" style={{ fontSize: size * 0.26 }}>
                        Voice Billing
                    </span>
                </span>
            )}
        </span>
    );
}
