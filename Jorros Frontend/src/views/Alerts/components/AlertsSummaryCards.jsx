"use client";

// Alert totals shown at the top of the page.
export default function AlertsSummaryCards({ alerts = [] }) {
    const active = alerts.filter((item) => item.status === "Active").length;
    const disabled = alerts.filter((item) => item.status === "Disabled").length;
    const highPriority = alerts.filter((item) => item.priority === "High").length;

    const cards = [
        {
            title: "Total Alerts",
            value: alerts.length,
            label: "Configured alerts",
            icon: "notifications",
            className: "total",
        },
        {
            title: "Active Alerts",
            value: active,
            label: "Currently enabled",
            icon: "notification_important",
            className: "active",
        },
        {
            title: "High Priority",
            value: highPriority,
            label: "Needs attention",
            icon: "priority_high",
            className: "configured",
        },
        {
            title: "Disabled Alerts",
            value: disabled,
            label: "Currently inactive",
            icon: "notifications_off",
            className: "disabled",
        },
    ];

    return (
        <section className="alerts-page-summary-grid">
            {cards.map((card) => (
                <article
                    key={card.title}
                    className={`alerts-page-summary-card ${card.className}`}
                >
                    <span className="alerts-page-summary-icon">
                        <span className="material-symbols-outlined">
                            {card.icon}
                        </span>
                    </span>

                    <div>
                        <p>{card.title}</p>
                        <h2>{card.value}</h2>
                        <small>{card.label}</small>
                    </div>
                </article>
            ))}
        </section>
    );
}
