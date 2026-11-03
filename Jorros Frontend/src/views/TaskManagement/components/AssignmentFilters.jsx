export default function AssignmentFilters({
    employees,
    filtersAreDefault,
    onClear,
    onClearDate,
    priority,
    priorityOptions,
    reassignment,
    schedule,
    search,
    selectedDate,
    selectedEmployee,
    setPriority,
    setReassignment,
    setSchedule,
    setSearch,
    setSelectedEmployee,
    setStatus,
    status,
    statusOptions,
}) {
    return (
        <div className="assignment-filters" aria-label="Assignment search and filters">
            {selectedDate && (
                <div className="assignment-calendar-filter">
                    <span className="material-symbols-outlined" aria-hidden="true">calendar_month</span>
                    <span>Calendar date: <strong>{selectedDate}</strong></span>
                    <button type="button" onClick={onClearDate} aria-label="Clear calendar date filter">
                        <span className="material-symbols-outlined" aria-hidden="true">close</span>
                    </button>
                </div>
            )}
            <div className="assignment-filter-primary-row">
                <label className="assignment-search">
                    <span className="material-symbols-outlined" aria-hidden="true">search</span>
                    <input
                        value={search}
                        onChange={(event) => setSearch(event.target.value)}
                        placeholder="Search task, code, employee, field, pen, or location..."
                        aria-label="Search assignments"
                    />
                </label>
                <button
                    type="button"
                    className="assignment-clear"
                    onClick={onClear}
                    disabled={filtersAreDefault}
                >
                    Clear Filters
                </button>
            </div>
            <div className="assignment-filter-select-row">
                <label className="assignment-filter-field">
                    <span>Schedule</span>
                    <select value={schedule} onChange={(event) => setSchedule(event.target.value)} aria-label="Filter by schedule">
                        <option value="Actionable Now">Today & Missed / Attention</option>
                        <option value="Today">Today</option>
                        <option value="Missed / Overdue">Missed / Overdue</option>
                        <option value="Upcoming">Upcoming</option>
                        <option value="Next 7 Days">Next 7 Days</option>
                        <option value="All Scheduled">All Scheduled</option>
                    </select>
                </label>
                <label className="assignment-filter-field">
                    <span>Status</span>
                    <select value={status} onChange={(event) => setStatus(event.target.value)} aria-label="Filter by task status">
                        {statusOptions.map((option) => (
                            <option key={option} value={option}>{option === "All" ? "All Statuses" : option}</option>
                        ))}
                    </select>
                </label>
                <label className="assignment-filter-field">
                    <span>Priority</span>
                    <select value={priority} onChange={(event) => setPriority(event.target.value)} aria-label="Filter by priority">
                        {priorityOptions.map((option) => (
                            <option key={option} value={option}>{option === "All" ? "All Priorities" : option}</option>
                        ))}
                    </select>
                </label>
                <label className="assignment-filter-field">
                    <span>Employee</span>
                    <select value={selectedEmployee} onChange={(event) => setSelectedEmployee(event.target.value)} aria-label="Filter by employee">
                        <option value="All">All Employees</option>
                        <option value="Unassigned">Unassigned</option>
                        {employees.map((employee) => (
                            <option key={employee.id} value={String(employee.id)}>{employee.full_name}</option>
                        ))}
                    </select>
                </label>
                <label className="assignment-filter-field">
                    <span>Assignment State</span>
                    <select value={reassignment} onChange={(event) => setReassignment(event.target.value)} aria-label="Filter by reassignment">
                        <option value="All">All Assignment States</option>
                        <option value="Needs Reassignment">Needs Reassignment</option>
                        <option value="Leave Coverage">Leave Coverage</option>
                        <option value="No Reassignment">No Reassignment Needed</option>
                    </select>
                </label>
            </div>
        </div>
    );
}
