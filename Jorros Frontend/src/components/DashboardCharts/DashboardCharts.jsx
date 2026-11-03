"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import {
    ArcElement,
    CategoryScale,
    Chart as ChartJS,
    Legend,
    LinearScale,
    LineElement,
    PointElement,
    Tooltip,
} from "chart.js";

import {
    Doughnut,
    Line,
    Pie,
} from "react-chartjs-2";

import "./DashboardCharts.css";

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    ArcElement,
    Tooltip,
    Legend
);

const filterOptions = [
    "Today",
    "This Month",
    "Last Month",
    "This Week",
    "Last Week",
    "Last 7 Days",
    "Last 30 Days",
    "This Year",
];

const chartColors = [
    "#43a047",
    "#fbc02d",
    "#ef5350",
    "#42a5f5",
    "#8e24aa",
    "#ffb74d",
];

function makeLineOptions(maxValue = 100, stepSize = 20) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
            mode: "index",
            intersect: false,
        },
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                enabled: true,
            },
        },
        scales: {
            y: {
                beginAtZero: true,
                min: 0,
                max: maxValue,
                ticks: {
                    stepSize,
                    font: {
                        size: 10,
                    },
                },
                grid: {
                    color: "#eeeeee",
                },
            },
            x: {
                ticks: {
                    font: {
                        size: 10,
                    },
                },
                grid: {
                    display: false,
                },
            },
        },
        elements: {
            line: {
                tension: 0.35,
                borderWidth: 2,
            },
            point: {
                radius: 3,
                hoverRadius: 5,
            },
        },
    };
}

const pieChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
        legend: {
            display: false,
        },
        tooltip: {
            enabled: true,
        },
    },
};

const doughnutChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "65%",
    plugins: {
        legend: {
            display: false,
        },
        tooltip: {
            enabled: true,
        },
    },
};


function normalizeHealthStatus(value) {
    const status = String(value || "")
        .trim()
        .replace(/\s+/g, " ")
        .toLowerCase();

    if (status === "healthy") return "Healthy";
    if (["at risk", "at-risk", "atrisk"].includes(status)) return "At Risk";
    if (["under treatment", "under-treatment", "treatment"].includes(status)) {
        return "Under Treatment";
    }
    if (status === "sick") return "Sick";

    return "";
}

function getLivestockCount(record) {
    const storedQuantity = Number(
        record.quantity ?? record.qty ?? record.count
    );

    // Individual livestock records normally have no quantity field.
    if (!Number.isFinite(storedQuantity) || storedQuantity <= 0) {
        return 1;
    }

    return storedQuantity;
}

function firstValidNumber(...values) {
    for (const value of values) {
        if (value === undefined || value === null || value === "") {
            continue;
        }

        const number = Number(value);

        if (Number.isFinite(number) && number >= 0) {
            return number;
        }
    }

    return 0;
}

function readHealthBreakdown(record) {
    const breakdown = record.healthBreakdown || record.health_breakdown || {};

    const explicitFields = [
        record.healthyQuantity,
        record.healthy_quantity,
        record.atRiskQuantity,
        record.at_risk_quantity,
        record.sickQuantity,
        record.sick_quantity,
        record.underTreatmentQuantity,
        record.under_treatment_quantity,
        breakdown.healthy,
        breakdown.atRisk,
        breakdown.at_risk,
        breakdown.sick,
        breakdown.underTreatment,
        breakdown.under_treatment,
    ];

    const hasExplicitBreakdown = explicitFields.some(
        (value) => value !== undefined && value !== null && value !== ""
    );

    if (hasExplicitBreakdown) {
        return {
            Healthy: firstValidNumber(
                record.healthyQuantity,
                record.healthy_quantity,
                breakdown.healthy
            ),
            "At Risk": firstValidNumber(
                record.atRiskQuantity,
                record.at_risk_quantity,
                breakdown.atRisk,
                breakdown.at_risk
            ),
            "Under Treatment": firstValidNumber(
                record.underTreatmentQuantity,
                record.under_treatment_quantity,
                breakdown.underTreatment,
                breakdown.under_treatment
            ),
            Sick: firstValidNumber(
                record.sickQuantity,
                record.sick_quantity,
                breakdown.sick
            ),
        };
    }

    // Aggregate imports also keep the health breakdown inside the notes.
    const notes = String(
        record.healthNotes ?? record.health_notes ?? ""
    );

    if (/health\s*breakdown\s*:/i.test(notes)) {
        const readFromNotes = (pattern) => {
            const match = notes.match(pattern);
            return match ? Number(match[1]) || 0 : 0;
        };

        return {
            Healthy: readFromNotes(/(\d+)\s*healthy/i),
            "At Risk": readFromNotes(/(\d+)\s*at\s*risk/i),
            "Under Treatment": readFromNotes(
                /(\d+)\s*under\s*treatment/i
            ),
            Sick: readFromNotes(/(\d+)\s*sick/i),
        };
    }

    const status = normalizeHealthStatus(
        record.healthStatus ?? record.health_status ?? record.status
    );

    if (!status) {
        return null;
    }

    return {
        Healthy: status === "Healthy" ? getLivestockCount(record) : 0,
        "At Risk": status === "At Risk" ? getLivestockCount(record) : 0,
        "Under Treatment":
            status === "Under Treatment" ? getLivestockCount(record) : 0,
        Sick: status === "Sick" ? getLivestockCount(record) : 0,
    };
}

function normalizeDate(value) {
    if (!value) {
        return null;
    }

    const date = new Date(value);

    return Number.isNaN(date.getTime()) ? null : date;
}

function inSelectedRange(value, selectedFilter) {
    const date = normalizeDate(value);

    if (!date) {
        return true;
    }

    const today = new Date();
    const startToday = new Date(
        today.getFullYear(),
        today.getMonth(),
        today.getDate()
    );

    const target = new Date(
        date.getFullYear(),
        date.getMonth(),
        date.getDate()
    );

    if (selectedFilter.includes(" to ")) {
        const [fromValue, toValue] = selectedFilter.split(" to ");
        const from = new Date(`${fromValue}T00:00:00`);
        const to = new Date(`${toValue}T23:59:59`);

        return target >= from && target <= to;
    }

    const start = new Date(startToday);
    const end = new Date(startToday);

    switch (selectedFilter) {
        case "Today":
            break;
        case "This Week": {
            const day = start.getDay();
            const diff = day === 0 ? 6 : day - 1;
            start.setDate(start.getDate() - diff);
            end.setDate(start.getDate() + 6);
            break;
        }
        case "Last Week": {
            const day = start.getDay();
            const diff = day === 0 ? 6 : day - 1;
            start.setDate(start.getDate() - diff - 7);
            end.setTime(start.getTime());
            end.setDate(end.getDate() + 6);
            break;
        }
        case "Last 7 Days":
            start.setDate(start.getDate() - 6);
            break;
        case "Last 30 Days":
            start.setDate(start.getDate() - 29);
            break;
        case "Last Month":
            start.setFullYear(today.getFullYear(), today.getMonth() - 1, 1);
            end.setFullYear(today.getFullYear(), today.getMonth(), 0);
            break;
        case "This Year":
            start.setFullYear(today.getFullYear(), 0, 1);
            end.setFullYear(today.getFullYear(), 11, 31);
            break;
        case "This Month":
        default:
            start.setFullYear(today.getFullYear(), today.getMonth(), 1);
            end.setFullYear(today.getFullYear(), today.getMonth() + 1, 0);
            break;
    }

    return target >= start && target <= end;
}

function getDashboardChartFilter(period) {
    if (typeof period === "string" && period.includes(" to ")) {
        return period;
    }

    if (period === "today") {
        return "Today";
    }

    if (period === "week") {
        return "This Week";
    }

    if (period === "year") {
        return "This Year";
    }

    return "This Month";
}

function ChartFilter({
    idPrefix,
    selectedFilter,
    setSelectedFilter,
}) {
    const [isOpen, setIsOpen] = useState(false);
    const [showCustomRange, setShowCustomRange] = useState(false);
    const [fromDate, setFromDate] = useState("");
    const [toDate, setToDate] = useState("");
    const filterRef = useRef(null);

    useEffect(() => {
        const handleOutsideClick = (event) => {
            if (
                filterRef.current &&
                !filterRef.current.contains(event.target)
            ) {
                setIsOpen(false);
            }
        };

        document.addEventListener("mousedown", handleOutsideClick);

        return () => {
            document.removeEventListener(
                "mousedown",
                handleOutsideClick
            );
        };
    }, []);

    const handleFilterSelect = (option) => {
        setSelectedFilter(option);
        setShowCustomRange(false);
        setIsOpen(false);
    };

    const handleCustomRangeSubmit = (event) => {
        event.preventDefault();

        if (!fromDate || !toDate) {
            notify("Please select the From and To dates.");
            return;
        }

        if (fromDate > toDate) {
            notify("The From date cannot be later than the To date.");
            return;
        }

        setSelectedFilter(`${fromDate} to ${toDate}`);
        setShowCustomRange(false);
        setIsOpen(false);
    };

    return (
        <div className="chart-filter" ref={filterRef}>
            <button
                type="button"
                className="month-filter"
                onClick={() => setIsOpen((currentValue) => !currentValue)}
            >
                <span className="filter-text">{selectedFilter}</span>
                <span className="material-symbols-outlined">
                    expand_more
                </span>
            </button>

            <div
                className={
                    isOpen
                        ? "filter-dropdown show"
                        : "filter-dropdown"
                }
            >
                {filterOptions.map((option) => (
                    <button
                        type="button"
                        key={option}
                        className={
                            selectedFilter === option
                                ? "filter-item active"
                                : "filter-item"
                        }
                        onClick={() => handleFilterSelect(option)}
                    >
                        {option}
                    </button>
                ))}

                <button
                    type="button"
                    className="filter-item custom-option"
                    onClick={() =>
                        setShowCustomRange(
                            (currentValue) => !currentValue
                        )
                    }
                >
                    Custom Range
                </button>

                {showCustomRange && (
                    <form
                        className="custom-range"
                        onSubmit={handleCustomRangeSubmit}
                    >
                        <label htmlFor={`${idPrefix}-from`}>
                            From
                        </label>
                        <input
                            id={`${idPrefix}-from`}
                            type="date"
                            value={fromDate}
                            onChange={(event) =>
                                setFromDate(event.target.value)
                            }
                        />

                        <label htmlFor={`${idPrefix}-to`}>To</label>
                        <input
                            id={`${idPrefix}-to`}
                            type="date"
                            value={toDate}
                            onChange={(event) =>
                                setToDate(event.target.value)
                            }
                        />

                        <button type="submit" className="apply-btn">
                            Apply
                        </button>
                    </form>
                )}
            </div>
        </div>
    );
}

function DashboardCharts({
    period = "month",
    crops = [],
    livestock = [],
}) {
    const [cropFilter, setCropFilter] = useState("This Month");
    const [livestockFilter, setLivestockFilter] =
        useState("This Month");

    const dashboardFilter =
        getDashboardChartFilter(period);

    // Global period changes update both chart filters together.
    useEffect(() => {
        setCropFilter(dashboardFilter);
        setLivestockFilter(dashboardFilter);
    }, [dashboardFilter]);


    const cropChart = useMemo(() => {
        const records = [];

        crops.forEach((crop) => {
            const history = crop.growthRecords || [];

            if (history.length > 0) {
                history.forEach((record) => {
                    if (
                        inSelectedRange(
                            record.updateDate || record.createdAt,
                            cropFilter
                        )
                    ) {
                        records.push({
                            label: `${crop.name} ${record.updateDate || ""}`.trim(),
                            value: Number(record.growth) || 0,
                            date:
                                record.updateDate ||
                                record.createdAt ||
                                "",
                        });
                    }
                });
            } else if (
                inSelectedRange(
                    crop.updatedAt || crop.createdAt || crop.plantingDate,
                    cropFilter
                )
            ) {
                records.push({
                    label: crop.name || crop.cropCode || "Crop",
                    value: Number(crop.growth) || 0,
                    date:
                        crop.updatedAt ||
                        crop.createdAt ||
                        crop.plantingDate ||
                        "",
                });
            }
        });

        records.sort((a, b) =>
            String(a.date).localeCompare(String(b.date))
        );

        const limited = records.slice(-12);

        return {
            data: {
                labels: limited.map((record) => record.label),
                datasets: [
                    {
                        label: "Growth %",
                        data: limited.map((record) => record.value),
                        borderColor: "#2e7d32",
                        backgroundColor: "transparent",
                    },
                ],
            },
            empty: limited.length === 0,
        };
    }, [cropFilter, crops]);

    const livestockChart = useMemo(() => {
        const records = livestock
            .filter((record) =>
                inSelectedRange(
                    record.updatedAt ||
                        record.createdAt ||
                        record.dateAcquired,
                    livestockFilter
                )
            )
            .slice(0, 12)
            .reverse();

        const maxWeight = Math.max(
            100,
            ...records.map((record) => Number(record.weight) || 0)
        );

        const roundedMax = Math.ceil(maxWeight / 20) * 20;

        return {
            data: {
                labels: records.map(
                    (record) =>
                        record.recordName ||
                        record.animalId ||
                        "Livestock"
                ),
                datasets: [
                    {
                        label: "Weight (kg)",
                        data: records.map(
                            (record) => Number(record.weight) || 0
                        ),
                        borderColor: "#8e24aa",
                        backgroundColor: "transparent",
                    },
                ],
            },
            options: makeLineOptions(
                roundedMax,
                Math.max(10, Math.round(roundedMax / 5))
            ),
            empty: records.length === 0,
        };
    }, [livestock, livestockFilter]);

    const cropStatus = useMemo(() => {
        const order = [
            "Planted",
            "Growing",
            "Ready for Harvest",
            "Harvested",
            "Failed",
        ];

        // Status distribution always represents the crops currently in the system.
        const values = order
            .map((status, index) => ({
                label: status,
                value: crops.filter(
                    (crop) => crop.status === status
                ).length,
                color: chartColors[index % chartColors.length],
            }))
            .filter((item) => item.value > 0);

        return values.length > 0
            ? values
            : [
                  {
                      label: "No crop records",
                      value: 1,
                      color: "#e0e0e0",
                  },
              ];
    }, [crops]);

    const livestockHealth = useMemo(() => {
        const order = [
            "Healthy",
            "At Risk",
            "Under Treatment",
            "Sick",
        ];
        const colors = [
            "#43a047",
            "#ffa726",
            "#42a5f5",
            "#ef5350",
        ];

        // Use each batch's real health breakdown instead of only its overall status.
        const totals = livestock.reduce((result, record) => {
            const breakdown = readHealthBreakdown(record);

            if (!breakdown) {
                return result;
            }

            order.forEach((status) => {
                result[status] =
                    (result[status] || 0) +
                    (Number(breakdown[status]) || 0);
            });

            return result;
        }, {});

        // Keep every health category visible, even when its count is zero.
        return order.map((status, index) => ({
            label: status,
            value: totals[status] || 0,
            color: colors[index],
        }));
    }, [livestock]);

    const cropStatusData = {
        labels: cropStatus.map((item) => item.label),
        datasets: [
            {
                data: cropStatus.map((item) => item.value),
                backgroundColor: cropStatus.map((item) => item.color),
                borderWidth: 0,
            },
        ],
    };

    const livestockHealthTotal = livestockHealth.reduce(
        (total, item) => total + item.value,
        0
    );

    const livestockHealthData = {
        labels: livestockHealth.map((item) => item.label),
        datasets: [
            {
                data: livestockHealth.map((item) => item.value),
                backgroundColor: livestockHealth.map(
                    (item) => item.color
                ),
                borderWidth: 0,
            },
        ],
    };

    return (
        <>
            <article className="dashboard-card crop-growth">
                <div className="card-title">
                    <h3>Crop Growth Overview</h3>

                    <ChartFilter
                        idPrefix="crop-filter"
                        selectedFilter={cropFilter}
                        setSelectedFilter={setCropFilter}
                    />
                </div>

                <div className="chart-area">
                    {cropChart.empty ? (
                        <div className="empty-state">
                            No crop growth records for this period.
                        </div>
                    ) : (
                        <Line
                            data={cropChart.data}
                            options={makeLineOptions(100, 20)}
                        />
                    )}
                </div>
            </article>

            <article className="dashboard-card crop-status">
                <div className="card-title">
                    <h3>Crop Status Distribution</h3>
                </div>

                <div className="pie-layout">
                    <div className="pie-chart">
                        <Pie
                            data={cropStatusData}
                            options={pieChartOptions}
                        />
                    </div>

                    <div className="pie-legend">
                        {cropStatus.map((item) => (
                            <div className="legend-row" key={item.label}>
                                <span
                                    className="legend-box"
                                    style={{
                                        backgroundColor: item.color,
                                    }}
                                />
                                <span>{item.label}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </article>

            <article className="dashboard-card livestock-health">
                <div className="card-title">
                    <h3>Livestock Health Status</h3>
                </div>

                <div className="pie-layout">
                    <div className="pie-chart">
                        {livestockHealthTotal > 0 ? (
                            <Doughnut
                                data={livestockHealthData}
                                options={doughnutChartOptions}
                            />
                        ) : (
                            <div className="empty-state">
                                No livestock health records.
                            </div>
                        )}
                    </div>

                    <div className="pie-legend">
                        {livestockHealth.map((item) => (
                            <div className="legend-row" key={item.label}>
                                <span
                                    className="legend-box"
                                    style={{
                                        backgroundColor: item.color,
                                    }}
                                />
                                <span>
                                    {item.label} ({item.value})
                                </span>
                            </div>
                        ))}
                    </div>
                </div>
            </article>

            <article className="dashboard-card livestock-growth">
                <div className="card-title">
                    <h3>Livestock Growth Overview</h3>

                    <ChartFilter
                        idPrefix="livestock-filter"
                        selectedFilter={livestockFilter}
                        setSelectedFilter={setLivestockFilter}
                    />
                </div>

                <div className="chart-area">
                    {livestockChart.empty ? (
                        <div className="empty-state">
                            No livestock records for this period.
                        </div>
                    ) : (
                        <Line
                            data={livestockChart.data}
                            options={livestockChart.options}
                        />
                    )}
                </div>
            </article>
        </>
    );
}

export default DashboardCharts;
