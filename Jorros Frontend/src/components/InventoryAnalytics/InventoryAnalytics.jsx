"use client";

import { useMemo } from "react";

import {
    Bar,
    Doughnut,
    Line,
} from "react-chartjs-2";

import {
    ArcElement,
    BarElement,
    CategoryScale,
    Chart as ChartJS,
    Filler,
    Legend,
    LineElement,
    LinearScale,
    PointElement,
    Tooltip,
} from "chart.js";

import "./InventoryAnalytics.css";

ChartJS.register(
    ArcElement,
    BarElement,
    CategoryScale,
    Filler,
    Legend,
    LineElement,
    LinearScale,
    PointElement,
    Tooltip
);

function getStockStatus(item) {
    const quantity = Number(
        item.quantity
    );

    const reorderLevel = Number(
        item.reorderLevel
    );

    if (quantity <= 0) {
        return "Out of Stock";
    }

    if (quantity <= reorderLevel) {
        return "Low Stock";
    }

    return "In Stock";
}

function getClassName(value = "") {
    return value
        .toLowerCase()
        .replaceAll(" ", "-");
}

function parseDate(dateValue) {
    if (!dateValue) {
        return null;
    }

    const [year, month, day] =
        dateValue.split("-").map(Number);

    return new Date(
        year,
        month - 1,
        day
    );
}

function formatDate(dateValue) {
    const date = parseDate(dateValue);

    if (!date) {
        return "Not specified";
    }

    return date.toLocaleDateString(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
        }
    );
}

function formatCurrency(value) {
    return Number(value || 0).toLocaleString(
        "en-PH",
        {
            style: "currency",
            currency: "PHP",
            maximumFractionDigits: 0,
        }
    );
}

function getDaysUntil(dateValue) {
    const targetDate =
        parseDate(dateValue);

    if (!targetDate) {
        return null;
    }

    const today = new Date();

    today.setHours(0, 0, 0, 0);
    targetDate.setHours(0, 0, 0, 0);

    return Math.ceil(
        (targetDate - today) /
            (1000 * 60 * 60 * 24)
    );
}

function getExpirationStatus(daysLeft) {
    if (daysLeft === null) {
        return "No Expiration";
    }

    if (daysLeft < 0) {
        return "Expired";
    }

    if (daysLeft === 0) {
        return "Expires Today";
    }

    if (daysLeft <= 30) {
        return "Critical";
    }

    if (daysLeft <= 120) {
        return "Expiring Soon";
    }

    return "Valid";
}

function getMonthKey(date) {
    const year = date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    return `${year}-${month}`;
}

function getPreviousSixMonths() {
    const months = [];
    const currentDate = new Date();

    for (
        let monthOffset = 5;
        monthOffset >= 0;
        monthOffset -= 1
    ) {
        const date = new Date(
            currentDate.getFullYear(),
            currentDate.getMonth() -
                monthOffset,
            1
        );

        months.push({
            key: getMonthKey(date),

            label:
                date.toLocaleDateString(
                    "en-US",
                    {
                        month: "short",
                    }
                ),
        });
    }

    return months;
}

function getHistoryChange(record) {
    if (
        record.type ===
        "Set Exact Quantity"
    ) {
        return (
            Number(record.newQuantity) -
            Number(
                record.previousQuantity
            )
        );
    }

    if (record.type === "Restock") {
        return Number(
            record.quantity
        );
    }

    return -Number(
        record.quantity
    );
}

function InventoryAnalytics({
    inventory,
    movementSummary = null,
    summary = null,
}) {
    const inventoryStatistics =
        useMemo(() => {
            if (summary) {
                const lowStock = summary.low_stock || 0;
                const outOfStock = summary.out_of_stock || 0;
                return {
                    inStock: summary.in_stock || 0, lowStock, outOfStock,
                    totalValue: summary.total_value || 0,
                    suppliers: summary.supplier_count || 0,
                    attentionRequired: lowStock + outOfStock,
                };
            }
            const inStock =
                inventory.filter(
                    (item) =>
                        getStockStatus(
                            item
                        ) === "In Stock"
                ).length;

            const lowStock =
                inventory.filter(
                    (item) =>
                        getStockStatus(
                            item
                        ) === "Low Stock"
                ).length;

            const outOfStock =
                inventory.filter(
                    (item) =>
                        getStockStatus(
                            item
                        ) ===
                        "Out of Stock"
                ).length;

            const totalValue =
                inventory.reduce(
                    (total, item) =>
                        total +
                        Number(
                            item.quantity
                        ) *
                            Number(
                                item.cost
                            ),
                    0
                );

            const suppliers =
                new Set(
                    inventory.map(
                        (item) =>
                            item.supplier
                    )
                ).size;

            return {
                inStock,
                lowStock,
                outOfStock,
                totalValue,
                suppliers,

                attentionRequired:
                    lowStock +
                    outOfStock,
            };
        }, [inventory, summary]);

    const categoryValues =
        useMemo(() => {
            if (summary) return summary.category_values || [];
            const groupedCategories =
                new Map();

            inventory.forEach(
                (item) => {
                    const current =
                        groupedCategories.get(
                            item.category
                        ) || 0;

                    const itemValue =
                        Number(
                            item.quantity
                        ) *
                        Number(item.cost);

                    groupedCategories.set(
                        item.category,
                        current + itemValue
                    );
                }
            );

            return Array.from(
                groupedCategories.entries()
            )
                .map(
                    ([
                        category,
                        value,
                    ]) => ({
                        category,
                        value,
                    })
                )
                .sort(
                    (first, second) =>
                        second.value -
                        first.value
                );
        }, [inventory, summary]);

    const stockAlertItems =
        useMemo(() => {
            if (summary) {
                return (summary.lowStockItems || []).map((item) => ({
                    ...item,
                    stockStatus: getStockStatus(item),
                    suggestedOrder: Math.max(0, Number(item.reorderLevel) * 2 - Number(item.quantity)),
                }));
            }
            return inventory
                .filter(
                    (item) =>
                        getStockStatus(
                            item
                        ) !== "In Stock"
                )
                .map((item) => {
                    const recommendedLevel =
                        Number(
                            item.reorderLevel
                        ) * 2;

                    const suggestedOrder =
                        Math.max(
                            0,
                            recommendedLevel -
                                Number(
                                    item.quantity
                                )
                        );

                    return {
                        ...item,

                        stockStatus:
                            getStockStatus(
                                item
                            ),

                        suggestedOrder,
                    };
                })
                .sort(
                    (first, second) => {
                        if (
                            first.stockStatus ===
                                "Out of Stock" &&
                            second.stockStatus !==
                                "Out of Stock"
                        ) {
                            return -1;
                        }

                        if (
                            second.stockStatus ===
                                "Out of Stock" &&
                            first.stockStatus !==
                                "Out of Stock"
                        ) {
                            return 1;
                        }

                        return (
                            Number(
                                first.quantity
                            ) -
                            Number(
                                second.quantity
                            )
                        );
                    }
                );
        }, [inventory, summary]);

    const expirationRecords =
        useMemo(() => {
            if (summary) {
                return (summary.expirationItems || []).map((item) => {
                    const daysLeft = getDaysUntil(item.expirationDate);
                    return { ...item, daysLeft, expirationStatus: getExpirationStatus(daysLeft) };
                });
            }
            return inventory
                .filter(
                    (item) =>
                        Boolean(
                            item.expirationDate
                        )
                )
                .map((item) => {
                    const daysLeft =
                        getDaysUntil(
                            item.expirationDate
                        );

                    return {
                        ...item,

                        daysLeft,

                        expirationStatus:
                            getExpirationStatus(
                                daysLeft
                            ),
                    };
                })
                .sort(
                    (first, second) =>
                        first.daysLeft -
                        second.daysLeft
                );
        }, [inventory, summary]);

    const supplierPerformance =
        useMemo(() => {
            if (summary) return summary.supplier_performance || [];
            const suppliers =
                new Map();

            inventory.forEach(
                (item) => {
                    const existing =
                        suppliers.get(
                            item.supplier
                        ) || {
                            supplier:
                                item.supplier,

                            itemCount: 0,

                            totalQuantity:
                                0,

                            inventoryValue:
                                0,

                            attentionItems:
                                0,

                            latestDelivery:
                                "",
                        };

                    existing.itemCount +=
                        1;

                    existing.totalQuantity +=
                        Number(
                            item.quantity
                        );

                    existing.inventoryValue +=
                        Number(
                            item.quantity
                        ) *
                        Number(item.cost);

                    if (
                        getStockStatus(
                            item
                        ) !== "In Stock"
                    ) {
                        existing.attentionItems +=
                            1;
                    }

                    if (
                        !existing.latestDelivery ||
                        item.dateAcquired >
                            existing.latestDelivery
                    ) {
                        existing.latestDelivery =
                            item.dateAcquired;
                    }

                    suppliers.set(
                        item.supplier,
                        existing
                    );
                }
            );

            return Array.from(
                suppliers.values()
            ).sort(
                (first, second) =>
                    second.inventoryValue -
                    first.inventoryValue
            );
        }, [inventory, summary]);

    const monthlyMovements =
        useMemo(() => {
            const months =
                getPreviousSixMonths();

            if (Array.isArray(movementSummary)) {
                const saved = new Map(movementSummary.map((row) => [row.month, row]));
                return months.map((month) => {
                    const row = saved.get(month.key);
                    const incoming = Number(row?.incoming || 0);
                    const outgoing = Number(row?.outgoing || 0);
                    return { ...month, incoming, outgoing, net: incoming - outgoing };
                });
            }

            const movementMap =
                new Map(
                    months.map(
                        (month) => [
                            month.key,
                            {
                                incoming: 0,
                                outgoing: 0,
                                net: 0,
                            },
                        ]
                    )
                );

            inventory.forEach(
                (item) => {
                    (
                        item.stockHistory ||
                        []
                    ).forEach(
                        (record) => {
                            if (
                                !record.date
                            ) {
                                return;
                            }

                            const monthKey =
                                record.date.slice(
                                    0,
                                    7
                                );

                            if (
                                !movementMap.has(
                                    monthKey
                                )
                            ) {
                                return;
                            }

                            const change =
                                getHistoryChange(
                                    record
                                );

                            const current =
                                movementMap.get(
                                    monthKey
                                );

                            if (change >= 0) {
                                current.incoming +=
                                    change;
                            } else {
                                current.outgoing +=
                                    Math.abs(
                                        change
                                    );
                            }

                            current.net +=
                                change;
                        }
                    );
                }
            );

            return months.map(
                (month) => ({
                    ...month,
                    ...movementMap.get(
                        month.key
                    ),
                })
            );
        }, [inventory, movementSummary]);

    const stockStatusChartData =
        useMemo(() => {
            return {
                labels: [
                    "In Stock",
                    "Low Stock",
                    "Out of Stock",
                ],

                datasets: [
                    {
                        data: [
                            inventoryStatistics.inStock,
                            inventoryStatistics.lowStock,
                            inventoryStatistics.outOfStock,
                        ],

                        backgroundColor: [
                            "#22c55e",
                            "#f59e0b",
                            "#ef4444",
                        ],

                        borderWidth: 0,
                    },
                ],
            };
        }, [inventoryStatistics]);

    const categoryValueChartData =
        useMemo(() => {
            return {
                labels:
                    categoryValues.map(
                        (item) =>
                            item.category
                    ),

                datasets: [
                    {
                        label:
                            "Inventory Value",

                        data:
                            categoryValues.map(
                                (item) =>
                                    item.value
                            ),

                        backgroundColor:
                            "#43a047",

                        borderRadius: 7,
                    },
                ],
            };
        }, [categoryValues]);

    const stockMovementChartData =
        useMemo(() => {
            return {
                labels:
                    monthlyMovements.map(
                        (month) =>
                            month.label
                    ),

                datasets: [
                    {
                        label:
                            "Stock Received",

                        data:
                            monthlyMovements.map(
                                (month) =>
                                    month.incoming
                            ),

                        borderColor:
                            "#16a34a",

                        backgroundColor:
                            "rgba(22, 163, 74, 0.14)",

                        pointBackgroundColor:
                            "#16a34a",

                        borderWidth: 3,

                        tension: 0.35,

                        fill: true,
                    },
                    {
                        label:
                            "Stock Released",

                        data:
                            monthlyMovements.map(
                                (month) =>
                                    month.outgoing
                            ),

                        borderColor:
                            "#f59e0b",

                        backgroundColor:
                            "rgba(245, 158, 11, 0.08)",

                        pointBackgroundColor:
                            "#f59e0b",

                        borderWidth: 3,

                        tension: 0.35,

                        fill: false,
                    },
                ],
            };
        }, [monthlyMovements]);

    const doughnutOptions = {
        responsive: true,

        maintainAspectRatio: false,

        cutout: "64%",

        plugins: {
            legend: {
                position: "bottom",

                labels: {
                    usePointStyle: true,

                    padding: 18,

                    font: {
                        family: "Inter",
                        size: 11,
                    },
                },
            },
        },
    };

    const categoryBarOptions = {
        responsive: true,

        maintainAspectRatio: false,

        indexAxis: "y",

        plugins: {
            legend: {
                display: false,
            },

            tooltip: {
                callbacks: {
                    label(context) {
                        return formatCurrency(
                            context.parsed.x
                        );
                    },
                },
            },
        },

        scales: {
            x: {
                beginAtZero: true,

                ticks: {
                    callback(value) {
                        return `₱${Number(
                            value
                        ).toLocaleString(
                            "en-PH",
                            {
                                notation:
                                    "compact",
                            }
                        )}`;
                    },
                },

                grid: {
                    color:
                        "rgba(0, 0, 0, 0.06)",
                },
            },

            y: {
                grid: {
                    display: false,
                },
            },
        },
    };

    const lineOptions = {
        responsive: true,

        maintainAspectRatio: false,

        plugins: {
            legend: {
                position: "bottom",

                labels: {
                    usePointStyle: true,

                    padding: 18,

                    font: {
                        family: "Inter",
                        size: 11,
                    },
                },
            },
        },

        scales: {
            x: {
                grid: {
                    display: false,
                },
            },

            y: {
                beginAtZero: true,

                ticks: {
                    precision: 0,
                },

                grid: {
                    color:
                        "rgba(0, 0, 0, 0.06)",
                },
            },
        },
    };

    return (
        <section className="inventory-analytics-section">
            <div className="inventory-analytics-heading">
                <div>
                    <h2>
                        Inventory Analytics
                    </h2>

                    <p>
                        Review stock availability,
                        inventory value, movement,
                        expiration, and supplier
                        performance.
                    </p>
                </div>

                <span>
                    Updated from current inventory
                    records
                </span>
            </div>

            <div className="inventory-analytics-chart-grid">
                <article className="inventory-analytics-card inventory-stock-distribution-card">
                    <div className="inventory-analytics-card-header">
                        <div>
                            <h3>
                                Stock Distribution
                            </h3>

                            <p>
                                Current inventory
                                records by stock status.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            donut_large
                        </span>
                    </div>

                    <div className="inventory-analytics-chart-area inventory-doughnut-chart">
                        <Doughnut
                            data={
                                stockStatusChartData
                            }
                            options={
                                doughnutOptions
                            }
                        />
                    </div>
                </article>

                <article className="inventory-analytics-card">
                    <div className="inventory-analytics-card-header">
                        <div>
                            <h3>
                                Value by Category
                            </h3>

                            <p>
                                Remaining inventory
                                cost grouped by
                                category.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            payments
                        </span>
                    </div>

                    <div className="inventory-analytics-chart-area">
                        <Bar
                            data={
                                categoryValueChartData
                            }
                            options={
                                categoryBarOptions
                            }
                        />
                    </div>
                </article>

                <article className="inventory-analytics-card inventory-movement-card">
                    <div className="inventory-analytics-card-header">
                        <div>
                            <h3>
                                Stock Movement Trend
                            </h3>

                            <p>
                                Received and released
                                inventory during the
                                previous six months.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            monitoring
                        </span>
                    </div>

                    <div className="inventory-analytics-chart-area">
                        <Line
                            data={
                                stockMovementChartData
                            }
                            options={
                                lineOptions
                            }
                        />
                    </div>
                </article>

                <article className="inventory-analytics-card inventory-health-card">
                    <div className="inventory-analytics-card-header">
                        <div>
                            <h3>
                                Inventory Health
                            </h3>

                            <p>
                                Current inventory
                                monitoring statistics.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            analytics
                        </span>
                    </div>

                    <div className="inventory-health-stat-grid">
                        <div>
                            <span className="material-symbols-outlined">
                                inventory_2
                            </span>

                            <small>
                                Total Records
                            </small>

                            <strong>
                                {
                                    summary?.total ?? inventory.length
                                }
                            </strong>
                        </div>

                        <div>
                            <span className="material-symbols-outlined">
                                warning
                            </span>

                            <small>
                                Needs Attention
                            </small>

                            <strong>
                                {
                                    inventoryStatistics.attentionRequired
                                }
                            </strong>
                        </div>

                        <div>
                            <span className="material-symbols-outlined">
                                store
                            </span>

                            <small>
                                Suppliers
                            </small>

                            <strong>
                                {
                                    inventoryStatistics.suppliers
                                }
                            </strong>
                        </div>

                        <div>
                            <span className="material-symbols-outlined">
                                account_balance_wallet
                            </span>

                            <small>
                                Current Value
                            </small>

                            <strong>
                                {formatCurrency(
                                    inventoryStatistics.totalValue
                                )}
                            </strong>
                        </div>
                    </div>

                    <div className="inventory-health-message">
                        <span className="material-symbols-outlined">
                            {inventoryStatistics.attentionRequired >
                            0
                                ? "notification_important"
                                : "verified"}
                        </span>

                        <p>
                            {inventoryStatistics.attentionRequired >
                            0
                                ? `${inventoryStatistics.attentionRequired} inventory record(s) require restocking or review.`
                                : "All inventory records currently have sufficient stock."}
                        </p>
                    </div>
                </article>
            </div>

            <div className="inventory-monitoring-grid">
                <article className="inventory-monitoring-card">
                    <div className="inventory-monitoring-header">
                        <div>
                            <h3>
                                Low-Stock Alerts
                            </h3>

                            <p>
                                Items that have reached
                                or fallen below their
                                reorder level. The first 25 appear below.
                            </p>
                        </div>

                        <span className="inventory-monitoring-count">
                            {
                                inventoryStatistics.attentionRequired
                            }{" "}
                            {inventoryStatistics.attentionRequired ===
                            1
                                ? "item"
                                : "items"}
                        </span>
                    </div>

                    <div className="inventory-alert-list">
                        {stockAlertItems.length >
                        0 ? (
                            stockAlertItems.map(
                                (item) => (
                                    <article
                                        className="inventory-alert-item"
                                        key={
                                            item.id
                                        }
                                    >
                                        <span
                                            className={`inventory-alert-icon ${getClassName(
                                                item.stockStatus
                                            )}`}
                                        >
                                            <span className="material-symbols-outlined">
                                                {item.stockStatus ===
                                                "Out of Stock"
                                                    ? "error"
                                                    : "warning"}
                                            </span>
                                        </span>

                                        <div className="inventory-alert-main">
                                            <div className="inventory-alert-title">
                                                <strong>
                                                    {
                                                        item.name
                                                    }
                                                </strong>

                                                <span
                                                    className={getClassName(
                                                        item.stockStatus
                                                    )}
                                                >
                                                    {
                                                        item.stockStatus
                                                    }
                                                </span>
                                            </div>

                                            <p>
                                                {
                                                    item.itemCode
                                                }{" "}
                                                •{" "}
                                                {
                                                    item.location
                                                }
                                            </p>

                                            <div className="inventory-alert-stock-details">
                                                <div>
                                                    <small>
                                                        Available
                                                    </small>

                                                    <strong>
                                                        {
                                                            item.quantity
                                                        }{" "}
                                                        {
                                                            item.unit
                                                        }
                                                    </strong>
                                                </div>

                                                <div>
                                                    <small>
                                                        Reorder
                                                        Level
                                                    </small>

                                                    <strong>
                                                        {
                                                            item.reorderLevel
                                                        }{" "}
                                                        {
                                                            item.unit
                                                        }
                                                    </strong>
                                                </div>

                                                <div>
                                                    <small>
                                                        Suggested
                                                        Order
                                                    </small>

                                                    <strong>
                                                        {
                                                            item.suggestedOrder
                                                        }{" "}
                                                        {
                                                            item.unit
                                                        }
                                                    </strong>
                                                </div>
                                            </div>
                                        </div>
                                    </article>
                                )
                            )
                        ) : (
                            <div className="inventory-monitoring-empty">
                                <span className="material-symbols-outlined">
                                    verified
                                </span>

                                <p>
                                    No low-stock alerts
                                    found.
                                </p>
                            </div>
                        )}
                    </div>
                </article>

                <article className="inventory-monitoring-card">
                    <div className="inventory-monitoring-header">
                        <div>
                            <h3>
                                Expiration Monitoring
                            </h3>

                            <p>
                                Inventory records sorted
                                by the nearest expiration
                                date. The first 25 appear below.
                            </p>
                        </div>

                        <span className="inventory-monitoring-count">
                            {
                                summary?.expiration_count ?? expirationRecords.length
                            }{" "}
                            dated items
                        </span>
                    </div>

                    <div className="inventory-expiration-list">
                        {expirationRecords.length >
                        0 ? (
                            expirationRecords
                                .map((item) => (
                                    <article
                                        className="inventory-expiration-item"
                                        key={
                                            item.id
                                        }
                                    >
                                        <span
                                            className={`inventory-expiration-icon ${getClassName(
                                                item.expirationStatus
                                            )}`}
                                        >
                                            <span className="material-symbols-outlined">
                                                event
                                            </span>
                                        </span>

                                        <div className="inventory-expiration-main">
                                            <strong>
                                                {
                                                    item.name
                                                }
                                            </strong>

                                            <p>
                                                {
                                                    item.category
                                                }{" "}
                                                •{" "}
                                                {
                                                    item.quantity
                                                }{" "}
                                                {
                                                    item.unit
                                                }
                                            </p>
                                        </div>

                                        <div className="inventory-expiration-right">
                                            <span
                                                className={getClassName(
                                                    item.expirationStatus
                                                )}
                                            >
                                                {
                                                    item.expirationStatus
                                                }
                                            </span>

                                            <strong>
                                                {formatDate(
                                                    item.expirationDate
                                                )}
                                            </strong>

                                            <small>
                                                {item.daysLeft <
                                                0
                                                    ? `${Math.abs(
                                                          item.daysLeft
                                                      )} days overdue`
                                                    : item.daysLeft ===
                                                      0
                                                    ? "Expires today"
                                                    : `${item.daysLeft} days remaining`}
                                            </small>
                                        </div>
                                    </article>
                                ))
                        ) : (
                            <div className="inventory-monitoring-empty">
                                <span className="material-symbols-outlined">
                                    event_available
                                </span>

                                <p>
                                    No expiration dates
                                    recorded.
                                </p>
                            </div>
                        )}
                    </div>
                </article>
            </div>

            <article className="inventory-supplier-card">
                <div className="inventory-supplier-header">
                    <div>
                        <h3>
                            Supplier Performance
                        </h3>

                        <p>
                            Summary of items, inventory
                            value, latest delivery, and
                            records that need
                            attention. The top 25 suppliers appear below.
                        </p>
                    </div>

                    <span>
                        {
                            inventoryStatistics.suppliers
                        }{" "}
                        suppliers
                    </span>
                </div>

                <div className="inventory-supplier-table-wrapper">
                    <table className="inventory-supplier-table">
                        <thead>
                            <tr>
                                <th>
                                    Supplier
                                </th>

                                <th>
                                    Supplied Items
                                </th>

                                <th>
                                    Remaining Quantity
                                </th>

                                <th>
                                    Inventory Value
                                </th>

                                <th>
                                    Needs Attention
                                </th>

                                <th>
                                    Latest Delivery
                                </th>

                                <th>
                                    Performance
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {supplierPerformance.map(
                                (supplier) => {
                                    const performance =
                                        supplier.attentionItems ===
                                        0
                                            ? "Good"
                                            : supplier.attentionItems <
                                              supplier.itemCount
                                            ? "Review"
                                            : "Needs Action";

                                    return (
                                        <tr
                                            key={
                                                supplier.supplier
                                            }
                                        >
                                            <td>
                                                <div className="inventory-supplier-name">
                                                    <span className="material-symbols-outlined">
                                                        store
                                                    </span>

                                                    <strong>
                                                        {
                                                            supplier.supplier
                                                        }
                                                    </strong>
                                                </div>
                                            </td>

                                            <td>
                                                {
                                                    supplier.itemCount
                                                }
                                            </td>

                                            <td>
                                                {
                                                    supplier.totalQuantity
                                                }
                                            </td>

                                            <td>
                                                {formatCurrency(
                                                    supplier.inventoryValue
                                                )}
                                            </td>

                                            <td>
                                                {
                                                    supplier.attentionItems
                                                }
                                            </td>

                                            <td>
                                                {formatDate(
                                                    supplier.latestDelivery
                                                )}
                                            </td>

                                            <td>
                                                <span
                                                    className={`inventory-supplier-performance ${getClassName(
                                                        performance
                                                    )}`}
                                                >
                                                    {
                                                        performance
                                                    }
                                                </span>
                                            </td>
                                        </tr>
                                    );
                                }
                            )}
                        </tbody>
                    </table>
                </div>
            </article>

            <div className="inventory-analytics-tip">
                <span className="material-symbols-outlined">
                    lightbulb
                </span>

                <p>
                    <strong>
                        Inventory Tip:
                    </strong>{" "}
                    Restock items before they reach zero
                    and release products with the
                    nearest expiration date first.
                </p>
            </div>
        </section>
    );
}

export default InventoryAnalytics;
