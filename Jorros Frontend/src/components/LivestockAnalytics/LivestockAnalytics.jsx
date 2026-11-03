"use client";

import {
    useEffect,
    useMemo,
    useState,
    memo,
} from "react";

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

import "./LivestockAnalytics.css";

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

const animalTypeColors = {
    Pig: "#43a047",
    Chicken: "#f59e0b",
    Goat: "#8b5cf6",
    Cattle: "#3b82f6",
    Duck: "#06b6d4",
    Other: "#9ca3af",
};

const estimatedFeedPricePerKg = {
    Pig: 30,
    Chicken: 32,
    Goat: 20,
    Cattle: 18,
    Duck: 28,
    Other: 25,
};

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
    return Number(value).toLocaleString(
        "en-PH",
        {
            style: "currency",
            currency: "PHP",
            maximumFractionDigits: 0,
        }
    );
}

function getStatusClass(status = "") {
    return status
        .toLowerCase()
        .replaceAll(" ", "-");
}

function getAgeGroup(dateOfBirth) {
    const birthDate =
        parseDate(dateOfBirth);

    if (!birthDate) {
        return "Unknown";
    }

    const today = new Date();

    let totalMonths =
        (today.getFullYear() -
            birthDate.getFullYear()) *
            12 +
        today.getMonth() -
        birthDate.getMonth();

    if (
        today.getDate() <
        birthDate.getDate()
    ) {
        totalMonths -= 1;
    }

    if (totalMonths <= 3) {
        return "Newborn";
    }

    if (totalMonths <= 12) {
        return "Young";
    }

    if (totalMonths <= 24) {
        return "Growing";
    }

    return "Mature";
}

function getPreviousMonthLabels() {
    const labels = [];
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

        labels.push(
            date.toLocaleDateString(
                "en-US",
                {
                    month: "short",
                }
            )
        );
    }

    return labels;
}

function LivestockAnalytics({
    livestock,
}) {
    const [
        recordModal,
        setRecordModal,
    ] = useState(null);

    const [
        showFarmTip,
        setShowFarmTip,
    ] = useState(true);

    useEffect(() => {
        if (recordModal) {
            document.body.style.overflow =
                "hidden";
        } else {
            document.body.style.overflow =
                "";
        }

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [recordModal]);

    const livestockByType =
        useMemo(() => {
            const groupedTypes =
                new Map();

            livestock.forEach(
                (animal) => {
                    const currentValue =
                        groupedTypes.get(
                            animal.type
                        ) || 0;

                    groupedTypes.set(
                        animal.type,
                        currentValue +
                            Number(
                                animal.quantity
                            )
                    );
                }
            );

            return Array.from(
                groupedTypes.entries()
            ).map(
                ([type, quantity]) => ({
                    type,
                    quantity,
                })
            );
        }, [livestock]);

    const ageDistribution =
        useMemo(() => {
            const groups = {
                Newborn: 0,
                Young: 0,
                Growing: 0,
                Mature: 0,
                Unknown: 0,
            };

            livestock.forEach(
                (animal) => {
                    const ageGroup =
                        getAgeGroup(
                            animal.dateOfBirth
                        );

                    groups[ageGroup] +=
                        Number(
                            animal.quantity
                        );
                }
            );

            return groups;
        }, [livestock]);

    const feedConsumptionByType =
        useMemo(() => {
            const groupedConsumption =
                new Map();

            livestock.forEach(
                (animal) => {
                    const dailyAmount =
                        Number(
                            animal
                                .feedingSchedule
                                ?.dailyAmountKg
                        ) || 0;

                    const currentValue =
                        groupedConsumption.get(
                            animal.type
                        ) || 0;

                    groupedConsumption.set(
                        animal.type,
                        currentValue +
                            dailyAmount * Number(animal.quantity || 0)
                    );
                }
            );

            return Array.from(
                groupedConsumption.entries()
            ).map(
                ([type, amount]) => ({
                    type,
                    amount,
                })
            );
        }, [livestock]);

    const currentMonthlyFeedCost =
        useMemo(() => {
            return livestock.reduce(
                (total, animal) => {
                    const dailyAmount =
                        Number(
                            animal
                                .feedingSchedule
                                ?.dailyAmountKg
                        ) || 0;

                    const feedPrice =
                        estimatedFeedPricePerKg[
                            animal.type
                        ] ||
                        estimatedFeedPricePerKg.Other;

                    return (
                        total +
                        dailyAmount *
                            Number(animal.quantity || 0) *
                            30 *
                            feedPrice
                    );
                },
                0
            );
        }, [livestock]);

    const monthlyFeedCostData =
        useMemo(() => {
            const trendMultipliers = [
                0.86,
                0.89,
                0.92,
                0.95,
                0.98,
                1,
            ];

            return trendMultipliers.map(
                (multiplier) =>
                    Math.round(
                        currentMonthlyFeedCost *
                            multiplier
                    )
            );
        }, [currentMonthlyFeedCost]);

    const vaccinationRecords =
        useMemo(() => {
            return livestock
                .flatMap((animal) =>
                    (
                        animal.vaccinationRecords ||
                        []
                    ).map((record) => ({
                        ...record,

                        animalId:
                            animal.animalId,

                        recordName:
                            animal.recordName,

                        type:
                            animal.type,

                        breed:
                            animal.breed,

                        quantity:
                            animal.quantity,
                    }))
                )
                .sort((first, second) =>
                    (
                        second.dateAdministered ||
                        ""
                    ).localeCompare(
                        first.dateAdministered ||
                            ""
                    )
                );
        }, [livestock]);

    const feedingRecords =
        useMemo(() => {
            return [...livestock].sort(
                (first, second) =>
                    first.animalId.localeCompare(
                        second.animalId
                    )
            );
        }, [livestock]);

    const livestockTypeChartData =
        useMemo(() => {
            return {
                labels:
                    livestockByType.map(
                        (item) =>
                            item.type
                    ),

                datasets: [
                    {
                        label:
                            "Animal Count",

                        data:
                            livestockByType.map(
                                (item) =>
                                    item.quantity
                            ),

                        backgroundColor:
                            livestockByType.map(
                                (item) =>
                                    animalTypeColors[
                                        item.type
                                    ] ||
                                    animalTypeColors.Other
                            ),

                        borderWidth: 0,
                    },
                ],
            };
        }, [livestockByType]);

    const ageChartData =
        useMemo(() => {
            return {
                labels: [
                    "Newborn",
                    "Young",
                    "Growing",
                    "Mature",
                ],

                datasets: [
                    {
                        label:
                            "Animal Count",

                        data: [
                            ageDistribution.Newborn,
                            ageDistribution.Young,
                            ageDistribution.Growing,
                            ageDistribution.Mature,
                        ],

                        backgroundColor: [
                            "#81c784",
                            "#42a5f5",
                            "#ffb74d",
                            "#8e24aa",
                        ],

                        borderRadius: 7,
                    },
                ],
            };
        }, [ageDistribution]);

    const feedChartData =
        useMemo(() => {
            return {
                labels:
                    feedConsumptionByType.map(
                        (item) =>
                            item.type
                    ),

                datasets: [
                    {
                        label:
                            "Daily Feed Consumption",

                        data:
                            feedConsumptionByType.map(
                                (item) =>
                                    item.amount
                            ),

                        backgroundColor:
                            "#43a047",

                        borderRadius: 7,
                    },
                ],
            };
        }, [feedConsumptionByType]);

    const feedCostChartData =
        useMemo(() => {
            return {
                labels:
                    getPreviousMonthLabels(),

                datasets: [
                    {
                        label:
                            "Estimated Feed Cost",

                        data:
                            monthlyFeedCostData,

                        borderColor:
                            "#2e7d32",

                        backgroundColor:
                            "rgba(46, 125, 50, 0.14)",

                        pointBackgroundColor:
                            "#2e7d32",

                        pointRadius: 4,

                        borderWidth: 3,

                        fill: true,

                        tension: 0.35,
                    },
                ],
            };
        }, [monthlyFeedCostData]);

    const doughnutOptions = {
        responsive: true,

        maintainAspectRatio: false,

        cutout: "63%",

        plugins: {
            legend: {
                position: "bottom",

                labels: {
                    usePointStyle: true,

                    padding: 16,

                    font: {
                        family: "Inter",
                        size: 11,
                    },
                },
            },

            tooltip: {
                callbacks: {
                    label(context) {
                        return ` ${context.label}: ${context.parsed}`;
                    },
                },
            },
        },
    };

    const barOptions = {
        responsive: true,

        maintainAspectRatio: false,

        plugins: {
            legend: {
                display: false,
            },
        },

        scales: {
            x: {
                grid: {
                    display: false,
                },

                ticks: {
                    font: {
                        family: "Inter",
                        size: 11,
                    },
                },
            },

            y: {
                beginAtZero: true,

                ticks: {
                    precision: 0,

                    font: {
                        family: "Inter",
                        size: 10,
                    },
                },

                grid: {
                    color:
                        "rgba(0, 0, 0, 0.06)",
                },
            },
        },
    };

    const feedOptions = {
        ...barOptions,

        scales: {
            ...barOptions.scales,

            y: {
                ...barOptions.scales.y,

                title: {
                    display: true,
                    text: "kg per day",
                },
            },
        },
    };

    const lineOptions = {
        responsive: true,

        maintainAspectRatio: false,

        plugins: {
            legend: {
                display: false,
            },

            tooltip: {
                callbacks: {
                    label(context) {
                        return formatCurrency(
                            context.parsed.y
                        );
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
        },
    };

    return (
        <section className="livestock-insights">
            <div className="livestock-insights-heading">
                <div>
                    <h2>
                        Livestock Analytics
                    </h2>

                    <p>
                        Review livestock population,
                        age, feed consumption, and
                        estimated feed expenses.
                    </p>
                </div>

                <span>
                    Based on the current livestock
                    records
                </span>
            </div>

            <div className="livestock-analytics-grid">
                <article className="livestock-chart-card">
                    <div className="livestock-chart-header">
                        <div>
                            <h3>
                                Livestock by Type
                            </h3>

                            <p>
                                Total animal count by
                                livestock category.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            pets
                        </span>
                    </div>

                    <div className="livestock-chart-area doughnut-chart-area">
                        <Doughnut
                            data={
                                livestockTypeChartData
                            }
                            options={
                                doughnutOptions
                            }
                        />
                    </div>
                </article>

                <article className="livestock-chart-card">
                    <div className="livestock-chart-header">
                        <div>
                            <h3>
                                Age Group Distribution
                            </h3>

                            <p>
                                Distribution based on
                                recorded birth dates.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            timeline
                        </span>
                    </div>

                    <div className="livestock-chart-area">
                        <Bar
                            data={ageChartData}
                            options={barOptions}
                        />
                    </div>
                </article>

                <article className="livestock-chart-card">
                    <div className="livestock-chart-header">
                        <div>
                            <h3>
                                Feed Consumption
                            </h3>

                            <p>
                                Recorded daily feed usage
                                by animal type.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            nutrition
                        </span>
                    </div>

                    <div className="livestock-chart-area">
                        <Bar
                            data={feedChartData}
                            options={feedOptions}
                        />
                    </div>
                </article>

                <article className="livestock-chart-card">
                    <div className="livestock-chart-header">
                        <div>
                            <h3>
                                Monthly Feed Cost
                            </h3>

                            <p>
                                Estimated from daily feed
                                consumption records.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            payments
                        </span>
                    </div>

                    <div className="livestock-chart-area">
                        <Line
                            data={
                                feedCostChartData
                            }
                            options={lineOptions}
                        />
                    </div>

                    <div className="feed-cost-summary">
                        <small>
                            Current estimated monthly
                            cost
                        </small>

                        <strong>
                            {formatCurrency(
                                currentMonthlyFeedCost
                            )}
                        </strong>
                    </div>
                </article>
            </div>

            <div className="livestock-record-grid">
                <article className="livestock-record-card">
                    <div className="livestock-record-header">
                        <div>
                            <h3>
                                Vaccination Records
                            </h3>

                            <p>
                                Recent livestock
                                vaccinations.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            vaccines
                        </span>
                    </div>

                    <div className="livestock-record-preview-list">
                        {vaccinationRecords.length >
                        0 ? (
                            vaccinationRecords
                                .slice(0, 3)
                                .map((record) => (
                                    <div
                                        className="livestock-record-preview"
                                        key={`${record.animalId}-${record.id}`}
                                    >
                                        <div>
                                            <strong>
                                                {
                                                    record.animalId
                                                }
                                            </strong>

                                            <p>
                                                {
                                                    record.type
                                                }{" "}
                                                (
                                                {
                                                    record.breed
                                                }
                                                )
                                            </p>
                                        </div>

                                        <div className="livestock-record-preview-right">
                                            <strong>
                                                {
                                                    record.vaccine
                                                }
                                            </strong>

                                            <small>
                                                {formatDate(
                                                    record.dateAdministered
                                                )}
                                            </small>
                                        </div>
                                    </div>
                                ))
                        ) : (
                            <div className="livestock-record-empty">
                                No vaccination records
                                available.
                            </div>
                        )}
                    </div>

                    <button
                        type="button"
                        className="livestock-view-all-button"
                        onClick={() =>
                            setRecordModal(
                                "vaccination"
                            )
                        }
                    >
                        View All
                        <span className="material-symbols-outlined">
                            arrow_forward
                        </span>
                    </button>
                </article>

                <article className="livestock-record-card">
                    <div className="livestock-record-header">
                        <div>
                            <h3>
                                Feeding Schedule
                            </h3>

                            <p>
                                Current feeding plans and
                                consumption.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            nutrition
                        </span>
                    </div>

                    <div className="livestock-record-preview-list">
                        {feedingRecords
                            .slice(0, 3)
                            .map((animal) => (
                                <div
                                    className="livestock-record-preview"
                                    key={
                                        animal.id
                                    }
                                >
                                    <div>
                                        <strong>
                                            {
                                                animal.animalId
                                            }
                                        </strong>

                                        <p>
                                            {
                                                animal.type
                                            }{" "}
                                            (
                                            {
                                                animal.breed
                                            }
                                            )
                                        </p>
                                    </div>

                                    <div className="livestock-record-preview-right">
                                        <strong>
                                            {
                                                animal
                                                    .feedingSchedule
                                                    .feedType
                                            }
                                        </strong>

                                        <small>
                                            {
                                                animal
                                                    .feedingSchedule
                                                    .dailyAmountKg
                                            }{" "}
                                            kg/day
                                        </small>
                                    </div>
                                </div>
                            ))}
                    </div>

                    <button
                        type="button"
                        className="livestock-view-all-button"
                        onClick={() =>
                            setRecordModal(
                                "feeding"
                            )
                        }
                    >
                        View All
                        <span className="material-symbols-outlined">
                            arrow_forward
                        </span>
                    </button>
                </article>
            </div>

            {showFarmTip && (
                <div className="livestock-farm-tip">
                    <div>
                        <span className="material-symbols-outlined">
                            pets
                        </span>

                        <p>
                            <strong>
                                Farm Tip:
                            </strong>{" "}
                            Keep livestock vaccination
                            and feeding records updated
                            for better farm monitoring.
                        </p>
                    </div>

                    <button
                        type="button"
                        aria-label="Close livestock farm tip"
                        onClick={() =>
                            setShowFarmTip(false)
                        }
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </div>
            )}

            {recordModal ===
                "vaccination" && (
                <div
                    className="livestock-record-modal-overlay"
                    onMouseDown={() =>
                        setRecordModal(null)
                    }
                >
                    <div
                        className="livestock-record-modal"
                        onMouseDown={(
                            event
                        ) =>
                            event.stopPropagation()
                        }
                    >
                        <header className="livestock-record-modal-header">
                            <div>
                                <h2>
                                    Vaccination Records
                                </h2>

                                <p>
                                    View all recorded
                                    livestock
                                    vaccinations and
                                    upcoming schedules.
                                </p>
                            </div>

                            <button
                                type="button"
                                onClick={() =>
                                    setRecordModal(
                                        null
                                    )
                                }
                                aria-label="Close vaccination records"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </header>

                        <div className="livestock-record-modal-body">
                            <div className="livestock-record-table-wrapper">
                                <table className="livestock-record-table">
                                    <thead>
                                        <tr>
                                            <th>
                                                Animal ID
                                            </th>

                                            <th>
                                                Record
                                            </th>

                                            <th>
                                                Type /
                                                Breed
                                            </th>

                                            <th>
                                                Vaccine
                                            </th>

                                            <th>
                                                Administered
                                            </th>

                                            <th>
                                                Next Due
                                            </th>

                                            <th>
                                                Status
                                            </th>

                                            <th>
                                                Administered
                                                By
                                            </th>

                                            <th>
                                                Notes
                                            </th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {vaccinationRecords.length >
                                        0 ? (
                                            vaccinationRecords.map(
                                                (
                                                    record
                                                ) => (
                                                    <tr
                                                        key={`${record.animalId}-${record.id}`}
                                                    >
                                                        <td>
                                                            <strong>
                                                                {
                                                                    record.animalId
                                                                }
                                                            </strong>
                                                        </td>

                                                        <td>
                                                            {
                                                                record.recordName
                                                            }
                                                        </td>

                                                        <td>
                                                            {
                                                                record.type
                                                            }

                                                            <small>
                                                                {
                                                                    record.breed
                                                                }
                                                            </small>
                                                        </td>

                                                        <td>
                                                            {
                                                                record.vaccine
                                                            }
                                                        </td>

                                                        <td>
                                                            {formatDate(
                                                                record.dateAdministered
                                                            )}
                                                        </td>

                                                        <td>
                                                            {formatDate(
                                                                record.nextDue
                                                            )}
                                                        </td>

                                                        <td>
                                                            <span
                                                                className={`livestock-record-status ${getStatusClass(
                                                                    record.status
                                                                )}`}
                                                            >
                                                                {
                                                                    record.status
                                                                }
                                                            </span>
                                                        </td>

                                                        <td>
                                                            {
                                                                record.administeredBy
                                                            }
                                                        </td>

                                                        <td>
                                                            {
                                                                record.notes
                                                            }
                                                        </td>
                                                    </tr>
                                                )
                                            )
                                        ) : (
                                            <tr>
                                                <td
                                                    colSpan="9"
                                                    className="livestock-record-table-empty"
                                                >
                                                    No
                                                    vaccination
                                                    records
                                                    available.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {recordModal ===
                "feeding" && (
                <div
                    className="livestock-record-modal-overlay"
                    onMouseDown={() =>
                        setRecordModal(null)
                    }
                >
                    <div
                        className="livestock-record-modal"
                        onMouseDown={(
                            event
                        ) =>
                            event.stopPropagation()
                        }
                    >
                        <header className="livestock-record-modal-header">
                            <div>
                                <h2>
                                    Feeding Schedule
                                </h2>

                                <p>
                                    View all livestock
                                    feeding schedules,
                                    feed types, and daily
                                    consumption.
                                </p>
                            </div>

                            <button
                                type="button"
                                onClick={() =>
                                    setRecordModal(
                                        null
                                    )
                                }
                                aria-label="Close feeding schedules"
                            >
                                <span className="material-symbols-outlined">
                                    close
                                </span>
                            </button>
                        </header>

                        <div className="livestock-record-modal-body">
                            <div className="livestock-record-table-wrapper">
                                <table className="livestock-record-table feeding-table">
                                    <thead>
                                        <tr>
                                            <th>
                                                Animal ID
                                            </th>

                                            <th>
                                                Record
                                            </th>

                                            <th>
                                                Type /
                                                Breed
                                            </th>

                                            <th>
                                                Animal
                                                Count
                                            </th>

                                            <th>
                                                Feeding
                                                Schedule
                                            </th>

                                            <th>
                                                Feed Type
                                            </th>

                                            <th>
                                                Daily
                                                Consumption
                                            </th>

                                            <th>
                                                Feeding
                                                Notes
                                            </th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {feedingRecords.map(
                                            (
                                                animal
                                            ) => (
                                                <tr
                                                    key={
                                                        animal.id
                                                    }
                                                >
                                                    <td>
                                                        <strong>
                                                            {
                                                                animal.animalId
                                                            }
                                                        </strong>
                                                    </td>

                                                    <td>
                                                        {
                                                            animal.recordName
                                                        }
                                                    </td>

                                                    <td>
                                                        {
                                                            animal.type
                                                        }

                                                        <small>
                                                            {
                                                                animal.breed
                                                            }
                                                        </small>
                                                    </td>

                                                    <td>
                                                        {
                                                            animal.quantity
                                                        }
                                                    </td>

                                                    <td>
                                                        {
                                                            animal
                                                                .feedingSchedule
                                                                .times
                                                        }
                                                    </td>

                                                    <td>
                                                        {
                                                            animal
                                                                .feedingSchedule
                                                                .feedType
                                                        }
                                                    </td>

                                                    <td>
                                                        {
                                                            animal
                                                                .feedingSchedule
                                                                .dailyAmountKg
                                                        }{" "}
                                                        kg/day
                                                    </td>

                                                    <td>
                                                        {
                                                            animal
                                                                .feedingSchedule
                                                                .notes
                                                        }
                                                    </td>
                                                </tr>
                                            )
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </section>
    );
}

export default memo(LivestockAnalytics);
