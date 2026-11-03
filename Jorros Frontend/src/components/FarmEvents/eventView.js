export const EVENT_KINDS = ["Farm Event", "Planned No-Work Day", "Emergency Suspension"];
export function eventLocalTime(value, timezone = "Asia/Manila") {
    if (!value) return "";
    if (!/Z$|[+-]\d\d:\d\d$/.test(value)) return String(value).slice(0, 16);
    const parts = new Intl.DateTimeFormat("en-CA", { timeZone: timezone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(value));
    const p = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export function eventTouchesDate(event, dateKey, timezone = "Asia/Manila") {
    const start = eventLocalTime(event.starts_at, timezone);
    const stop = eventLocalTime(event.ended_at || event.ends_at, timezone);
    if (!start || !dateKey || dateKey < start.slice(0, 10)) return false;
    if (event.requires_reopening && !event.ended_at) return true;
    return stop > `${dateKey}T00:00`;
}
export function eventCreatePath({ kind = "Farm Event", date = "", source = "", reason = "", title = "", reference = "" } = {}) {
    const query = new URLSearchParams({ eventAction: "create", kind });
    if (date) query.set("date", date);
    if (source) query.set("source", source.slice(0, 150));
    if (reason) query.set("reason", reason.slice(0, 2000));
    if (title) query.set("title", title.slice(0, 150));
    if (reference) query.set("reference", reference.slice(0, 600));
    return `/staff-calendar?${query.toString()}`;
}
export function eventForm(event = {}, date, timezone) {
    return { title: event.title || "", kind: EVENT_KINDS.includes(event.kind) ? event.kind : "Farm Event",
        starts_at: eventLocalTime(event.starts_at, timezone) || `${date}T08:00`, ends_at: eventLocalTime(event.ends_at, timezone) || `${date}T17:00`,
        scope_type: event.scope_type || "All", scope_values: (event.scope_values || []).map(String),
        reason: event.reason || "", instructions: event.instructions || "", source_name: event.source_name || "", source_reference: event.source_reference || "" };
}
