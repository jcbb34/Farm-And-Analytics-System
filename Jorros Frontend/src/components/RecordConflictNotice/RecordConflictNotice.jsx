import "./RecordConflictNotice.css";

export default function RecordConflictNotice({ conflict, disabled = false, reloadHint = "Reloading replaces this form with the latest saved values." }) {
    if (!conflict?.message) return null;
    return <div className="record-conflict-notice" role="alert">
        <strong>Record updated elsewhere</strong>
        <p>{conflict.message}</p>
        <p>{reloadHint}</p>
        <button type="button" onClick={conflict.reload} disabled={disabled || conflict.reloading}>{conflict.reloading ? "Reloading…" : "Reload latest record"}</button>
        {conflict.error && <p>{conflict.error}</p>}
    </div>;
}
