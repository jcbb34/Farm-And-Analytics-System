import "./ResourceChoiceTools.css";
export default function ResourceChoiceTools({ id, choice, label = "Search records", disabled = false }) {
    if (!choice) return null;
    return <div className="resource-choice-tools">
        <input id={id} type="search" aria-label={label} placeholder={label} maxLength={120} value={choice.search} onChange={event => choice.setSearch(event.target.value)} disabled={disabled} />
        <small role="status">{choice.loading ? "Loading choices…" : choice.error ? "Choices unavailable" : `${choice.pageCount} of ${choice.total} matching choices`}</small>
        {choice.error && <div role="alert">{choice.error} <button type="button" className="workforce-button secondary compact" onClick={choice.retry} disabled={disabled || choice.loading}>Retry choices</button></div>}
        {!choice.error && choice.pageCount < choice.total && <button type="button" className="workforce-button secondary compact" onClick={choice.loadMore} disabled={disabled || choice.loading}>Load more choices</button>}
    </div>;
}
