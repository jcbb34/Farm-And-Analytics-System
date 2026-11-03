"use client";

function DashboardSummaryCards({ cards }) {
    return (
        <section className="summary-grid">
            {cards.map((card) => (
                <article
                    key={card.id}
                    className={`summary-card ${card.className}`}
                >
                    <h3>{card.title}</h3>
                    <h2>{card.value}</h2>
                </article>
            ))}
        </section>
    );
}

export default DashboardSummaryCards;
