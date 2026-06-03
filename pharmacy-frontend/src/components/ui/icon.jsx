/**
 * Icon — wrapper around Google Material Symbols Outlined.
 * Loaded via the Google Fonts <link> in _app.jsx; the .material-symbols-outlined
 * base class lives in globals.css.
 *
 * Usage:
 *   <Icon name="dashboard" />                       — 22px outlined
 *   <Icon name="check_circle" filled />             — filled variant
 *   <Icon name="logout" size={20} className="..." />
 */
export default function Icon({ name, filled = false, size, className = "", style, ...rest }) {
    const inlineStyle = size != null ? { ...style, fontSize: typeof size === "number" ? `${size}px` : size } : style;
    return (
        <span
            className={`material-symbols-outlined${filled ? " filled" : ""} ${className}`.trim()}
            style={inlineStyle}
            aria-hidden="true"
            {...rest}
        >
            {name}
        </span>
    );
}
