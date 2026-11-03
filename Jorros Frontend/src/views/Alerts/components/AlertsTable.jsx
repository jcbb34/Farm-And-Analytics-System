"use client";

import "./AlertsTable.css";

// Alert records table and row actions.
export default function AlertsTable({
    filteredAlerts,
    totalAlerts,
    loading,
    error,
    actionBusyId,
    onView,
    onEdit,
    onTest,
    onToggle,
    onDelete,
    getClassName,
    getCategoryIcon,
}) {
    return (
        <>
            <div className="alerts-page-record-heading">
                <div>
                    <h2>Alert Records</h2>
                    <p>{filteredAlerts.length} records found</p>
                </div>
            </div>

            <div className="alerts-page-table-wrapper alerts-page-scroll-table">
                <table className="alerts-page-table alerts-page-records-table">
                    <thead>
                        <tr>
                            <th>Alert Name</th>
                            <th>Subject</th>
                            <th>Condition</th>
                            <th>Priority</th>
                            <th>Status</th>
                            <th>Source</th>
                            <th>Actions</th>
                        </tr>
                    </thead>

                    <tbody>
                        {loading ? (
                            <tr>
                                <td colSpan="7" className="alerts-page-empty-table">
                                    <span className="material-symbols-outlined">
                                        progress_activity
                                    </span>
                                    <p>Loading alert records...</p>
                                </td>
                            </tr>
                        ) : error ? (
                            <tr>
                                <td colSpan="7" className="alerts-page-empty-table">
                                    <span className="material-symbols-outlined">
                                        error
                                    </span>
                                    <p>{error}</p>
                                </td>
                            </tr>
                        ) : filteredAlerts.length > 0 ? (
                            filteredAlerts.map((item) => (
                                <tr key={item.id}>
                                    <td>
                                        <div className="alerts-page-name-cell">
                                            <span
                                                className={`alerts-page-category-icon ${getClassName(
                                                    item.category
                                                )}`}
                                            >
                                                <span className="material-symbols-outlined">
                                                    {getCategoryIcon(item.category)}
                                                </span>
                                            </span>

                                            <div>
                                                <strong>{item.alertName}</strong>
                                            </div>
                                        </div>
                                    </td>

                                    <td>{item.subject}</td>

                                    <td>
                                        <strong className="alerts-page-threshold">
                                            {item.condition} {item.threshold} {item.unit}
                                        </strong>
                                    </td>

                                    <td>
                                        <span
                                            className={`alerts-page-priority ${getClassName(
                                                item.priority
                                            )}`}
                                        >
                                            {item.priority}
                                        </span>
                                    </td>

                                    <td>
                                        <span
                                            className={`alerts-page-status ${getClassName(
                                                item.status
                                            )}`}
                                        >
                                            {item.status}
                                        </span>
                                    </td>

                                    <td>
                                        <span
                                            className={`alerts-page-source-badge ${
                                                item.isAutomatic ? "system" : "manual"
                                            }`}
                                        >
                                            {item.isAutomatic ? "System" : "Manual"}
                                        </span>
                                    </td>

                                    <td>
                                        <div className="alerts-page-row-actions">
                                            <button
                                                type="button"
                                                className="alerts-page-view-button"
                                                title="View alert details"
                                                aria-label={`View ${item.alertName}`}
                                                onClick={() => onView(item)}
                                            >
                                                <span className="material-symbols-outlined">
                                                    visibility
                                                </span>
                                                <span className="alerts-page-view-button-label">
                                                    View
                                                </span>
                                            </button>

                                            {!item.isAutomatic && (
                                                <>
                                                    <button
                                                        type="button"
                                                        title="Edit alert"
                                                        onClick={() => onEdit(item)}
                                                        disabled={actionBusyId === item.id}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            edit
                                                        </span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        title="Test alert"
                                                        onClick={() => onTest(item)}
                                                        disabled={actionBusyId === item.id}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            play_arrow
                                                        </span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        className={`alerts-page-toggle-button ${
                                                            item.status === "Active"
                                                                ? "enabled"
                                                                : ""
                                                        }`}
                                                        title="Enable or disable alert"
                                                        onClick={() => onToggle(item)}
                                                        disabled={actionBusyId === item.id}
                                                    >
                                                        <span className="alerts-page-toggle-circle" />
                                                    </button>

                                                    <button
                                                        type="button"
                                                        className="delete"
                                                        title="Delete alert"
                                                        onClick={() => onDelete(item)}
                                                        disabled={actionBusyId === item.id}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            delete
                                                        </span>
                                                    </button>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="7" className="alerts-page-empty-table">
                                    <span className="material-symbols-outlined">
                                        notifications_off
                                    </span>
                                    <p>No alert records match the filters.</p>
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            <div className="alerts-page-table-footer">
                Showing {filteredAlerts.length} of {totalAlerts} alert records
            </div>
        </>
    );
}
