const CARD_DEFINITIONS = [
    { key: "pending", label: "Pending", icon: "pending_actions" },
    { key: "progress", label: "In Progress", icon: "play_circle" },
    { key: "review", label: "For Review", icon: "fact_check" },
    { key: "overdue", label: "Overdue", icon: "warning" },
    { key: "held", label: "Held / Review", icon: "pause_circle" },
    { key: "reassign", label: "Reassignment", icon: "assignment_ind" },
];


export default function TaskSummaryCards({ stats, loading, error, onRetry }) {
    return (
        <>
        {error && <p className="workforce-error" role="status">{error} <button type="button" className="workforce-button secondary compact" onClick={onRetry}>Retry totals</button></p>}
        <section className="workforce-stats task-management-compact-stats" aria-label="Task Management summary" aria-busy={loading}>
            {CARD_DEFINITIONS.map(({ key, label, icon }) => (
                <div key={key} className={`workforce-stat ${key}`}>
                    <div className="workforce-stat-icon">
                        <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
                    </div>
                    <div className="workforce-stat-copy">
                        <span className="workforce-stat-label">{label}</span>
                        <strong>{loading && !stats ? "…" : stats ? (stats[key] ?? 0) : "—"}</strong>
                    </div>
                </div>
            ))}
        </section>
        </>
    );
}
