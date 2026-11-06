import { useRef, useState } from "react";
import { formatDateKey } from "../../utils/farmCalendar.js";
import { attendanceReviewReasons, formatStaffTime } from "./staffAttendance.js";

export default function StaffAttendanceSummary({ todayKey, timezone, summary, ready, busy, error, updatedAt, employeeName, onRefresh, onViewToday, onFilter, onViewRow, onTask }) {
    const reviewRef = useRef(null);
    const [coverageOnly, setCoverageOnly] = useState(false);
    const cards = [
        { id: "present", label: "Present", value: summary.present, icon: "how_to_reg", hint: "Includes late arrivals and checked-out staff" },
        { id: "not-checked-in", label: "Not Checked In", value: summary.notCheckedIn, icon: "schedule", hint: "Scheduled staff; excused time is excluded" },
        { id: "leave", label: "On Leave", value: summary.leave, icon: "event_busy", hint: "Approved leave only" },
        { id: "coverage", label: "Needs Coverage", value: summary.coverageTasks.length, icon: "assignment_late", hint: "Tasks requiring an assignment" },
    ];
    const reviewCount = summary.reviewRows.length + summary.coverageTasks.length;
    const visibleReviewCount = coverageOnly ? summary.coverageTasks.length : reviewCount;
    const showCoverage = () => {
        setCoverageOnly(true);
        if (reviewRef.current) reviewRef.current.open = true;
        window.requestAnimationFrame(() => {
            reviewRef.current?.scrollIntoView({ block: "nearest", behavior: "instant" });
            reviewRef.current?.querySelector("summary")?.focus({ preventScroll: true });
        });
    };
    return <section className="staff-attendance-overview" aria-labelledby="staff-today-title" aria-busy={busy}>
        <div className="staff-attendance-heading">
            <div><h2 id="staff-today-title">Today’s Attendance</h2><p><time dateTime={todayKey}>{formatDateKey(todayKey, { weekday: "long", month: "short", day: "numeric", year: "numeric" })}</time> · {timezone} · {employeeName || "All employees"}</p></div>
            <div className="staff-attendance-actions">
                <button type="button" className="workforce-button" onClick={onViewToday}>View Today’s Attendance</button>
            </div>
        </div>
        <p className="staff-attendance-freshness" role="status">{error ? "Attendance could not be updated." : busy ? "Updating attendance…" : updatedAt ? `Last updated ${formatStaffTime(updatedAt, timezone)} (farm time)` : "Loading attendance…"}</p>
        {error && <div className="workforce-error" role="alert">Unable to load attendance. {error} <button type="button" className="workforce-button secondary compact" disabled={busy} onClick={onRefresh}>Retry attendance</button></div>}
        <div className="staff-attendance-counts">
            {cards.map((card) => <button key={card.id} type="button" className={`staff-attendance-count ${card.id}`} disabled={!ready || busy}
                onClick={() => card.id === "coverage" ? showCoverage() : onFilter(card.id)} aria-label={ready ? `${card.label}: ${card.value}. ${card.id === "coverage" ? "View tasks needing coverage" : "View employees"}` : `${card.label}: unavailable`}>
                <span className="staff-attendance-count-icon material-symbols-outlined" aria-hidden="true">{card.icon}</span><span><span className="staff-attendance-count-label">{card.label}</span><strong>{ready ? card.value : busy ? "…" : "—"}</strong><small>{card.hint}</small></span>
            </button>)}
        </div>
        {ready && <details className="staff-attendance-review" ref={reviewRef}>
            <summary>{coverageOnly ? "Needs Coverage" : "Needs Review"} <span>{visibleReviewCount}</span></summary>
            {coverageOnly && <button type="button" className="workforce-button secondary" onClick={() => setCoverageOnly(false)}>Show all review items</button>}
            <p>Possible absence is a warning, not a confirmed absence. Confirm the employee’s situation before making a correction.</p>
            {visibleReviewCount === 0 ? <p>{coverageOnly ? "No tasks need coverage today." : "No attendance or coverage issues to review."}</p> : <ul>
                {!coverageOnly && summary.reviewRows.map((row) => <li key={`employee-${row.employee.id}`}><div><strong>{row.employee.full_name}</strong><span>{attendanceReviewReasons(row, todayKey).join(" · ")}</span></div><button type="button" className="workforce-button secondary" onClick={() => onViewRow(row)}>View attendance</button></li>)}
                {summary.coverageTasks.map((task) => <li key={`task-${task.id}`}><div><strong>{task.name || "Unassigned task"}</strong><span>Needs coverage · {task.activity_date}</span></div><button type="button" className="workforce-button secondary" onClick={() => onTask(task)}>Resolve assignment</button></li>)}
            </ul>}
        </details>}
    </section>;
}
