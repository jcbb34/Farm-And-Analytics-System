import { recommendCrops } from "../data/philippinesCropGuide.js";

export const RECOMMENDATION_CONDITIONS_KEY =
    "joross-crop-recommendation-conditions";

export const RECOMMENDATION_CONDITIONS_EVENT =
    "joross:crop-recommendation-conditions-changed";

export function getDefaultRecommendationConditions() {
    return {
        month: new Date().getMonth() + 1,
        region: "Bicol Region",
        rainfall: "Normal",
        irrigation: "Limited Irrigation",
        drainage: "Good",
        temperature: 29,
        useLiveWeather: true,
    };
}

function safeNumber(value, fallback = 0) {
    const number = Number(value);
    return Number.isFinite(number) ? number : fallback;
}

export function normalizeCropName(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}

export function classifyRainfall(rainTotalMm) {
    const value = safeNumber(rainTotalMm, 0);

    if (value < 5) {
        return "Low";
    }

    if (value >= 30) {
        return "High";
    }

    return "Normal";
}

export function getStoredRecommendationConditions() {
    const defaults = getDefaultRecommendationConditions();

    if (typeof window === "undefined") {
        return defaults;
    }

    try {
        const raw = window.localStorage.getItem(
            RECOMMENDATION_CONDITIONS_KEY
        );

        if (!raw) {
            return defaults;
        }

        const parsed = JSON.parse(raw);

        return {
            ...defaults,
            ...parsed,
            month: safeNumber(parsed?.month, defaults.month),
            temperature: safeNumber(
                parsed?.temperature,
                defaults.temperature
            ),
            useLiveWeather:
                parsed?.useLiveWeather !== false,
        };
    } catch {
        return defaults;
    }
}

export function saveRecommendationConditions(conditions) {
    if (typeof window === "undefined") {
        return;
    }

    const next = {
        ...getDefaultRecommendationConditions(),
        ...conditions,
        month: safeNumber(
            conditions?.month,
            new Date().getMonth() + 1
        ),
        temperature: safeNumber(
            conditions?.temperature,
            29
        ),
        useLiveWeather:
            conditions?.useLiveWeather !== false,
    };

    window.localStorage.setItem(
        RECOMMENDATION_CONDITIONS_KEY,
        JSON.stringify(next)
    );

    window.dispatchEvent(
        new CustomEvent(
            RECOMMENDATION_CONDITIONS_EVENT,
            {
                detail: next,
            }
        )
    );
}

export function applyWeatherToConditions(
    conditions,
    weatherData
) {
    const next = {
        ...getDefaultRecommendationConditions(),
        ...conditions,
    };

    if (!next.useLiveWeather || !weatherData) {
        return next;
    }

    const liveTemperature = safeNumber(
        weatherData?.current?.temperatureC,
        next.temperature
    );

    return {
        ...next,
        month: new Date().getMonth() + 1,
        temperature: Math.round(liveTemperature),
        rainfall: classifyRainfall(
            weatherData?.next24Hours?.rainTotalMm
        ),
        useLiveWeather: true,
    };
}

function getCropNameFromPerformanceRow(row) {
    return (
        row?.crop ||
        row?.cropName ||
        row?.name ||
        ""
    );
}

function getYieldFromPerformanceRow(row) {
    return safeNumber(
        row?.yieldKgPerHa ??
            row?.yieldPerHectare ??
            row?.yieldPerHa,
        0
    );
}

function collectPerformanceByCrop(liveData = {}) {
    const valuesByCrop = new Map();

    const addValue = (cropName, value) => {
        const key = normalizeCropName(cropName);
        const yieldValue = safeNumber(value, 0);

        if (!key || yieldValue <= 0) {
            return;
        }

        if (!valuesByCrop.has(key)) {
            valuesByCrop.set(key, []);
        }

        valuesByCrop.get(key).push(yieldValue);
    };

    (liveData.reports || []).forEach((report) => {
        if (
            report?.status === "Archived" ||
            report?.category !== "Crop"
        ) {
            return;
        }

        const performanceRows =
            report?.snapshot?.cropPerformance || [];

        performanceRows.forEach((row) => {
            addValue(
                getCropNameFromPerformanceRow(row),
                getYieldFromPerformanceRow(row)
            );
        });
    });

    (liveData.crops || []).forEach((crop) => {
        (crop?.yieldRecords || []).forEach((record) => {
            addValue(
                crop?.name,
                record?.yieldPerHectare ??
                    record?.yieldKgPerHa ??
                    record?.yieldPerHa
            );
        });
    });

    const result = new Map();

    valuesByCrop.forEach((values, key) => {
        const average =
            values.reduce(
                (total, value) => total + value,
                0
            ) / values.length;

        result.set(key, {
            averageYield: average,
            recordCount: values.length,
        });
    });

    return result;
}

function getFarmAverageYield(performanceByCrop) {
    const values = Array.from(
        performanceByCrop.values()
    )
        .map((entry) => entry.averageYield)
        .filter((value) => value > 0);

    if (values.length === 0) {
        return 0;
    }

    return (
        values.reduce(
            (total, value) => total + value,
            0
        ) / values.length
    );
}

function getCurrentCropNames(crops = []) {
    return new Set(
        crops
            .filter(
                (crop) =>
                    crop?.status !== "Archived" &&
                    crop?.status !== "Failed"
            )
            .map((crop) =>
                normalizeCropName(crop?.name)
            )
            .filter(Boolean)
    );
}

function findMatchingSeedItem(
    inventory = [],
    cropName
) {
    const target = normalizeCropName(cropName);

    if (!target) {
        return null;
    }

    return (
        inventory.find((item) => {
            const itemName = normalizeCropName(
                item?.name || item?.itemName
            );
            const category = normalizeCropName(
                item?.category
            );
            const description = normalizeCropName(
                item?.description
            );
            const combined = `${itemName} ${description}`;
            const isSeed =
                category.includes("seed") ||
                itemName.includes("seed") ||
                description.includes("seed");

            const reverseMatch =
                itemName.length >= 3 &&
                target.includes(itemName);

            return (
                isSeed &&
                (combined.includes(target) ||
                    reverseMatch)
            );
        }) || null
    );
}

function scoreToSuitability(score) {
    if (score >= 85) {
        return "Highly Suitable";
    }

    if (score >= 70) {
        return "Suitable";
    }

    if (score >= 55) {
        return "Conditional";
    }

    return "Not Preferred";
}

export function enhanceCropRecommendations(
    recommendations = [],
    liveData = {}
) {
    const crops = liveData.crops || [];
    const inventory = liveData.inventory || [];
    const performanceByCrop =
        collectPerformanceByCrop(liveData);
    const farmAverageYield =
        getFarmAverageYield(performanceByCrop);
    const currentCropNames =
        getCurrentCropNames(crops);

    return recommendations
        .map((crop) => {
            const cropKey = normalizeCropName(
                crop?.name
            );
            const hasCurrentRecord =
                currentCropNames.has(cropKey);
            const performance =
                performanceByCrop.get(cropKey);
            const hasHistory = Boolean(performance);
            const matchingSeed =
                findMatchingSeedItem(
                    inventory,
                    crop?.name
                );

            let adjustment = 0;
            const farmReasons = [];

            if (
                hasHistory &&
                farmAverageYield > 0
            ) {
                if (
                    performance.averageYield >=
                    farmAverageYield * 1.05
                ) {
                    adjustment += 5;
                    farmReasons.push(
                        "Joross Farm history shows above-average yield for this same crop."
                    );
                } else if (
                    performance.averageYield <
                    farmAverageYield * 0.75
                ) {
                    adjustment -= 4;
                    farmReasons.push(
                        "Joross Farm history shows below-average yield for this same crop."
                    );
                } else {
                    adjustment += 2;
                    farmReasons.push(
                        "Joross Farm history shows yield close to the farm average for this same crop."
                    );
                }
            }

            if (hasCurrentRecord) {
                adjustment += 1;
                farmReasons.push(
                    "This crop is already present in current Joross Farm crop records."
                );
            }

            if (matchingSeed) {
                const quantity = safeNumber(
                    matchingSeed?.quantity,
                    0
                );
                const reorderLevel = safeNumber(
                    matchingSeed?.reorderLevel,
                    0
                );

                if (quantity <= 0) {
                    adjustment -= 5;
                    farmReasons.push(
                        "Matching seed inventory is currently out of stock."
                    );
                } else if (
                    quantity <= reorderLevel
                ) {
                    adjustment -= 3;
                    farmReasons.push(
                        "Matching seed inventory is at or below reorder level."
                    );
                } else {
                    adjustment += 2;
                    farmReasons.push(
                        "Matching seed inventory is currently available."
                    );
                }
            }

            const score = Math.max(
                0,
                Math.min(
                    100,
                    safeNumber(crop?.score, 0) +
                        adjustment
                )
            );

            const evidenceSources = [
                "Seasonal crop guide",
                liveData.weather ? "Current weather" : null,
                hasHistory ? "Joross yield history" : null,
                matchingSeed ? "Seed inventory" : null,
                hasCurrentRecord ? "Current crop records" : null,
            ].filter(Boolean);
            const evidenceLevel =
                evidenceSources.length >= 4
                    ? "Strong evidence"
                    : evidenceSources.length >= 3
                      ? "Moderate evidence"
                      : "Limited evidence";

            let farmStatus =
                "NEW · No Joross Farm Record";

            if (
                hasCurrentRecord &&
                hasHistory
            ) {
                farmStatus =
                    "✓ Current Joross Crop · ↺ Joross Farm History";
            } else if (hasCurrentRecord) {
                farmStatus =
                    "✓ Current Joross Crop";
            } else if (hasHistory) {
                farmStatus =
                    "↺ Joross Farm History";
            }

            const trialNote =
                !hasCurrentRecord &&
                !hasHistory
                    ? " Joross Farm has no current or historical record for this crop, so use a small trial plot before wider planting."
                    : "";

            return {
                ...crop,
                score,
                suitability:
                    scoreToSuitability(score),
                farmStatus,
                hasCurrentRecord,
                hasHistory,
                historicalAverageYield:
                    performance?.averageYield || 0,
                historicalRecordCount:
                    performance?.recordCount || 0,
                evidenceLevel,
                evidenceSources,
                notes: `${crop?.notes || ""}${trialNote}`.trim(),
                reasons: [
                    ...farmReasons,
                    ...(crop?.reasons || []),
                ],
            };
        })
        .sort((a, b) => b.score - a.score);
}

export function buildCropRecommendations(
    conditions,
    liveData = {}
) {
    const effectiveConditions =
        applyWeatherToConditions(
            conditions,
            liveData.weather
        );

    const baseRecommendations =
        recommendCrops(effectiveConditions);

    return enhanceCropRecommendations(
        baseRecommendations,
        liveData
    );
}

function daysUntilDate(value) {
    if (!value) {
        return null;
    }

    const target = new Date(
        `${String(value).slice(0, 10)}T00:00:00`
    );

    if (Number.isNaN(target.getTime())) {
        return null;
    }

    const today = new Date();
    const startOfToday = new Date(
        today.getFullYear(),
        today.getMonth(),
        today.getDate()
    );

    return Math.ceil(
        (target.getTime() -
            startOfToday.getTime()) /
            86400000
    );
}

export function buildLiveInsights(liveData = {}) {
    const insights = [];
    const weather = liveData.weather;

    if (weather) {
        const next24 = weather.next24Hours || {};

        if (next24.thunderstormExpected) {
            insights.push({
                id: "weather-thunderstorm",
                icon: "thunderstorm",
                title: "Thunderstorm risk",
                metric: "High",
                suitability: "Not Preferred",
                note: "OpenWeather indicates thunderstorm conditions within the next 24 hours.",
                reasons: [
                    "Review outdoor field work and protect vulnerable farm materials.",
                ],
            });
        } else if (
            safeNumber(next24.rainTotalMm, 0) >= 30
        ) {
            insights.push({
                id: "weather-rain",
                icon: "rainy",
                title: "Heavy rainfall watch",
                metric: `${safeNumber(
                    next24.rainTotalMm,
                    0
                ).toFixed(1)} mm`,
                suitability: "Conditional",
                note: "Rainfall is elevated for the next 24 hours.",
                reasons: [
                    "Check drainage and adjust watering or field work if needed.",
                ],
            });
        } else if (
            safeNumber(
                next24.maxTemperatureC,
                0
            ) >= 32
        ) {
            insights.push({
                id: "weather-heat",
                icon: "device_thermostat",
                title: "High temperature",
                metric: `${safeNumber(
                    next24.maxTemperatureC,
                    0
                ).toFixed(1)}°C`,
                suitability: "Conditional",
                note: "Maximum temperature is high for the next 24 hours.",
                reasons: [
                    "Review watering schedules and animal heat-stress precautions.",
                ],
            });
        } else {
            insights.push({
                id: "weather-normal",
                icon: "partly_cloudy_day",
                title: "Weather conditions",
                metric: `${safeNumber(
                    weather?.current?.temperatureC,
                    0
                ).toFixed(1)}°C`,
                suitability: "Suitable",
                note:
                    weather?.current?.description ||
                    "Current weather is available.",
                reasons: [
                    `Next 24h rain: ${safeNumber(
                        next24.rainTotalMm,
                        0
                    ).toFixed(1)} mm`,
                ],
            });
        }
    }

    const harvestDue = (liveData.crops || []).filter(
        (crop) => {
            if (
                ["Harvested", "Failed"].includes(
                    crop?.status
                )
            ) {
                return false;
            }

            if (
                crop?.status === "Ready for Harvest"
            ) {
                return true;
            }

            const days = daysUntilDate(
                crop?.estimatedHarvest
            );

            return (
                days !== null &&
                days >= 0 &&
                days <= 7
            );
        }
    );

    insights.push({
        id: "crop-harvest",
        icon: "agriculture",
        title: "Harvest readiness",
        metric: String(harvestDue.length),
        suitability:
            harvestDue.length > 0
                ? "Conditional"
                : "Suitable",
        note:
            harvestDue.length > 0
                ? `${harvestDue.length} crop record(s) are ready or due for harvest within 7 days.`
                : "No crop record is due for harvest within the next 7 days.",
        reasons: harvestDue
            .slice(0, 3)
            .map((crop) => crop?.name),
    });

    const livestock = liveData.livestock || [];

    const vaccinationDue = livestock.filter(
        (record) => {
            const days = daysUntilDate(
                record?.nextVaccination
            );

            return (
                days !== null &&
                days >= 0 &&
                days <= 7
            );
        }
    );

    const healthConcernAnimals = livestock.reduce(
        (total, record) => {
            const healthy = safeNumber(
                record?.healthyQuantity,
                0
            );
            const atRisk = safeNumber(
                record?.atRiskQuantity,
                0
            );
            const sick = safeNumber(
                record?.sickQuantity,
                0
            );
            const treatment = safeNumber(
                record?.underTreatmentQuantity,
                0
            );
            // Under-treatment is a condition on affected animals, not an
            // additional head-count bucket. If count-aware batch health is
            // present, trust those counts and never fall back to a legacy
            // batch status such as "Mixed".
            const affected = sick + atRisk;
            const trackedHealth = healthy + affected;

            if (trackedHealth > 0) {
                return total + affected;
            }

            if (treatment > 0) {
                return total + treatment;
            }

            const status = normalizeCropName(
                record?.healthStatus
            );

            if (
                status &&
                !["healthy", "good"].includes(status)
            ) {
                return (
                    total +
                    Math.max(
                        1,
                        safeNumber(
                            record?.quantity,
                            1
                        )
                    )
                );
            }

            return total;
        },
        0
    );

    insights.push({
        id: "livestock-health",
        icon: "health_and_safety",
        title: "Livestock attention",
        metric: String(
            vaccinationDue.length +
                healthConcernAnimals
        ),
        suitability:
            vaccinationDue.length +
                healthConcernAnimals >
            0
                ? "Conditional"
                : "Suitable",
        note:
            vaccinationDue.length +
                healthConcernAnimals >
            0
                ? `${vaccinationDue.length} vaccination record(s) due and ${healthConcernAnimals} animal(s) needing health attention.`
                : "No immediate livestock vaccination or health concern was found.",
        reasons: vaccinationDue
            .slice(0, 2)
            .map(
                (record) =>
                    record?.recordName ||
                    record?.animalId
            ),
    });

    const lowStock = (liveData.inventory || []).filter(
        (item) =>
            safeNumber(item?.quantity, 0) <=
            safeNumber(item?.reorderLevel, 0)
    );

    insights.push({
        id: "inventory-low",
        icon: "inventory_2",
        title: "Low inventory",
        metric: String(lowStock.length),
        suitability:
            lowStock.length > 0
                ? "Not Preferred"
                : "Suitable",
        note:
            lowStock.length > 0
                ? `${lowStock.length} inventory item(s) are at or below reorder level.`
                : "Inventory records are above their configured reorder levels.",
        reasons: lowStock
            .slice(0, 3)
            .map(
                (item) =>
                    `${item?.name}: ${item?.quantity} ${
                        item?.unit || "unit"
                    }`
            ),
    });

    const activeAlerts = (liveData.alerts || []).filter((alert) => {
        const status = String(alert?.status || "").trim().toLowerCase();
        const name = String(alert?.alertName || alert?.name || "").trim().toLowerCase();
        const type = String(alert?.alertType || alert?.type || "").trim().toLowerCase();
        // Routine due-soon reminders belong to Dashboard/Tasks, not risk
        // intelligence. Keep this defensive filter even after the alert engine
        // auto-resolves old legacy reminders.
        return status === "active" && name !== "task due soon" && type !== "task due soon";
    });
    const highAlerts = activeAlerts.filter((alert) =>
        ["high", "critical"].includes(String(alert?.priority || "").trim().toLowerCase())
    );

    insights.push({
        id: "active-alerts",
        icon: "notifications_active",
        title: "Active alerts",
        metric: String(activeAlerts.length),
        suitability:
            highAlerts.length > 0
                ? "Not Preferred"
                : activeAlerts.length > 0
                ? "Conditional"
                : "Suitable",
        note:
            highAlerts.length > 0
                ? `${highAlerts.length} active High/Critical-priority alert(s) require attention.`
                : activeAlerts.length > 0
                ? `${activeAlerts.length} active alert(s) are currently being monitored.`
                : "There are no active alerts.",
        reasons: activeAlerts
            .slice(0, 3)
            .map((alert) => alert?.alertName),
    });

    const now = new Date();
    const today = `${now.getFullYear()}-${String(
        now.getMonth() + 1
    ).padStart(2, "0")}-${String(
        now.getDate()
    ).padStart(2, "0")}`;
    const activities = liveData.activities || [];
    const closedTaskStatuses = new Set([
        "completed",
        "cancelled",
        "canceled",
        "archived",
        "resolved",
    ]);
    const isOpenTask = (activity) =>
        !closedTaskStatuses.has(String(activity?.status || "").trim().toLowerCase());
    const overdueTasks = activities.filter(
        (activity) =>
            isOpenTask(activity) &&
            activity?.date &&
            activity.date < today
    );
    const todayTasks = activities.filter(
        (activity) =>
            isOpenTask(activity) &&
            activity?.date === today
    );

    insights.push({
        id: "farm-tasks",
        icon: "assignment",
        title: "Farm tasks",
        metric: String(
            overdueTasks.length + todayTasks.length
        ),
        suitability:
            overdueTasks.length > 0
                ? "Conditional"
                : "Suitable",
        note:
            overdueTasks.length > 0
                ? `${overdueTasks.length} overdue and ${todayTasks.length} task(s) due today.`
                : `${todayTasks.length} task(s) are due today and no overdue task was found.`,
        reasons: [
            ...overdueTasks,
            ...todayTasks,
        ]
            .slice(0, 3)
            .map((activity) => activity?.name),
    });

    return insights.slice(0, 6);
}
