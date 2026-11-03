"use client";

import "./PageState.css";

const stateIcons = {
    loading: "progress_activity",
    empty: "inbox",
    error: "error",
    offline: "cloud_off",
};

function PageState({
    type = "empty",
    title,
    message,
    actionLabel,
    onAction,
    compact = false,
}) {
    return (
        <section
            className={`app-page-state app-page-state-${type} ${
                compact ? "compact" : ""
            }`}
            role={type === "error" ? "alert" : "status"}
        >
            <span className="material-symbols-outlined app-page-state-icon">
                {stateIcons[type] || "info"}
            </span>

            <h2>{title || "Nothing to display"}</h2>

            {message && <p>{message}</p>}

            {actionLabel && onAction && (
                <button type="button" onClick={onAction}>
                    <span className="material-symbols-outlined">
                        refresh
                    </span>
                    {actionLabel}
                </button>
            )}
        </section>
    );
}

export default PageState;
