const statusClass = (value) => String(value || "").toLowerCase().replaceAll(" ", "-");


function PositionChips({ employee, includeTitle = false }) {
    const positions = employee.positions || [];
    if (!positions.length) return <span>{employee.position || "—"}</span>;

    return (
        <div className="employee-position-chips">
            {positions.map((position) => (
                <span
                    key={position.id}
                    className={`employee-position-chip ${position.is_primary ? "primary" : ""}`}
                    title={includeTitle ? position.category : undefined}
                >
                    {position.name}{position.is_primary ? " • Primary" : ""}
                </span>
            ))}
        </div>
    );
}


export function EmployeesPanel({
    employees,
    loading,
    onAdd,
    onArchive,
    onEdit,
    onSchedule,
    onStatusAction,
    onView,
    repairAccountLinks,
    repairingAccountLinks,
}) {
    return (
        <section className="workforce-card">
            <div className="workforce-card-header">
                <div>
                    <h2>Employee Profiles</h2>
                    <p className="workforce-card-subtitle">
                        View registered employees and manage farm worker profiles. Login accounts can be linked later
                        from account administration.
                    </p>
                </div>
                <div className="assignment-card-actions">
                    <button
                        className="workforce-button secondary"
                        type="button"
                        onClick={repairAccountLinks}
                        disabled={repairingAccountLinks}
                    >
                        <span className="material-symbols-outlined">link</span>
                        {repairingAccountLinks ? "Repairing…" : "Repair Account Links"}
                    </button>
                    <button className="workforce-button" onClick={onAdd}>
                        <span className="material-symbols-outlined">person_add</span>
                        Add Employee
                    </button>
                </div>
            </div>

            <div className="workforce-table-wrap">
                <table className="workforce-table">
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Name</th>
                            <th>Farm Positions</th>
                            <th>Contact</th>
                            <th>Employment</th>
                            <th>Work Schedule</th>
                            <th>Login</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan="9"><div className="workforce-empty">Loading employees…</div></td></tr>
                        ) : employees.length > 0 ? employees.map((employee) => (
                            <tr key={employee.id}>
                                <td><strong>{employee.employee_code}</strong></td>
                                <td>
                                    <strong>{employee.full_name}</strong>
                                    {employee.assigned_area && <><br /><small>{employee.assigned_area}</small></>}
                                </td>
                                <td><PositionChips employee={employee} includeTitle /></td>
                                <td>
                                    {employee.contact_number || "—"}
                                    {employee.email && <><br /><small>{employee.email}</small></>}
                                </td>
                                <td>
                                    {employee.employment_type || "—"}
                                    {employee.date_hired && <><br /><small>Hired {employee.date_hired}</small></>}
                                </td>
                                <td>
                                    <div className="employee-login-cell">
                                        <strong>
                                            {employee.schedule_status === "Needs Setup"
                                                ? "Schedule Needs Setup"
                                                : employee.weekly_schedule_summary || "Configured"}
                                        </strong>
                                        <small>
                                            {employee.next_rest_day
                                                ? `Next rest: ${employee.next_rest_day}`
                                                : employee.schedule_status === "Needs Setup"
                                                    ? "Legacy availability preserved"
                                                    : "No fixed upcoming rest day"}
                                        </small>
                                    </div>
                                </td>
                                <td>
                                    <div className="employee-login-cell">
                                        <strong>
                                            {employee.account_status
                                                || (employee.login_user_id ? "Account Linked" : "No Login Account")}
                                        </strong>
                                        <small>{employee.login_username || employee.account_issue || "No username linked"}</small>
                                    </div>
                                </td>
                                <td>
                                    <span className={`employee-status ${statusClass(employee.employment_status)}`}>
                                        {employee.employment_status}
                                    </span>
                                </td>
                                <td>
                                    <div className="employee-row-actions">
                                        <button
                                            type="button"
                                            className="employee-icon-action view"
                                            onClick={() => onView(employee)}
                                            title="View employee"
                                            aria-label={`View ${employee.full_name}`}
                                        >
                                            <span className="material-symbols-outlined">visibility</span>
                                        </button>
                                        <button
                                            type="button"
                                            className="employee-icon-action edit"
                                            onClick={() => onEdit(employee)}
                                            title="Edit employee"
                                            aria-label={`Edit ${employee.full_name}`}
                                        >
                                            <span className="material-symbols-outlined">edit</span>
                                        </button>
                                        <button
                                            type="button"
                                            className="employee-icon-action edit"
                                            onClick={() => onSchedule(employee)}
                                            title="Manage work schedule"
                                            aria-label={`Manage work schedule for ${employee.full_name}`}
                                        >
                                            <span className="material-symbols-outlined">calendar_month</span>
                                        </button>
                                        <button
                                            type="button"
                                            className={`employee-icon-action ${employee.employment_status === "Active" ? "deactivate" : "activate"}`}
                                            onClick={() => onStatusAction(employee)}
                                            title={employee.employment_status === "Active" ? "Deactivate employee" : "Activate employee"}
                                            aria-label={`${employee.employment_status === "Active" ? "Deactivate" : "Activate"} ${employee.full_name}`}
                                        >
                                            <span className="material-symbols-outlined">
                                                {employee.employment_status === "Active" ? "person_off" : "person_check"}
                                            </span>
                                        </button>
                                        <button
                                            type="button"
                                            className="employee-icon-action archive"
                                            onClick={() => onArchive(employee)}
                                            title="Archive employee"
                                            aria-label={`Archive ${employee.full_name}`}
                                        >
                                            <span className="material-symbols-outlined">archive</span>
                                        </button>
                                    </div>
                                </td>
                            </tr>
                        )) : (
                            <tr>
                                <td colSpan="9">
                                    <div className="workforce-empty">No employee profiles have been registered yet.</div>
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </section>
    );
}


export function EmployeeArchivesPanel({ archivedEmployees, loading, onRestore }) {
    return (
        <section className="workforce-card">
            <div className="workforce-card-header">
                <div>
                    <h2>Employee Archives</h2>
                    <p className="workforce-card-subtitle">
                        Archived employees are kept for historical records and can be restored without deleting past
                        tasks, attendance, or resource usage.
                    </p>
                </div>
                <div className="archive-count-badge">
                    <span className="material-symbols-outlined">archive</span>
                    {archivedEmployees.length} Archived
                </div>
            </div>
            <div className="workforce-table-wrap">
                <table className="workforce-table">
                    <thead>
                        <tr>
                            <th>Code</th>
                            <th>Employee</th>
                            <th>Farm Positions</th>
                            <th>Contact</th>
                            <th>Archive Details</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {loading ? (
                            <tr><td colSpan="6"><div className="workforce-empty">Loading archived employees…</div></td></tr>
                        ) : archivedEmployees.length ? archivedEmployees.map((employee) => (
                            <tr key={employee.id}>
                                <td><strong>{employee.employee_code}</strong></td>
                                <td>
                                    <strong>{employee.full_name}</strong><br />
                                    <span className="employee-status inactive">Archived</span>
                                </td>
                                <td><PositionChips employee={employee} /></td>
                                <td>
                                    {employee.contact_number || "—"}
                                    {employee.email && <><br /><small>{employee.email}</small></>}
                                </td>
                                <td>
                                    <strong>
                                        {employee.archived_at
                                            ? new Date(employee.archived_at).toLocaleDateString()
                                            : "—"}
                                    </strong>
                                    {employee.archived_by_name && <><br /><small>By {employee.archived_by_name}</small></>}
                                    {employee.archive_reason && (
                                        <div className="archive-reason">{employee.archive_reason}</div>
                                    )}
                                </td>
                                <td>
                                    <button
                                        className="workforce-button secondary compact"
                                        onClick={() => onRestore(employee)}
                                    >
                                        <span className="material-symbols-outlined">unarchive</span> Restore
                                    </button>
                                </td>
                            </tr>
                        )) : (
                            <tr><td colSpan="6"><div className="workforce-empty">No archived employee profiles.</div></td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </section>
    );
}
