export const WEEK_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

export const makeWeeklySchedule = (effectiveFrom = "") => ({
    effective_from: effectiveFrom,
    effective_to: null,
    timezone: "Asia/Manila",
    schedule_type: "Fixed",
    backup_employee_id: null,
    days: WEEK_DAYS.map((_, day_of_week) => ({
        day_of_week,
        state: day_of_week === 6 ? "Rest Day" : "Working Day",
        start_time: day_of_week === 6 ? null : "08:00",
        end_time: day_of_week === 6 ? null : "17:00",
        break_start_time: day_of_week === 6 ? null : "12:00",
        break_end_time: day_of_week === 6 ? null : "13:00",
    })),
});

export const normalizeWeeklySchedule = (schedule, effectiveFrom = "") => {
    if (!schedule) return makeWeeklySchedule(effectiveFrom);
    const byDay = new Map((schedule.days || []).map((day) => [Number(day.day_of_week), day]));
    return {
        effective_from: schedule.effective_from || effectiveFrom,
        effective_to: schedule.effective_to || null,
        timezone: schedule.timezone || "Asia/Manila",
        schedule_type: schedule.schedule_type || "Fixed",
        backup_employee_id: schedule.backup_employee_id ? String(schedule.backup_employee_id) : "",
        days: WEEK_DAYS.map((_, day_of_week) => {
            const day = byDay.get(day_of_week);
            const working = day ? Boolean(day.is_working_day ?? day.state === "Working Day") : day_of_week !== 6;
            return {
                day_of_week,
                state: working ? "Working Day" : "Rest Day",
                start_time: working ? String(day?.start_time || "08:00").slice(0, 5) : null,
                end_time: working ? String(day?.end_time || "17:00").slice(0, 5) : null,
                break_start_time: working && day?.break_start_time ? String(day.break_start_time).slice(0, 5) : working ? "12:00" : null,
                break_end_time: working && day?.break_end_time ? String(day.break_end_time).slice(0, 5) : working ? "13:00" : null,
            };
        }),
    };
};

export const validateWeeklySchedule = (schedule) => {
    if (!schedule?.effective_from) return "Schedule effective-start date is required.";
    if (!Array.isArray(schedule.days) || schedule.days.length !== 7) return "Configure all seven days of the week.";
    if (new Set(schedule.days.map((day) => Number(day.day_of_week))).size !== 7) return "Each weekday must be configured exactly once.";
    const working = schedule.days.filter((day) => day.state === "Working Day");
    const resting = schedule.days.filter((day) => day.state === "Rest Day");
    if (!working.length) return "At least one Working Day is required.";
    if (schedule.schedule_type === "Fixed" && !resting.length) return "A fixed schedule requires at least one Rest Day.";
    for (const day of working) {
        if (!day.start_time || !day.end_time) return `${WEEK_DAYS[day.day_of_week]} requires a start and end time.`;
        if (day.end_time <= day.start_time) return `${WEEK_DAYS[day.day_of_week]} end time must be after start time.`;
        const hasBreakStart = Boolean(day.break_start_time);
        const hasBreakEnd = Boolean(day.break_end_time);
        if (hasBreakStart !== hasBreakEnd) return `${WEEK_DAYS[day.day_of_week]} break requires both start and end time.`;
        if (hasBreakStart && (day.break_end_time <= day.break_start_time || day.break_start_time < day.start_time || day.break_end_time > day.end_time)) {
            return `${WEEK_DAYS[day.day_of_week]} break must be inside the shift and end after it starts.`;
        }
    }
    return "";
};

export const applyWeeklyScheduleTemplate = (value, template) => {
    const base = { ...value, schedule_type: template === "rotating" ? "Rotating / No Fixed Rest Day" : "Fixed" };
    const restDays = template === "mon-fri" ? new Set([5, 6]) : template === "mon-sat" ? new Set([6]) : new Set();
    return {
        ...base,
        days: value.days.map((day) => {
            const rest = restDays.has(day.day_of_week);
            if (template === "custom") return { ...day };
            if (template === "rotating") {
                return { ...day, state: "Working Day", start_time: day.start_time || "08:00", end_time: day.end_time || "17:00", break_start_time: day.break_start_time || "12:00", break_end_time: day.break_end_time || "13:00" };
            }
            return rest
                ? { ...day, state: "Rest Day", start_time: null, end_time: null, break_start_time: null, break_end_time: null }
                : { ...day, state: "Working Day", start_time: day.start_time || "08:00", end_time: day.end_time || "17:00", break_start_time: day.break_start_time || "12:00", break_end_time: day.break_end_time || "13:00" };
        }),
    };
};
