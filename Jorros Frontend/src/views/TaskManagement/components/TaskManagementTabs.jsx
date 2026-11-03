const BASE_TABS = [
    { id: "tasks", label: "Tasks", icon: "task_alt" },
    { id: "employees", label: "Employees", icon: "groups" },
];


export default function TaskManagementTabs({
    activeTab,
    canManageCareProtocols,
    canManageLeaveRequests,
    onChange,
}) {
    const tabs = [
        ...BASE_TABS,
        ...(canManageLeaveRequests
            ? [{ id: "leave", label: "Leave Requests", icon: "event_busy" }]
            : []),
        ...(canManageCareProtocols
            ? [{ id: "templates", label: "Care Protocols", icon: "clinical_notes" }]
            : []),
        { id: "archives", label: "Archives", icon: "archive" },
    ];

    return (
        <nav className="workforce-tabs workforce-primary-tabs" aria-label="Task Management sections">
            {tabs.map(({ id, label, icon }) => (
                <button
                    key={id}
                    type="button"
                    className={`workforce-tab workforce-primary-tab ${activeTab === id ? "active" : ""}`}
                    onClick={() => onChange(id)}
                    aria-current={activeTab === id ? "page" : undefined}
                >
                    <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
                    <span>{label}</span>
                </button>
            ))}
        </nav>
    );
}
