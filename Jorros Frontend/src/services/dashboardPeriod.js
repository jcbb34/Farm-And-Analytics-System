const ALLOWED_PERIODS = new Set([
    "today",
    "week",
    "month",
    "last30",
    "year",
    "custom",
]);

/** @param {number} value */
function pad(value) {
    return String(value).padStart(2, "0");
}

/** @param {Date | string | number} value */
export function formatDashboardDateKey(value) {
    const date = value instanceof Date ? value : new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "";
    }

    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
        date.getDate()
    )}`;
}

/** @param {string} value */
export function normalizeDashboardPeriod(value) {
    return ALLOWED_PERIODS.has(value) ? value : "month";
}

/** @param {string} dateKey */
function formatFriendlyDate(dateKey) {
    if (!dateKey) return "";

    const date = new Date(`${dateKey}T00:00:00`);
    if (Number.isNaN(date.getTime())) return dateKey;

    return date.toLocaleDateString("en-PH", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

/** @param {string} period @param {{startDate?: string, endDate?: string}} customRange @param {Date} now */
export function getDashboardPeriodRange(
    period,
    customRange = {},
    now = new Date()
) {
    const selectedPeriod = normalizeDashboardPeriod(period);
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    let start = new Date(today);
    let end = new Date(today);
    let label = "Today";

    if (selectedPeriod === "week") {
        const day = start.getDay();
        const mondayOffset = day === 0 ? 6 : day - 1;
        start.setDate(start.getDate() - mondayOffset);
        end = new Date(start);
        end.setDate(end.getDate() + 6);
        label = "This Week";
    } else if (selectedPeriod === "month") {
        start = new Date(today.getFullYear(), today.getMonth(), 1);
        end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
        label = "This Month";
    } else if (selectedPeriod === "last30") {
        start.setDate(start.getDate() - 29);
        label = "Last 30 Days";
    } else if (selectedPeriod === "year") {
        start = new Date(today.getFullYear(), 0, 1);
        end = new Date(today.getFullYear(), 11, 31);
        label = "This Year";
    } else if (selectedPeriod === "custom") {
        const customStart = String(customRange?.startDate || "").slice(0, 10);
        const customEnd = String(customRange?.endDate || "").slice(0, 10);

        if (customStart && customEnd) {
            const first = customStart <= customEnd ? customStart : customEnd;
            const last = customStart <= customEnd ? customEnd : customStart;

            return {
                period: selectedPeriod,
                startDate: first,
                endDate: last,
                label: `${formatFriendlyDate(first)} – ${formatFriendlyDate(last)}`,
                shortLabel: "Custom Range",
            };
        }

        label = "Custom Range";
    }

    return {
        period: selectedPeriod,
        startDate: formatDashboardDateKey(start),
        endDate: formatDashboardDateKey(end),
        label,
        shortLabel: label,
    };
}

/** @param {string} value @param {{startDate: string, endDate: string}} range */
export function isDateInDashboardRange(value, range) {
    if (!range?.startDate || !range?.endDate) {
        return true;
    }

    const key = String(value || "").slice(0, 10);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key)) {
        return false;
    }

    return key >= range.startDate && key <= range.endDate;
}

/** @param {{startDate?: string, endDate?: string}} range */
export function countDashboardRangeDays(range) {
    if (!range?.startDate || !range?.endDate) return 1;

    const start = new Date(`${range.startDate}T00:00:00`);
    const end = new Date(`${range.endDate}T00:00:00`);

    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) {
        return 1;
    }

    return Math.max(1, Math.round((end.getTime() - start.getTime()) / 86400000) + 1);
}
