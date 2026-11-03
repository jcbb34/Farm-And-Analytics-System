// Summary cards shown at the top of Crops Management.
function CropsSummaryCards({ cards }) {
    return (
        <section className="crop-summary-grid">
            {cards.map((card) => (
                <article
                    className={`crop-summary-card ${card.className}`}
                    key={card.id}
                >
                    <div className="crop-summary-icon">
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

export default CropsSummaryCards;
