"use client";

// Archived records table and filters
function formatDateTime(value) {
    if (!value) {
        return "Not specified";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Not specified";
    }

    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function getClassName(value = "") {
    return String(value)
        .toLowerCase()
        .replaceAll(" ", "-")
        .replaceAll("/", "-");
}

export default function ArchivedRecordsPanel({
    archivedRecords = [],
    filteredRecords = [],
    search,
    moduleFilter,
    onSearchChange,
    onModuleFilterChange,
    onResetFilters,
    onRestore,
    onDelete,
}) {
    return (
        <section className="settings-page-section">
            <div className="settings-page-section-heading">
                <div>
                    <h2>Archived Records</h2>
                    <p>
                        Review, restore, or permanently remove archived farm
                        records.
                    </p>
                </div>
            </div>

            <div className="settings-page-archive-filter">
                <div className="settings-page-search-box">
                    <span className="material-symbols-outlined">search</span>
                    <input
                        type="text"
                        placeholder="Search archived records..."
                        value={search}
                        onChange={(event) => onSearchChange(event.target.value)}
                    />
                </div>

                <select
                    value={moduleFilter}
                    onChange={(event) =>
                        onModuleFilterChange(event.target.value)
                    }
                >
                    <option value="All">All Modules</option>
                    <option value="Crop">Crop</option>
                    <option value="Livestock">Livestock</option>
                    <option value="Inventory">Inventory</option>
                    <option value="Report">Report</option>
                </select>

                <button type="button" onClick={onResetFilters}>
                    <span className="material-symbols-outlined">
                        restart_alt
                    </span>
                    Reset
                </button>
            </div>

            <article className="settings-page-archive-card">
                <div className="settings-page-table-wrapper">
                    <table className="settings-page-archive-table">
                        <thead>
                            <tr>
                                <th>Record Name</th>
                                <th>Module</th>
                                <th>Reason</th>
                                <th>Archived Date</th>
                                <th>Archived By</th>
                                <th>Actions</th>
                            </tr>
                        </thead>

                        <tbody>
                            {filteredRecords.length > 0 ? (
                                filteredRecords.map((record) => (
                                    <tr key={record.id}>
                                        <td>
                                            <div className="settings-page-archive-name">
                                                <span className="material-symbols-outlined">
                                                    archive
                                                </span>
                                                <strong>
                                                    {record.recordName}
                                                </strong>
                                            </div>
                                        </td>

                                        <td>
                                            <span
                                                className={`settings-page-module-badge ${getClassName(
                                                    record.module
                                                )}`}
                                            >
                                                {record.module}
                                            </span>
                                        </td>

                                        <td>{record.reason}</td>
                                        <td>
                                            {formatDateTime(record.archivedDate)}
                                        </td>
                                        <td>{record.archivedBy}</td>

                                        <td>
                                            <div className="settings-page-archive-actions">
                                                <button
                                                    type="button"
                                                    title="Restore record"
                                                    onClick={() =>
                                                        onRestore(record)
                                                    }
                                                >
                                                    <span className="material-symbols-outlined">
                                                        restore
                                                    </span>
                                                </button>

                                                <button
                                                    type="button"
                                                    className="delete"
                                                    title="Permanently delete record"
                                                    onClick={() =>
                                                        onDelete(record)
                                                    }
                                                >
                                                    <span className="material-symbols-outlined">
                                                        delete
                                                    </span>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td
                                        colSpan="6"
                                        className="settings-page-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            inventory_2
                                        </span>
                                        <p>
                                            No archived records match the
                                            selected filters.
                                        </p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="settings-page-table-footer">
                    Showing {filteredRecords.length} of {archivedRecords.length}{" "}
                    archived records
                </div>
            </article>
        </section>
    );
}
