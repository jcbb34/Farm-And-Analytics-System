"use client";

// Colors used by the report charts
const chartColors = [
    "#16a34a",
    "#3b82f6",
    "#f59e0b",
    "#8b5cf6",
    "#ef4444",
    "#6b7280",
    "#0ea5e9",
    "#84cc16",
];

// Add a color when the API data does not have one
export function colorizeData(items = []) {
    return items.map((item, index) => ({
        ...item,
        color:
            item.color ||
            chartColors[index % chartColors.length],
    }));
}

// Build the CSS gradient used by the pie chart
function buildPieGradient(items) {
    const total =
        items.reduce(
            (currentTotal, item) =>
                currentTotal + Number(item.value),
            0
        ) || 1;

    let previousPercentage = 0;

    const sections = items.map((item) => {
        const percentage =
            (Number(item.value) / total) * 100;

        const start = previousPercentage;
        const end = start + percentage;

        previousPercentage = end;

        return `${item.color} ${start}% ${end}%`;
    });

    return `conic-gradient(${sections.join(", ")})`;
}

// Simple bar chart for report totals
export function BarChart({ data, unit }) {
    const safeData = Array.isArray(data)
        ? data.filter((item) =>
              Number.isFinite(Number(item.value))
          )
        : [];

    if (safeData.length === 0) {
        return (
            <div className="reports-page-empty-table">
                <span className="material-symbols-outlined">
                    bar_chart
                </span>

                <p>No report data is available yet.</p>
            </div>
        );
    }

    const maximumValue = Math.max(
        ...safeData.map((item) => Number(item.value)),
        1
    );

    return (
        <div className="reports-page-bar-chart">
            <div className="reports-page-bar-area">
                {safeData.map((item) => (
                    <div
                        className="reports-page-bar-column"
                        key={item.label}
                    >
                        <div className="reports-page-bar-value">
                            {item.value}
                            {unit}
                        </div>

                        <div className="reports-page-bar-track">
                            <div
                                className="reports-page-bar-fill"
                                style={{
                                    height: `${
                                        (Number(item.value) /
                                            maximumValue) *
                                        100
                                    }%`,
                                }}
                            />
                        </div>

                        <span>{item.label}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}

// Simple pie chart with a legend
export function PieChart({ data }) {
    const safeData = Array.isArray(data)
        ? data.filter((item) => Number(item.value) > 0)
        : [];

    if (safeData.length === 0) {
        return (
            <div className="reports-page-empty-table">
                <span className="material-symbols-outlined">
                    pie_chart
                </span>

                <p>No report data is available yet.</p>
            </div>
        );
    }

    const coloredData = colorizeData(safeData);

    const total = coloredData.reduce(
        (currentTotal, item) =>
            currentTotal + Number(item.value),
        0
    );

    return (
        <div className="reports-page-pie-layout">
            <div
                className="reports-page-pie-chart"
                style={{
                    background: buildPieGradient(coloredData),
                }}
            >
                <div className="reports-page-pie-center">
                    <strong>{total}</strong>
                    <span>Total</span>
                </div>
            </div>

            <div className="reports-page-pie-legend">
                {coloredData.map((item) => (
                    <div key={item.label}>
                        <span
                            className="reports-page-legend-color"
                            style={{ background: item.color }}
                        />

                        <p>{item.label}</p>
                        <strong>{item.value}</strong>
                    </div>
                ))}
            </div>
        </div>
    );
}
