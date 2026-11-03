"use client";

import { useMemo } from "react";

import "./CropAnalytics.css";

function parseDateKey(dateValue) {
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
    const date = parseDateKey(
        dateValue
    );

    if (!date) {
        return "—";
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

function formatMonth(monthKey) {
    const [year, month] =
        monthKey.split("-").map(Number);

    return new Date(
        year,
        month - 1,
        1
    ).toLocaleDateString("en-US", {
        month: "short",
        year: "numeric",
    });
}

function getQualityClass(quality) {
    return quality
        .toLowerCase()
        .replaceAll(" ", "-");
}

function CropAnalytics({
    crops,
    yieldRecords,
}) {
    const monthlyPrediction =
        useMemo(() => {
            const groupedMonths =
                new Map();

            crops.forEach((crop) => {
                if (
                    !crop.estimatedHarvest
                ) {
                    return;
                }

                const monthKey =
                    crop.estimatedHarvest.slice(
                        0,
                        7
                    );

                const current =
                    groupedMonths.get(
                        monthKey
                    ) || {
                        monthKey,
                        cropCount: 0,
                        area: 0,
                    };

                current.cropCount += 1;
                current.area += Number(
                    crop.area
                );

                groupedMonths.set(
                    monthKey,
                    current
                );
            });

            return Array.from(
                groupedMonths.values()
            ).sort((first, second) =>
                first.monthKey.localeCompare(
                    second.monthKey
                )
            );
        }, [crops]);

    const yieldByCrop = useMemo(() => {
        const groupedYield =
            new Map();

        yieldRecords.forEach((record) => {
            const current =
                groupedYield.get(
                    record.cropName
                ) || {
                    cropName:
                        record.cropName,
                    quantityKg: 0,
                    records: 0,
                };

            current.quantityKg +=
                Number(
                    record.quantityKg
                );

            current.records += 1;

            groupedYield.set(
                record.cropName,
                current
            );
        });

        return Array.from(
            groupedYield.values()
        ).sort(
            (first, second) =>
                second.quantityKg -
                first.quantityKg
        );
    }, [yieldRecords]);

    const productivityStats =
        useMemo(() => {
            const totalYield =
                yieldRecords.reduce(
                    (total, record) =>
                        total +
                        Number(
                            record.quantityKg
                        ),
                    0
                );

            const totalArea =
                crops.reduce(
                    (total, crop) =>
                        total +
                        Number(crop.area),
                    0
                );

            const averageGrowth =
                crops.length > 0
                    ? crops.reduce(
                          (
                              total,
                              crop
                          ) =>
                              total +
                              Number(
                                  crop.growth
                              ),
                          0
                      ) / crops.length
                    : 0;

            const survivalRates =
                crops
                    .map((crop) => crop.survivalRate)
                    .filter(
                        (value) =>
                            value !== null &&
                            value !== undefined &&
                            Number.isFinite(Number(value))
                    );

            const averageSurvival =
                survivalRates.length > 0
                    ? survivalRates.reduce(
                          (total, value) =>
                              total + Number(value),
                          0
                      ) / survivalRates.length
                    : null;

            const topYieldCrop =
                yieldByCrop[0];

            return {
                totalYield,
                totalArea,
                averageGrowth,
                averageSurvival,
                topYieldCrop:
                    topYieldCrop
                        ? topYieldCrop.cropName
                        : "No data",
                yieldPerHectare:
                    totalArea > 0
                        ? totalYield /
                          totalArea
                        : 0,
            };
        }, [
            crops,
            yieldRecords,
            yieldByCrop,
        ]);

    const maxPredictionArea =
        Math.max(
            1,
            ...monthlyPrediction.map(
                (item) => item.area
            )
        );

    const maxCropYield = Math.max(
        1,
        ...yieldByCrop.map(
            (item) =>
                item.quantityKg
        )
    );

    return (
        <section className="crop-analytics-section">
            <div className="crop-analytics-heading">
                <div>
                    <h2>
                        Crop Analytics
                    </h2>

                    <p>
                        Review harvest forecasts,
                        yield performance, and crop
                        productivity.
                    </p>
                </div>

                <span>
                    Updated from current crop
                    and yield records
                </span>
            </div>

            <div className="crop-analytics-grid">
                <article className="crop-analytics-card harvest-prediction-card">
                    <div className="crop-analytics-card-header">
                        <div>
                            <h3>
                                Monthly Harvest
                                Prediction
                            </h3>

                            <p>
                                Expected harvest area
                                based on crop schedules.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            calendar_month
                        </span>
                    </div>

                    <div className="harvest-prediction-chart">
                        {monthlyPrediction.length >
                        0 ? (
                            monthlyPrediction.map(
                                (item) => (
                                    <div
                                        className="harvest-month-column"
                                        key={
                                            item.monthKey
                                        }
                                    >
                                        <div className="harvest-bar-area">
                                            <span
                                                style={{
                                                    height: `${Math.max(
                                                        10,
                                                        (item.area /
                                                            maxPredictionArea) *
                                                            100
                                                    )}%`,
                                                }}
                                            >
                                                <strong>
                                                    {item.area.toFixed(
                                                        1
                                                    )}{" "}
                                                    ha
                                                </strong>
                                            </span>
                                        </div>

                                        <small>
                                            {formatMonth(
                                                item.monthKey
                                            )}
                                        </small>

                                        <p>
                                            {
                                                item.cropCount
                                            }{" "}
                                            {item.cropCount ===
                                            1
                                                ? "crop"
                                                : "crops"}
                                        </p>
                                    </div>
                                )
                            )
                        ) : (
                            <div className="crop-analytics-empty">
                                No harvest prediction
                                data available.
                            </div>
                        )}
                    </div>
                </article>

                <article className="crop-analytics-card yield-performance-card">
                    <div className="crop-analytics-card-header">
                        <div>
                            <h3>
                                Yield Performance
                            </h3>

                            <p>
                                Total recorded yield
                                for each crop.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            monitoring
                        </span>
                    </div>

                    <div className="yield-performance-list">
                        {yieldByCrop.length >
                        0 ? (
                            yieldByCrop.map(
                                (item) => (
                                    <div
                                        className="yield-performance-item"
                                        key={
                                            item.cropName
                                        }
                                    >
                                        <div className="yield-performance-label">
                                            <strong>
                                                {
                                                    item.cropName
                                                }
                                            </strong>

                                            <span>
                                                {item.quantityKg.toLocaleString(
                                                    "en-US"
                                                )}{" "}
                                                kg
                                            </span>
                                        </div>

                                        <div className="yield-performance-track">
                                            <span
                                                style={{
                                                    width: `${Math.max(
                                                        5,
                                                        (item.quantityKg /
                                                            maxCropYield) *
                                                            100
                                                    )}%`,
                                                }}
                                            />
                                        </div>

                                        <small>
                                            {
                                                item.records
                                            }{" "}
                                            {item.records ===
                                            1
                                                ? "record"
                                                : "records"}
                                        </small>
                                    </div>
                                )
                            )
                        ) : (
                            <div className="crop-analytics-empty">
                                Add a yield record to
                                display performance.
                            </div>
                        )}
                    </div>
                </article>

                <article className="crop-analytics-card productivity-card">
                    <div className="crop-analytics-card-header">
                        <div>
                            <h3>
                                Crop Productivity
                            </h3>

                            <p>
                                Current production
                                statistics.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            analytics
                        </span>
                    </div>

                    <div className="productivity-stat-list">
                        <div className="productivity-stat-item">
                            <span className="material-symbols-outlined">
                                scale
                            </span>

                            <div>
                                <small>
                                    Total Yield
                                </small>

                                <strong>
                                    {productivityStats.totalYield.toLocaleString(
                                        "en-US"
                                    )}{" "}
                                    kg
                                </strong>
                            </div>
                        </div>

                        <div className="productivity-stat-item">
                            <span className="material-symbols-outlined">
                                landscape
                            </span>

                            <div>
                                <small>
                                    Total Area
                                </small>

                                <strong>
                                    {productivityStats.totalArea.toFixed(
                                        2
                                    )}{" "}
                                    ha
                                </strong>
                            </div>
                        </div>

                        <div className="productivity-stat-item">
                            <span className="material-symbols-outlined">
                                speed
                            </span>

                            <div>
                                <small>
                                    Average Visual Stage
                                </small>

                                <strong>
                                    {productivityStats.averageGrowth.toFixed(
                                        1
                                    )}
                                    %
                                </strong>
                            </div>
                        </div>

                        <div className="productivity-stat-item">
                            <span className="material-symbols-outlined">
                                grass
                            </span>

                            <div>
                                <small>
                                    Average Survival
                                </small>

                                <strong>
                                    {productivityStats.averageSurvival === null
                                        ? "No data"
                                        : `${productivityStats.averageSurvival.toFixed(1)}%`}
                                </strong>
                            </div>
                        </div>

                        <div className="productivity-stat-item">
                            <span className="material-symbols-outlined">
                                emoji_events
                            </span>

                            <div>
                                <small>
                                    Highest Yield
                                </small>

                                <strong>
                                    {
                                        productivityStats.topYieldCrop
                                    }
                                </strong>
                            </div>
                        </div>

                        <div className="productivity-stat-item wide">
                            <span className="material-symbols-outlined">
                                agriculture
                            </span>

                            <div>
                                <small>
                                    Overall Yield per
                                    Hectare
                                </small>

                                <strong>
                                    {productivityStats.yieldPerHectare.toLocaleString(
                                        "en-US",
                                        {
                                            maximumFractionDigits:
                                                2,
                                        }
                                    )}{" "}
                                    kg/ha
                                </strong>
                            </div>
                        </div>
                    </div>
                </article>
            </div>

            <article className="crop-yield-history-card">
                <div className="crop-yield-history-header">
                    <div>
                        <h3>
                            Recent Yield Records
                        </h3>

                        <p>
                            Latest recorded crop
                            harvests.
                        </p>
                    </div>

                    <span>
                        {yieldRecords.length}{" "}
                        {yieldRecords.length === 1
                            ? "record"
                            : "records"}
                    </span>
                </div>

                <div className="crop-yield-table-wrapper">
                    <table className="crop-yield-table">
                        <thead>
                            <tr>
                                <th>
                                    Crop
                                </th>

                                <th>
                                    Field
                                </th>

                                <th>
                                    Harvest Date
                                </th>

                                <th>
                                    Quantity
                                </th>

                                <th>
                                    Quality
                                </th>

                                <th>
                                    Harvest Type
                                </th>

                                <th>
                                    Yield / Hectare
                                </th>

                                <th>
                                    Notes
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {yieldRecords.length >
                            0 ? (
                                yieldRecords.map(
                                    (record) => (
                                        <tr
                                            key={
                                                record.id
                                            }
                                        >
                                            <td>
                                                <strong>
                                                    {
                                                        record.cropName
                                                    }
                                                </strong>
                                            </td>

                                            <td>
                                                {
                                                    record.field
                                                }
                                            </td>

                                            <td>
                                                {formatDate(
                                                    record.harvestDate
                                                )}
                                            </td>

                                            <td>
                                                {Number(
                                                    record.quantityKg
                                                ).toLocaleString(
                                                    "en-US"
                                                )}{" "}
                                                kg
                                            </td>

                                            <td>
                                                <span
                                                    className={`yield-quality ${getQualityClass(
                                                        record.quality
                                                    )}`}
                                                >
                                                    {
                                                        record.quality
                                                    }
                                                </span>
                                            </td>

                                            <td>
                                                {
                                                    record.harvestType
                                                }
                                            </td>

                                            <td>
                                                {Number(
                                                    record.yieldPerHectare
                                                ).toLocaleString(
                                                    "en-US",
                                                    {
                                                        maximumFractionDigits:
                                                            2,
                                                    }
                                                )}{" "}
                                                kg/ha
                                            </td>

                                            <td>
                                                {
                                                    record.notes ||
                                                    "—"
                                                }
                                            </td>
                                        </tr>
                                    )
                                )
                            ) : (
                                <tr>
                                    <td
                                        colSpan="8"
                                        className="crop-yield-empty"
                                    >
                                        No yield records
                                        available.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </article>
        </section>
    );
}

export default CropAnalytics;