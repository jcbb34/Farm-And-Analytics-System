import { formatDateKey } from "../../utils/farmCalendar.js";
import { anchorFromMonthInput, monthInputValue } from "./staffCalendarView.js";


const CALENDAR_VIEWS = [
    { id: "month", icon: "calendar_view_month", label: "Month" },
    { id: "week", icon: "calendar_view_week", label: "Week" },
    { id: "day", icon: "view_day", label: "Day" },
];


export function StaffCalendarToolbar({
    activeEmployees,
    anchor,
    availabilityFilter,
    changeView,
    employeeId,
    goToday,
    mode,
    move,
    setAnchor,
    setAvailabilityFilter,
    setEmployeeId,
    closeEditor,
    openFarmEvents,
    onClearFilters,
}) {
    return (
        <section className="staff-calendar-toolbar" aria-label="Staff calendar controls">
            <div className="staff-calendar-toolbar-primary">
                <div className="workforce-tabs staff-calendar-view-tabs" role="tablist" aria-label="Calendar view" onKeyDown={(event) => {
                    const current = CALENDAR_VIEWS.findIndex((view) => view.id === mode);
                    const next = event.key === "Home" ? 0 : event.key === "End" ? 2 : event.key === "ArrowRight" ? (current + 1) % 3 : event.key === "ArrowLeft" ? (current + 2) % 3 : -1;
                    if (next < 0) return;
                    event.preventDefault();
                    changeView(CALENDAR_VIEWS[next].id);
                    event.currentTarget.querySelectorAll('[role="tab"]')[next]?.focus();
                }}>
                    {CALENDAR_VIEWS.map(({ id, icon, label }) => (
                        <button
                            key={id}
                            type="button"
                            role="tab"
                            aria-selected={mode === id}
                            tabIndex={mode === id ? 0 : -1}
                            aria-controls="staff-calendar-content"
                            className={`workforce-tab ${mode === id ? "active" : ""}`}
                            onClick={() => changeView(id)}
                        >
                            <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
                            {label}
                        </button>
                    ))}
                </div>
                <div className="staff-calendar-date-navigation">
                <span className="staff-calendar-current-period">{formatDateKey(anchor, mode === "month" ? { month: "long", year: "numeric" } : { month: "short", day: "numeric", year: "numeric" })}{mode === "week" ? " · Week view" : ""}</span>
                <div className="staff-calendar-nav" aria-label="Calendar date navigation">
                    <button type="button" className="workforce-button secondary" onClick={() => move(-1)}>
                        <span className="material-symbols-outlined" aria-hidden="true">chevron_left</span>
                        <span className="staff-calendar-nav-label">Previous</span>
                    </button>
                    <button type="button" className="workforce-button secondary" onClick={goToday} title="Return to today in the current calendar view">Today</button>
                    <button type="button" className="workforce-button secondary" onClick={() => move(1)}>
                        <span className="staff-calendar-nav-label">Next</span>
                        <span className="material-symbols-outlined" aria-hidden="true">chevron_right</span>
                    </button>
                </div>
                </div>
                <div className="staff-calendar-toolbar-actions">
                    <button type="button" className="workforce-button secondary" onClick={openFarmEvents}><span className="material-symbols-outlined" aria-hidden="true">event_note</span>Farm Events & No-Work Days</button>
                </div>
            </div>
            <div className="staff-calendar-toolbar-filters" aria-label="Calendar filters">
                <label className="staff-calendar-filter">
                    <span>{mode === "month" ? "Month / Year" : "Date"}</span>
                    {mode === "month" ? <input type="month" value={monthInputValue(anchor)} onChange={(event) => {
                        setAnchor(anchorFromMonthInput(event.target.value, anchor)); closeEditor();
                    }} /> : <input type="date" value={anchor} onChange={(event) => {
                        if (event.target.value) setAnchor(event.target.value); closeEditor();
                    }} />}
                </label>
                <label className="staff-calendar-filter">
                    <span>Employee</span>
                    <select
                        value={employeeId}
                        onChange={(event) => {
                            setEmployeeId(event.target.value);
                            closeEditor();
                        }}
                    >
                        <option value="">All Employees</option>
                        {activeEmployees.map((employee) => (
                            <option value={employee.id} key={employee.id}>{employee.full_name}</option>
                        ))}
                    </select>
                </label>
                <label className="staff-calendar-filter">
                    <span>Status</span>
                    <select
                        value={availabilityFilter}
                        onChange={(event) => { setAvailabilityFilter(event.target.value); closeEditor(); }}
                    >
                        <option value="all">All Statuses</option>
                        <option value="present">Present</option>
                        <option value="not-checked-in">Not Checked In</option>
                        <option value="absent">Confirmed Absent</option>
                        <option value="not-scheduled">Not Scheduled / Excused</option>
                        <option value="needs-review">Needs Review</option>
                        <option value="scheduled">Scheduled / Working</option>
                        <option value="possible-absence">Possible Absence</option>
                        <option value="leave">On Leave</option>
                        <option value="coverage">Coverage Attention</option>
                    </select>
                </label>
                <div className="staff-calendar-filter-actions"><button type="button" className="workforce-button secondary" onClick={onClearFilters} disabled={!employeeId && availabilityFilter === "all"}>Clear Filters</button></div>
            </div>
        </section>
    );
}


export function StaffCalendarHeading({ anchor, mode, range, todayKey }) {
    const title = mode === "month"
        ? formatDateKey(anchor, { month: "long", year: "numeric" })
        : mode === "week"
            ? `${formatDateKey(range[0], { month: "short", day: "numeric" })} – ${formatDateKey(range[1], {
                month: "short",
                day: "numeric",
                year: "numeric",
            })}`
            : formatDateKey(anchor, {
                weekday: "long",
                month: "long",
                day: "numeric",
                year: "numeric",
            });
    const description = mode === "month"
        ? "Daily staffing totals and coverage signals."
        : mode === "week"
            ? "Employees by row with concise shift, availability, leave, and workload details."
            : "Select View Attendance for records, task coverage, and authorized corrections. Use Day Exception for a schedule change.";

    return (
        <div className="staff-calendar-title-row">
            <div>
                <h2>{mode === "day" ? `${anchor === todayKey ? "Today’s attendance" : anchor > todayKey ? "Staff schedule" : "Attendance"} · ` : ""}{title}</h2>
                <p>{description}</p>
            </div>
            <div className="calendar-legend" aria-label="Calendar legend">
                <span><i className="present" />Present</span>
                <span><i className="possible-absence" />Possible Absence</span>
                <span><i className="leave" />Leave</span>
                <span><i className="coverage-needed" />Needs Coverage</span>
                <span><i className="coverage-covered" />Covered</span>
            </div>
        </div>
    );
}
