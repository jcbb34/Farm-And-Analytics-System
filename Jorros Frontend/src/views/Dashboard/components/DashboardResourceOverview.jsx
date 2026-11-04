"use client";

/**
 * @param {{cards: import('../resourceOverview.js').ResourceCard[], loading: boolean,
 * totalRecords: number, periodLabel: string, error?: string, stockError?: string,
 * onRetry: () => void}} props
 */
export default function DashboardResourceOverview({ cards, loading, totalRecords, periodLabel, error, stockError, onRetry }) {
    return (
        <section className="dashboard-resource-overview" aria-labelledby="resource-overview-title" aria-busy={loading}>
            <div className="dashboard-resource-heading">
                <div>
                    <h2 id="resource-overview-title">Resource Consumption</h2>
                    <p>Actual inventory-linked usage for {periodLabel || "the selected period"}.</p>
                </div>
                <span role="status">{loading ? "Loading resource data…" : error ? "Resource data unavailable" : `${totalRecords.toLocaleString("en-PH")} ${totalRecords === 1 ? "usage record" : "usage records"}`}</span>
            </div>
            {error ? (
                <p role="alert" className="dashboard-resource-error">{error} <button type="button" onClick={onRetry}>Retry</button></p>
            ) : (
                <div className="dashboard-resource-grid">
                    {cards.map((card) => (
                        <article key={card.id} className="dashboard-resource-card">
                            <span className="material-symbols-outlined" aria-hidden="true">{card.icon}</span>
                            <div><small>{card.title}</small>{loading ? <span className="dashboard-resource-skeleton" aria-hidden="true" /> : <strong>{card.value}</strong>}</div>
                        </article>
                    ))}
                </div>
            )}
            {stockError && !loading && <p role="status" className="dashboard-resource-error">Current stock information is unavailable. <button type="button" onClick={onRetry}>Retry</button></p>}
        </section>
    );
}
