// Missing estimates are unknown, not zero. Keep analytics rendering resilient to null API fields.
export function asFiniteAnalyticsNumber(value) {
    if (value === null || value === undefined || typeof value === "boolean" ||
        (typeof value === "string" && value.trim() === "")) return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

export function formatAnalyticsDecimal(value, digits = 1, suffix = "", fallback = "No data") {
    const number = asFiniteAnalyticsNumber(value);
    return number === null ? fallback : `${number.toFixed(digits)}${suffix}`;
}

export function formatAnalyticsQuantity(value, suffix = "", fallback = "No data", maximumFractionDigits = 0) {
    const number = asFiniteAnalyticsNumber(value);
    return number === null ? fallback : `${number.toLocaleString("en-US", { maximumFractionDigits })}${suffix}`;
}
