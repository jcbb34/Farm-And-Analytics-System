"use client";

import { ImportHistoryPanel } from "../../../components/SmartImport/SmartImport.jsx";

// System export, import, backup, and reset tools
export default function SystemDataPanel({
    backups,
    backupCreating,
    backupError,
    backupLoading,
    isSystemAdministrator,
    smartImportRefreshKey,
    onCreateBackup,
    onDownloadBackup,
    onExportData,
    onOpenSmartImport,
    onResetPreferences,
}) {
    const formatDateTime = (value) => {
        if (!value) return "—";

        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) return "—";

        return parsed.toLocaleString("en-PH", {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    };

    const getClassName = (value = "") =>
        String(value)
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "-")
            .replace(/^-+|-+$/g, "");

    const formatFileSize = (value) => {
        const bytes = Number(value || 0);
        if (!Number.isFinite(bytes) || bytes <= 0) return "0 B";

        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;

        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    };

    return (
        <section className="settings-page-section">
            <div className="settings-page-section-heading">
                <div>
                    <h2>System Data</h2>
                    <p>
                        Export settings, smart-import structured farm records,
                        create database backups, or reset supported settings.
                    </p>
                </div>
            </div>

            <div className="settings-page-data-grid">
                <article className="settings-page-data-card export">
                    <span>
                        <span className="material-symbols-outlined">
                            file_download
                        </span>
                    </span>

                    <div>
                        <h3>Export Data</h3>
                        <p>
                            Create and download a server-side JSON export of the
                            current SQL Server application records.
                        </p>
                    </div>

                    <button type="button" onClick={onExportData}>
                        Export Data
                    </button>
                </article>

                <article className="settings-page-data-card import">
                    <span>
                        <span className="material-symbols-outlined">
                            upload_file
                        </span>
                    </span>

                    <div>
                        <h3>Import Farm Data</h3>
                        <p>
                            Analyze XLSX, CSV, or JSON records, detect the
                            correct farm module, review mappings, duplicates,
                            and generated IDs before importing.
                        </p>
                    </div>

                    <button type="button" onClick={onOpenSmartImport}>
                        Smart Import
                    </button>
                </article>

                <article className="settings-page-data-card backup">
                    <span>
                        <span className="material-symbols-outlined">backup</span>
                    </span>

                    <div>
                        <h3>Backup System</h3>
                        <p>
                            Back up the database together with task evidence
                            photos and thumbnails for recovery.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onCreateBackup}
                        disabled={backupCreating}
                    >
                        {backupCreating ? "Creating Backup..." : "Create Backup"}
                    </button>
                </article>

                <article className="settings-page-data-card reset">
                    <span>
                        <span className="material-symbols-outlined">
                            restart_alt
                        </span>
                    </span>

                    <div>
                        <h3>Reset Preferences</h3>
                        <p>
                            Restore notification and interface preferences on
                            this browser without deleting farm records.
                        </p>
                    </div>

                    <button type="button" onClick={onResetPreferences}>
                        Reset Preferences
                    </button>
                </article>
            </div>

            <article className="settings-page-backup-info">
                <span className="material-symbols-outlined">verified</span>
                <div>
                    <strong>Database Backup</strong>
                    <p>
                        Backups are created by FastAPI from the live SQL Server
                        application tables and stored under Jorros Backend/backups.
                        Smart Import writes validated farm records to the database
                        only after preview and confirmation. Export Data creates a
                        current server export, while Reset Preferences never deletes
                        database records.
                    </p>
                </div>
            </article>

            <article className="settings-page-archive-card">
                <div className="settings-page-section-heading">
                    <div>
                        <h2>Backup History</h2>
                        <p>
                            Database and task-photo recovery backups created by the
                            system.
                        </p>
                    </div>
                </div>

                <div className="settings-page-table-wrapper">
                    <table className="settings-page-archive-table">
                        <thead>
                            <tr>
                                <th>Backup</th>
                                <th>Created</th>
                                <th>Status</th>
                                <th>Tables</th>
                                <th>Rows</th>
                                <th>Size</th>
                                <th>Actions</th>
                            </tr>
                        </thead>

                        <tbody>
                            {backups.length > 0 ? (
                                backups.map((backup) => (
                                    <tr key={backup.id}>
                                        <td>
                                            <div className="settings-page-archive-name">
                                                <span className="material-symbols-outlined">
                                                    database
                                                </span>
                                                <strong>{backup.backupCode}</strong>
                                            </div>
                                        </td>
                                        <td>
                                            {formatDateTime(
                                                backup.completedAt || backup.createdAt
                                            )}
                                        </td>
                                        <td>
                                            <span
                                                className={`settings-page-module-badge ${getClassName(
                                                    backup.status
                                                )}`}
                                            >
                                                {backup.status}
                                            </span>
                                        </td>
                                        <td>{backup.tableCount}</td>
                                        <td>{backup.rowCount}</td>
                                        <td>{formatFileSize(backup.recoveryAvailable ? backup.recoverySizeBytes : backup.fileSizeBytes)}</td>
                                        <td>
                                            <div className="settings-page-archive-actions">
                                                <button
                                                    type="button"
                                                    title="Download backup"
                                                    disabled={backup.status !== "Completed"}
                                                    onClick={() => onDownloadBackup(backup)}
                                                >
                                                    <span className="material-symbols-outlined">
                                                        download
                                                    </span>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td
                                        colSpan="7"
                                        className="settings-page-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            backup
                                        </span>
                                        <p>
                                            {backupLoading
                                                ? "Loading backup history..."
                                                : backupError ||
                                                  "No database backup has been created yet."}
                                        </p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                <div className="settings-page-table-footer">
                    {backupError
                        ? backupError
                        : `Showing ${backups.length} backup record(s)`}
                </div>
            </article>

            <ImportHistoryPanel
                isAdministrator={isSystemAdministrator}
                refreshKey={smartImportRefreshKey}
            />
        </section>
    );
}
