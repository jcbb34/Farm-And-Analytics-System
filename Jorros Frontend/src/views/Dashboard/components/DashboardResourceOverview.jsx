"use client";

function DashboardResourceOverview({
    cards,
    loading,
    totalRecords,
    periodLabel,
}) {
    return (
        <section className="dashboard-resource-overview">
            <div className="dashboard-resource-heading">
                <div>
                    <h2>Resource Consumption</h2>
                    <p>
                        Actual inventory-linked usage for {periodLabel || "the selected period"}.
                    </p>
                </div>

                <span>{totalRecords || 0} usage records</span>
            </div>

            <div className="dashboard-resource-grid">
                {cards.map((card) => (
                    <article key={card.id} className="dashboard-resource-card">
                        <span className="material-symbols-outlined">
                            {card.icon}
                        </span>

                        <div>
                            <small>{card.title}</small>
                            <strong>{loading ? "…" : card.value}</strong>
                        </div>
                    </article>
                ))}
            </div>
        </section>
    );
}

export default DashboardResourceOverview;
