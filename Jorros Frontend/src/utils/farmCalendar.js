export const DEFAULT_FARM_TIMEZONE = "Asia/Manila";

const pad2 = (value) => String(value).padStart(2, "0");

export function parseDateKey(key) {
    const [year, month, day] = String(key || "").split("-").map(Number);
    if (!year || !month || !day) return null;
    return { year, month, day };
}

export function farmDateKey(value = new Date(), timeZone = DEFAULT_FARM_TIMEZONE) {
    const date = value instanceof Date ? value : new Date(value);
    const parts = new Intl.DateTimeFormat("en-US", {
        timeZone,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(date);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
}

export function localCalendarDateKey(value = new Date()) {
    const date = value instanceof Date ? value : new Date(value);
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

export function addCalendarDays(key, amount) {
    const parsed = parseDateKey(key);
    if (!parsed) return key;
    const date = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day + Number(amount || 0), 12));
    return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
}

export function addCalendarMonths(key, amount) {
    const parsed = parseDateKey(key);
    if (!parsed) return key;
    const first = new Date(Date.UTC(parsed.year, parsed.month - 1 + Number(amount || 0), 1, 12));
    const year = first.getUTCFullYear();
    const monthIndex = first.getUTCMonth();
    const maxDay = new Date(Date.UTC(year, monthIndex + 1, 0, 12)).getUTCDate();
    const day = Math.min(parsed.day, maxDay);
    return `${year}-${pad2(monthIndex + 1)}-${pad2(day)}`;
}

export function startOfWeekKey(key) {
    const parsed = parseDateKey(key);
    if (!parsed) return key;
    const date = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day, 12));
    const weekday = date.getUTCDay();
    return addCalendarDays(key, -(weekday === 0 ? 6 : weekday - 1));
}

export function monthRange(key) {
    const parsed = parseDateKey(key);
    if (!parsed) return [key, key];
    const start = `${parsed.year}-${pad2(parsed.month)}-01`;
    const nextMonth = addCalendarMonths(start, 1);
    return [start, addCalendarDays(nextMonth, -1)];
}

export function calendarRange(key, mode) {
    if (mode === "day") return [key, key];
    if (mode === "week") {
        const start = startOfWeekKey(key);
        return [start, addCalendarDays(start, 6)];
    }
    return monthRange(key);
}

export function moveCalendarAnchor(key, mode, direction) {
    if (mode === "day") return addCalendarDays(key, direction);
    if (mode === "week") return addCalendarDays(key, direction * 7);
    return addCalendarMonths(key, direction);
}

export function dateKeysBetween(startKey, endKey) {
    const result = [];
    let cursor = startKey;
    let guard = 0;
    while (cursor <= endKey && guard < 370) {
        result.push(cursor);
        cursor = addCalendarDays(cursor, 1);
        guard += 1;
    }
    return result;
}

export function formatDateKey(key, options = {}) {
    const parsed = parseDateKey(key);
    if (!parsed) return String(key || "");
    const date = new Date(Date.UTC(parsed.year, parsed.month - 1, parsed.day, 12));
    return new Intl.DateTimeFormat("en-PH", { timeZone: "UTC", ...options }).format(date);
}
