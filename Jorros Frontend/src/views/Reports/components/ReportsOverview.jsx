// Summary cards shown at the top of Reports
function ReportsOverview({ summary }) {
    const summaryCards = [
        { title: "Approved Reports", value: summary?.approved, description: "Official locked reports", icon: "verified", className: "completed" },
        { title: "For Review", value: summary?.forReview, description: "Waiting for approval", icon: "rate_review", className: "crop" },
        { title: "Automatic Reports", value: summary?.automatic, description: "Scheduled generation", icon: "schedule", className: "livestock" },
        { title: "Custom Reports", value: summary?.custom, description: "On-demand reports", icon: "description", className: "inventory" },
    ];
    return (
        <section className="reports-page-summary-grid">
            {summaryCards.map((card) => (
                <article
                    className={`reports-page-summary-card ${card.className}`}
                    key={card.title}
                >
                    <span className="reports-page-summary-icon">
                        <span className="material-symbols-outlined">
                            {card.icon}
                        </span>
                    </span>

                    <div>
                        <p>{card.title}</p>
                        <h2>{card.value ?? "—"}</h2>
                        <small>{card.description}</small>
                    </div>
                </article>
            ))}
        </section>
    );
}

export default ReportsOverview;
