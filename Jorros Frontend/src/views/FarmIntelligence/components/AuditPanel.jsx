"use client";

import { useEffect, useMemo, useState } from "react";

import {
    UPDATE_EVENT,
    getAuditLogs,
    loadAuditLogsFromServer,
} from "../../../services/farmIntelligenceService.js";

// Formats audit timestamps for display.
function formatDateTime(value) {
    if (!value) return "—";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    return date.toLocaleString("en-PH", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

// Audit log tab.
export default function AuditPanel() {
    const [logs, setLogs] =
        useState(getAuditLogs);
    const [search, setSearch] =
        useState("");
    const [moduleFilter, setModuleFilter] =
        useState("All");

    const filtered = useMemo(() => {
        const query =
            search.trim().toLowerCase();

        return logs.filter((log) => {
            const matchesModule =
                moduleFilter === "All" ||
                log.module === moduleFilter;

            const haystack = [
                log.action,
                log.module,
                log.recordName,
                log.details,
                log.user,
            ]
                .join(" ")
                .toLowerCase();

            return (
                matchesModule &&
                (!query ||
                    haystack.includes(
                        query
                    ))
            );
        });
    }, [
        logs,
        search,
        moduleFilter,
    ]);

    useEffect(() => {
        let cancelled = false;

        const refresh = () => {
            loadAuditLogsFromServer()
                .then((serverLogs) => {
                    if (!cancelled) {
                        setLogs(serverLogs);
                    }
                })
                .catch(() => {
                    if (!cancelled) {
                        setLogs(getAuditLogs());
                    }
                });
        };

        refresh();
        window.addEventListener(UPDATE_EVENT, refresh);

        return () => {
            cancelled = true;
            window.removeEventListener(UPDATE_EVENT, refresh);
        };
    }, []);

    return (
        <section className="fi-card fi-audit-panel">
            <div className="fi-section-heading fi-audit-heading">
                <div>
                    <h3>
                        Audit Log
                    </h3>
                    <p>
                        Track important system actions by user, module, record, and timestamp.
                    </p>
                </div>
            </div>

            <div className="fi-filter-row fi-audit-filter-row">
                <div className="fi-search">
                    <span className="material-symbols-outlined">
                        search
                    </span>
                    <input
                        value={search}
                        onChange={(event) =>
                            setSearch(
                                event.target
                                    .value
                            )
                        }
                        placeholder="Search activity..."
                    />
                </div>

                <select
                    value={moduleFilter}
                    onChange={(event) =>
                        setModuleFilter(
                            event.target.value
                        )
                    }
                >
                    <option>All</option>
                    <option>Crop</option>
                    <option>Livestock</option>
                    <option>Inventory</option>
                    <option>Production &amp; Sales</option>
                    <option>Report</option>
                    <option>System</option>
                </select>
            </div>

            <div className="fi-table-wrapper fi-audit-table-wrapper">
                <table className="fi-table">
                    <thead>
                        <tr>
                            <th>Date & Time</th>
                            <th>Action</th>
                            <th>Module</th>
                            <th>Record</th>
                            <th>User</th>
                            <th>Details</th>
                        </tr>
                    </thead>

                    <tbody>
                        {filtered.map((log) => (
                            <tr key={log.id}>
                                <td>
                                    {formatDateTime(
                                        log.timestamp
                                    )}
                                </td>
                                <td>
                                    <strong>
                                        {log.action}
                                    </strong>
                                </td>
                                <td>
                                    <span className="fi-module-badge">
                                        {log.module}
                                    </span>
                                </td>
                                <td>
                                    {log.recordName ||
                                        "—"}
                                </td>
                                <td>
                                    {log.user}
                                </td>
                                <td>
                                    {log.details ||
                                        "—"}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </section>
    );
}

