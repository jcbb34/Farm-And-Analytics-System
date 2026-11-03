"use client";

// Livestock totals shown at the top of the page
export default function LivestockSummaryCards({ statistics = [] }) {
    return (
        <section className="livestock-summary-grid">
            {statistics.map((card) => (
                <article
                    className={`livestock-summary-card ${card.className}`}
                    key={card.id}
                >
                    <div className="livestock-summary-icon">
                        <span className="material-symbols-outlined">
                            {card.icon}
                        </span>
                    </div>

                    <div>
                        <p>{card.title}</p>
                        <h2>{card.value}</h2>
                    </div>
                </article>
            ))}
        </section>
    );
}
