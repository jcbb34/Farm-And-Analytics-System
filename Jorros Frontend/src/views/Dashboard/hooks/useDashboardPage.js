"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { cropService } from "../../../services/cropService.js";
import { livestockService } from "../../../services/livestockService.js";
import { inventoryService } from "../../../services/inventoryService.js";
import { activityService } from "../../../services/activityService.js";
import { weatherService } from "../../../services/weatherService.js";
import { alertService } from "../../../services/alertService.js";
import { resourceUsageService } from "../../../services/resourceUsageService.js";
import {
    getDashboardPeriodRange,
    isDateInDashboardRange,
    normalizeDashboardPeriod,
} from "../../../services/dashboardPeriod.js";

const PERIOD_KEY = "joross-dashboard-period";
const CUSTOM_RANGE_KEY = "joross-dashboard-custom-range";

function readStoredPeriod() {
    if (typeof window === "undefined") return "month";
    return normalizeDashboardPeriod(localStorage.getItem(PERIOD_KEY));
}

function readStoredCustomRange() {
    if (typeof window === "undefined") {
        return { startDate: "", endDate: "" };
    }

    try {
        const parsed = JSON.parse(localStorage.getItem(CUSTOM_RANGE_KEY) || "{}");
        return {
            startDate: String(parsed?.startDate || "").slice(0, 10),
            endDate: String(parsed?.endDate || "").slice(0, 10),
        };
    } catch {
        return { startDate: "", endDate: "" };
    }
}

function dateIsWithinDays(value, days) {
    if (!value) return false;

    const target = new Date(`${String(value).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(target.getTime())) return false;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const limit = new Date(today);
    limit.setDate(limit.getDate() + days);

    return target >= today && target <= limit;
}

function isExpiringSoon(value, days = 30) {
    if (!value) return false;

    const expiration = new Date(`${String(value).slice(0, 10)}T00:00:00`);
    if (Number.isNaN(expiration.getTime())) return false;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const limit = new Date(today);
    limit.setDate(limit.getDate() + days);

    return expiration >= today && expiration <= limit;
}

export default function useDashboardPage() {
    const [dashboardPeriod, setDashboardPeriod] = useState(readStoredPeriod);
    const [dashboardCustomRange, setDashboardCustomRange] = useState(
        readStoredCustomRange
    );
    const [crops, setCrops] = useState([]);
    const [livestock, setLivestock] = useState([]);
    const [inventory, setInventory] = useState([]);
    const [activities, setActivities] = useState([]);
    const [resourceUsages, setResourceUsages] = useState([]);
    const [weatherData, setWeatherData] = useState(null);
    const [alertSettings, setAlertSettings] = useState(null);
    const [weatherError, setWeatherError] = useState("");
    const [loading, setLoading] = useState(true);
    const [resourceLoading, setResourceLoading] = useState(true);
    const [loadError, setLoadError] = useState("");

    const dashboardRange = useMemo(
        () => getDashboardPeriodRange(dashboardPeriod, dashboardCustomRange),
        [dashboardPeriod, dashboardCustomRange]
    );

    const dashboardPeriodLabel = dashboardRange.label;

    const loadDashboardData = useCallback(async () => {
        setLoading(true);
        setLoadError("");
        setWeatherError("");

        const weatherPromise = weatherService.getWeather();
        const results = await Promise.allSettled([
            cropService.getCrops(false, true),
            livestockService.getLivestock(false),
            inventoryService.getInventory(false),
            activityService.getActivities(false),
            alertService.getSettings(),
        ]);

        const [
            cropResult,
            livestockResult,
            inventoryResult,
            activityResult,
            alertSettingsResult,
        ] = results;

        let failedFarmDataCount = 0;

        if (cropResult.status === "fulfilled") {
            setCrops(cropResult.value);
        } else {
            failedFarmDataCount += 1;
            console.error("Failed to load dashboard crops:", cropResult.reason);
        }

        if (livestockResult.status === "fulfilled") {
            setLivestock(livestockResult.value);
        } else {
            failedFarmDataCount += 1;
            console.error(
                "Failed to load dashboard livestock:",
                livestockResult.reason
            );
        }

        if (inventoryResult.status === "fulfilled") {
            setInventory(inventoryResult.value);
        } else {
            failedFarmDataCount += 1;
            console.error(
                "Failed to load dashboard inventory:",
                inventoryResult.reason
            );
        }

        if (activityResult.status === "fulfilled") {
            setActivities(activityResult.value);
        } else {
            failedFarmDataCount += 1;
            console.error(
                "Failed to load dashboard activities:",
                activityResult.reason
            );
        }

        if (alertSettingsResult.status === "fulfilled") {
            setAlertSettings(alertSettingsResult.value);
        } else {
            setAlertSettings(null);
            console.error(
                "Failed to load alert settings for dashboard:",
                alertSettingsResult.reason
            );
        }

        if (failedFarmDataCount > 0) {
            setLoadError(
                failedFarmDataCount === 4
                    ? "Unable to load farm data. Make sure the FastAPI backend is running and you are logged in."
                    : "Some dashboard farm data could not be loaded."
            );
        }

        setLoading(false);

        try {
            setWeatherData(await weatherPromise);
            setWeatherError("");
        } catch (error) {
            setWeatherData(null);
            setWeatherError(error?.message || "Weather unavailable");
            console.error("Failed to load dashboard weather:", error);
        }
    }, []);

    const loadResourceUsages = useCallback(async () => {
        setResourceLoading(true);

        try {
            const usages = await resourceUsageService.getUsages({
                startDate: dashboardRange.startDate,
                endDate: dashboardRange.endDate,
            });
            setResourceUsages(usages.filter((item) => !item.isVoided));
        } catch (error) {
            setResourceUsages([]);
            console.error("Failed to load dashboard resource usage:", error);
        } finally {
            setResourceLoading(false);
        }
    }, [dashboardRange.endDate, dashboardRange.startDate]);

    useEffect(() => {
        loadDashboardData();
    }, [loadDashboardData]);

    useEffect(() => {
        loadResourceUsages();
    }, [loadResourceUsages]);

    useEffect(() => {
        const refreshActivities = async () => {
            try {
                setActivities(await activityService.getActivities(false));
            } catch (error) {
                console.error("Failed to refresh dashboard activities:", error);
            }
        };

        window.addEventListener("joross:activities-updated", refreshActivities);
        window.addEventListener(
            "joross:resource-usage-updated",
            loadResourceUsages
        );

        return () => {
            window.removeEventListener(
                "joross:activities-updated",
                refreshActivities
            );
            window.removeEventListener(
                "joross:resource-usage-updated",
                loadResourceUsages
            );
        };
    }, [loadResourceUsages]);

    const summaryCards = useMemo(() => {
        const totalCrops = crops.length;
        const totalLivestock = livestock.reduce(
            (total, record) =>
                total + Math.max(Number(record.quantity) || 0, 0),
            0
        );
        const totalArea = crops.reduce(
            (total, crop) => total + (Number(crop.area) || 0),
            0
        );

        const inventoryAlerts = inventory.filter(
            (item) => Number(item.quantity) <= Number(item.reorderLevel)
        ).length;

        const livestockHealthAlerts = livestock.filter((record) => {
            const affected =
                (Number(record.atRiskQuantity) || 0) +
                (Number(record.sickQuantity) || 0) +
                (Number(record.underTreatmentQuantity) || 0);

            return (
                affected > 0 ||
                ["At Risk", "Sick", "Under Treatment"].includes(
                    record.healthStatus
                )
            );
        }).length;

        const vaccinationAdvanceDays =
            Number(alertSettings?.livestock?.vaccinationAdvanceDays) || 7;
        const vaccinationAlerts = livestock.filter((record) =>
            dateIsWithinDays(record.nextVaccination, vaccinationAdvanceDays)
        ).length;

        const harvestAdvanceDays =
            Number(alertSettings?.crop?.harvestAdvanceDays) || 7;
        const harvestAlerts = crops.filter(
            (crop) =>
                !["Harvesting", "Harvested", "Failed"].includes(crop.status) &&
                dateIsWithinDays(crop.estimatedHarvest, harvestAdvanceDays)
        ).length;

        const pestAlerts = crops.reduce(
            (total, crop) =>
                total +
                (crop.pestDiseases || []).filter(
                    (record) => String(record.status).toLowerCase() === "active"
                ).length,
            0
        );

        const weatherSettings = alertSettings?.weather;
        const rainfallThreshold =
            Number(weatherSettings?.rainfallThreshold) || 80;
        const temperatureThreshold =
            Number(weatherSettings?.temperatureThreshold) || 32;
        const windSpeedThreshold =
            Number(weatherSettings?.windSpeedThreshold) || 40;

        const weatherAlerts = weatherData
            ? [
                  Boolean(weatherSettings?.thunderstormAlert ?? true) &&
                      weatherData.next24Hours.thunderstormExpected,
                  Boolean(weatherSettings?.highTemperatureAlert ?? true) &&
                      weatherData.next24Hours.maxTemperatureC >=
                          temperatureThreshold,
                  Boolean(weatherSettings?.strongWindAlert ?? true) &&
                      weatherData.next24Hours.maxWindSpeedKph >= windSpeedThreshold,
                  Boolean(weatherSettings?.heavyRainAlert ?? true) &&
                      weatherData.next24Hours.rainTotalMm >= rainfallThreshold,
              ].filter(Boolean).length
            : 0;

        const activeAlerts =
            inventoryAlerts +
            livestockHealthAlerts +
            vaccinationAlerts +
            harvestAlerts +
            pestAlerts +
            weatherAlerts;

        const periodTasks = activities.filter(
            (activity) =>
                ["Pending", "In Progress"].includes(activity.status) &&
                isDateInDashboardRange(activity.date, dashboardRange)
        ).length;

        const taskTitle =
            dashboardPeriod === "today"
                ? "Tasks Today"
                : dashboardPeriod === "custom"
                ? "Tasks in Range"
                : `Tasks ${dashboardRange.shortLabel}`;

        return [
            {
                id: 1,
                title: "Total Crops",
                value: loading ? "…" : String(totalCrops),
                className: "crops",
            },
            {
                id: 2,
                title: "Total Livestock",
                value: loading ? "…" : String(totalLivestock),
                className: "livestock",
            },
            {
                id: 3,
                title: "Active Alerts",
                value: loading ? "…" : String(activeAlerts),
                className: "alerts",
            },
            {
                id: 4,
                title: "Total Area",
                value: loading ? "…" : `${Number(totalArea.toFixed(2))} ha`,
                className: "area",
            },
            {
                id: 5,
                title: taskTitle,
                value: loading ? "…" : String(periodTasks),
                className: "tasks",
            },
        ];
    }, [
        activities,
        alertSettings,
        crops,
        dashboardPeriod,
        dashboardRange,
        inventory,
        livestock,
        loading,
        weatherData,
    ]);

    const resourceUsageSummary = useMemo(
        () => ({ totalRecords: resourceUsages.length }),
        [resourceUsages.length]
    );

    const resourceCards = useMemo(() => {
        const formatTypeTotal = (usageTypes) => {
            const matching = resourceUsages.filter((row) =>
                usageTypes.includes(row.usageType)
            );
            if (!matching.length) return "0";

            const byUnit = new Map();
            matching.forEach((row) => {
                const unit = row.unit || "unit";
                byUnit.set(
                    unit,
                    (byUnit.get(unit) || 0) + Number(row.quantity || 0)
                );
            });

            return [...byUnit.entries()]
                .map(
                    ([unit, quantity]) =>
                        `${Number(quantity.toFixed(2))} ${unit}`
                )
                .join(" / ");
        };

        const lowStockItems = inventory.filter(
            (item) => Number(item.quantity) <= Number(item.reorderLevel)
        ).length;
        const expiringItems = inventory.filter((item) =>
            isExpiringSoon(item.expirationDate, 30)
        ).length;

        return [
            {
                id: "fertilizer",
                icon: "compost",
                title: "Fertilizer Used",
                value: formatTypeTotal(["Fertilizer"]),
            },
            {
                id: "pesticide",
                icon: "pest_control",
                title: "Crop Protection Used",
                value: formatTypeTotal(["Pesticide", "Herbicide"]),
            },
            {
                id: "feed",
                icon: "grass",
                title: "Livestock Feed Used",
                value: formatTypeTotal(["Feed"]),
            },
            {
                id: "health",
                icon: "vaccines",
                title: "Animal Health Supplies",
                value: formatTypeTotal(["Medicine", "Vitamin", "Vaccine"]),
            },
            {
                id: "stock-watch",
                icon: "inventory",
                title: "Stock Watch",
                value: `${lowStockItems} low • ${expiringItems} expiring`,
            },
        ];
    }, [inventory, resourceUsages]);

    const handlePeriodChange = (nextPeriod) => {
        const normalized = normalizeDashboardPeriod(nextPeriod);
        setDashboardPeriod(normalized);

        if (typeof window !== "undefined") {
            localStorage.setItem(PERIOD_KEY, normalized);
            window.dispatchEvent(
                new CustomEvent("joross:dashboard-period-changed", {
                    detail: {
                        period: normalized,
                        range: getDashboardPeriodRange(
                            normalized,
                            dashboardCustomRange
                        ),
                    },
                })
            );
        }
    };

    const handleCustomRangeChange = (nextRange) => {
        const normalizedRange = {
            startDate: String(nextRange?.startDate || "").slice(0, 10),
            endDate: String(nextRange?.endDate || "").slice(0, 10),
        };

        setDashboardCustomRange(normalizedRange);
        setDashboardPeriod("custom");

        if (typeof window !== "undefined") {
            localStorage.setItem(CUSTOM_RANGE_KEY, JSON.stringify(normalizedRange));
            localStorage.setItem(PERIOD_KEY, "custom");

            window.dispatchEvent(
                new CustomEvent("joross:dashboard-period-changed", {
                    detail: {
                        period: "custom",
                        range: getDashboardPeriodRange(
                            "custom",
                            normalizedRange
                        ),
                    },
                })
            );
        }
    };

    return {
        dashboardPeriod,
        dashboardCustomRange,
        dashboardRange,
        dashboardPeriodLabel,
        crops,
        livestock,
        inventory,
        weatherData,
        weatherError,
        loading,
        resourceLoading,
        loadError,
        resourceUsageSummary,
        summaryCards,
        resourceCards,
        handlePeriodChange,
        handleCustomRangeChange,
    };
}
