// A saved working exception supersedes an older, unclocked rest-day marker.
// The stored record stays available to audit and attendance history.
export function attendanceStatusForSchedule(attendance, availability) {
    const status = String(attendance?.status || "");
    if (status === "Day Off"
        && !attendance?.check_in_at && !attendance?.check_out_at
        && availability?.is_working_day === true
        && ["Working Day Override", "Changed Shift"].includes(availability.exception_type)
        && !availability.attendance_status) return "Not Checked In";
    return status === "Day Off" ? "Rest Day" : status;
}
