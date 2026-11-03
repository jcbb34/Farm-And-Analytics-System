"use client";

import { useEffect } from "react";

// Read-only alert details.

function formatDateTime(value) {
    if (!value) return "Not triggered";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not triggered";

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

function formatSourceType(value) {
    if (!value) return "Manual";

    return String(value)
        .replaceAll("_", " ")
        .split(" ")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");
}

function AlertDetailsModal({
    open,
    alert,
    onClose,
}) {
    useEffect(() => {
        if (!open) {
            return undefined;
        }

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open]);

    if (!open || !alert) {
        return null;
    }

    const conditionText = [
        alert.condition,
        alert.threshold,
        alert.unit,
    ]
        .filter(Boolean)
        .join(" ");

    return (
        <div
            className="alerts-page-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="alerts-page-modal alerts-page-details-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="alerts-page-modal-header">
                    <div>
                        <h2>
                            Alert Details
                        </h2>

                        <p>
                            View the complete information for {alert.alertName}.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close alert details"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="alerts-page-modal-form">
                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                notifications
                            </span>

                            <div>
                                <h3>
                                    Alert Information
                                </h3>

                                <p>
                                    Complete alert configuration and current status.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-details-grid">
                            <div className="alerts-page-detail-item">
                                <span>
                                    Alert Name
                                </span>

                                <strong>
                                    {alert.alertName || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Category
                                </span>

                                <strong>
                                    {alert.category || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Subject
                                </span>

                                <strong>
                                    {alert.subject || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Alert Type
                                </span>

                                <strong>
                                    {alert.alertType || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Condition
                                </span>

                                <strong className="alerts-page-threshold">
                                    {conditionText || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Priority
                                </span>

                                <span
                                    className={`alerts-page-priority ${getClassName(
                                        alert.priority
                                    )}`}
                                >
                                    {alert.priority || "—"}
                                </span>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Status
                                </span>

                                <span
                                    className={`alerts-page-status ${getClassName(
                                        alert.status
                                    )}`}
                                >
                                    {alert.status || "—"}
                                </span>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Management
                                </span>

                                <strong>
                                    {alert.isAutomatic
                                        ? "Automatic"
                                        : "Manual"}
                                </strong>
                            </div>

                            {alert.isAutomatic && (
                                <div className="alerts-page-detail-item">
                                    <span>
                                        Source
                                    </span>

                                    <strong>
                                        {formatSourceType(
                                            alert.sourceType
                                        )}
                                    </strong>
                                </div>
                            )}

                            <div className="alerts-page-detail-item">
                                <span>
                                    Last Triggered
                                </span>

                                <strong>
                                    {formatDateTime(
                                        alert.lastTriggered
                                    )}
                                </strong>
                            </div>
                        </div>
                    </section>

                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                description
                            </span>

                            <div>
                                <h3>
                                    Description
                                </h3>

                                <p>
                                    Purpose and monitoring details for this alert.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-detail-description">
                            {alert.description ||
                                "No alert description provided."}
                        </div>
                    </section>

                    <footer className="alerts-page-form-footer">
                        <button
                            type="button"
                            className="alerts-page-save-button"
                            onClick={onClose}
                        >
                            Close
                        </button>
                    </footer>
                </div>
            </div>
        </div>
    );
}

export default AlertDetailsModal;
