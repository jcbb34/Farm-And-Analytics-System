// Inventory summary cards
function InventorySummaryCards({ cards }) {
    return (
        <section className="inventory-page-summary-grid">
            {cards.map((card) => (
                <article
                    className={`inventory-page-summary-card ${card.className}`}
                    key={card.id}
                >
                    <div className="inventory-page-summary-icon">
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

export default InventorySummaryCards;
