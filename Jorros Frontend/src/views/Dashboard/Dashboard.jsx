"use client";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import WeatherReadiness from "../../components/FarmEvents/WeatherReadiness.jsx";
import { weatherSignals } from "../../services/weatherPolicy.js";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import DashboardCharts from "../../components/DashboardCharts/DashboardCharts.jsx";
import DashboardCalendar from "../../components/DashboardCalendar/DashboardCalendar.jsx";
import DashboardActivity from "../../components/DashboardActivity/DashboardActivity.jsx";
import DashboardExtras, {
    DashboardWeatherStrip,
} from "../../components/DashboardExtras/DashboardExtras.jsx";
import PhoneAccessButton from "../../components/PhoneAccess/PhoneAccessButton.jsx";
import DashboardPeriodControl from "../../components/DashboardPeriodControl/DashboardPeriodControl.jsx";

import { cropService } from "../../services/cropService.js";
import { livestockService } from "../../services/livestockService.js";
import { inventoryService } from "../../services/inventoryService.js";
import { activityService } from "../../services/activityService.js";
import { weatherService } from "../../services/weatherService.js";
import { alertService } from "../../services/alertService.js";

import "./Dashboard.css";

function dateIsWithinDays(value, days) {
    if (!value) {
        return false;
    }

    const target = new Date(
        `${String(value).slice(0, 10)}T00:00:00`
    );

    if (Number.isNaN(target.getTime())) {
        return false;
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const limit = new Date(today);
    limit.setDate(limit.getDate() + days);

    return target >= today && target <= limit;
}

function dateIsToday(value) {
    if (!value) {
        return false;
    }

    const target = new Date(
        `${String(value).slice(0, 10)}T00:00:00`
    );

    if (Number.isNaN(target.getTime())) {
        return false;
    }

    const today = new Date();

    return (
        target.getFullYear() === today.getFullYear() &&
        target.getMonth() === today.getMonth() &&
        target.getDate() === today.getDate()
    );
}

function getSavedDashboardPeriod() {
    if (typeof window === "undefined") {
        return "month";
    }

    return (
        localStorage.getItem("joross-dashboard-period") ||
        "month"
    );
}

function Dashboard() {
    const [dashboardPeriod, setDashboardPeriod] = useState(
        getSavedDashboardPeriod
    );

    const [crops, setCrops] = useState([]);
    const [livestock, setLivestock] = useState([]);
    const [inventory, setInventory] = useState([]);
    const [activities, setActivities] = useState([]);
    const [eventCreationRequest, setEventCreationRequest] = useState(0);
    const requestFarmEvent = useCallback(() => setEventCreationRequest((value) => value + 1), []);
    const weatherRequestRef = useRef(false);
    const [weatherData, setWeatherData] = useState(null);
    const [alertSettings, setAlertSettings] = useState(null);

    const [loading, setLoading] = useState(true);
    const [activitiesLoading, setActivitiesLoading] =
        useState(true);
    const [loadError, setLoadError] = useState("");
    const [weatherError, setWeatherError] = useState("");

    // Load the data needed for the main dashboard first.
    const loadCoreDashboardData = useCallback(async () => {
        setLoading(true);
        setLoadError("");

        const [cropResult, livestockResult, inventoryResult] =
            await Promise.allSettled([
                cropService.getCrops(false, true),
                livestockService.getLivestock(false),
                inventoryService.getInventory(false),
            ]);

        let failedCount = 0;

        if (cropResult.status === "fulfilled") {
            setCrops(cropResult.value || []);
        } else {
            failedCount += 1;
            console.error(
                "Failed to load dashboard crops:",
                cropResult.reason
            );
        }

        if (livestockResult.status === "fulfilled") {
            // The livestock list already has quantity, health, weight, dates, and notes.
            setLivestock(livestockResult.value || []);
        } else {
            failedCount += 1;
            console.error(
                "Failed to load dashboard livestock:",
                livestockResult.reason
            );
        }

        if (inventoryResult.status === "fulfilled") {
            setInventory(inventoryResult.value || []);
        } else {
            failedCount += 1;
            console.error(
                "Failed to load dashboard inventory:",
                inventoryResult.reason
            );
        }

        if (failedCount > 0) {
            setLoadError(
                failedCount === 3
                    ? "Unable to load farm data. Make sure the FastAPI backend is running and you are logged in."
                    : "Some dashboard farm data could not be loaded."
            );
        }

        setLoading(false);
    }, []);

    // Activities are separate so task updates do not reload crops, livestock, and inventory.
    const loadDashboardActivities = useCallback(async () => {
        try {
            setActivitiesLoading(true);
            const records =
                await activityService.getActivities(false);
            setActivities(records || []);
        } catch (error) {
            console.error(
                "Failed to load dashboard activities:",
                error
            );
        } finally {
            setActivitiesLoading(false);
        }
    }, []);

    // Alert settings are helpful, but the default thresholds can be used while they load.
    const loadAlertSettings = useCallback(async () => {
        try {
            const settings = await alertService.getSettings();
            setAlertSettings(settings);
        } catch (error) {
            setAlertSettings(null);
            console.error(
                "Failed to load alert settings for dashboard:",
                error
            );
        }
    }, []);

    // Weather loads on its own so a slow external API never holds up farm records.
    const loadDashboardWeather = useCallback(async () => {
        if (weatherRequestRef.current) return;
        weatherRequestRef.current = true;
        try {
            setWeatherError("");
            const weather = await weatherService.getWeather();
            setWeatherData(weather);
        } catch (error) {
            setWeatherData((old) => old ? { ...old, dataStatus: "Stale" } : null);
            setWeatherError(
                error?.message || "Weather unavailable"
            );

            console.error(
                "Failed to load dashboard weather:",
                error
            );
        } finally { weatherRequestRef.current = false; }
    }, []);

    useEffect(() => {
        void loadCoreDashboardData();
        void loadDashboardActivities();
        void loadAlertSettings();
        void loadDashboardWeather();
    }, [
        loadAlertSettings,
        loadCoreDashboardData,
        loadDashboardActivities,
        loadDashboardWeather,
    ]);

    useEffect(() => {
        const refreshWeather = () => { if (!document.hidden) void loadDashboardWeather(); };
        const timer = window.setInterval(refreshWeather, 5 * 60 * 1000);
        window.addEventListener("focus", refreshWeather);
        document.addEventListener("visibilitychange", refreshWeather);
        return () => { window.clearInterval(timer); window.removeEventListener("focus", refreshWeather); document.removeEventListener("visibilitychange", refreshWeather); };
    }, [loadDashboardWeather]);

    useEffect(() => {
        const refreshDashboardActivities = () => {
            void loadDashboardActivities();
        };

        const refreshLinkedFarmData = () => {
            void loadCoreDashboardData();
        };

        window.addEventListener(
            "joross:activities-updated",
            refreshDashboardActivities
        );
        window.addEventListener(
            "joross:farm-data-updated",
            refreshLinkedFarmData
        );

        return () => {
            window.removeEventListener(
                "joross:activities-updated",
                refreshDashboardActivities
            );
            window.removeEventListener(
                "joross:farm-data-updated",
                refreshLinkedFarmData
            );
        };
    }, [
        loadCoreDashboardData,
        loadDashboardActivities,
    ]);

    const summaryCards = useMemo(() => {
        // Main totals always describe the farm's current state.
        const totalCrops = crops.length;

        const totalLivestock = livestock.reduce(
            (total, record) =>
                total +
                Math.max(Number(record.quantity) || 0, 0),
            0
        );

        const totalArea = crops.reduce(
            (total, crop) =>
                total + (Number(crop.area) || 0),
            0
        );

        const inventoryAlerts = inventory.filter(
            (item) =>
                Number(item.quantity) <=
                Number(item.reorderLevel)
        ).length;

        const livestockHealthAlerts = livestock.filter(
            (record) =>
                ["At Risk", "Sick"].includes(
                    record.healthStatus
                )
        ).length;

        const vaccinationAdvanceDays =
            Number(
                alertSettings?.livestock
                    ?.vaccinationAdvanceDays
            ) || 7;

        const vaccinationAlerts = livestock.filter(
            (record) =>
                dateIsWithinDays(
                    record.nextVaccination,
                    vaccinationAdvanceDays
                )
        ).length;

        const harvestAdvanceDays =
            Number(
                alertSettings?.crop?.harvestAdvanceDays
            ) || 7;

        const harvestAlerts = crops.filter(
            (crop) =>
                crop.status !== "Harvested" &&
                crop.status !== "Failed" &&
                dateIsWithinDays(
                    crop.estimatedHarvest,
                    harvestAdvanceDays
                )
        ).length;

        const pestAlerts = crops.reduce(
            (total, crop) =>
                total +
                (crop.pestDiseases || []).filter(
                    (record) =>
                        String(record.status).toLowerCase() ===
                        "active"
                ).length,
            0
        );

        const weatherAlerts = weatherSignals(weatherData, alertSettings?.weather).length;


        const activeAlerts =
            inventoryAlerts +
            livestockHealthAlerts +
            vaccinationAlerts +
            harvestAlerts +
            pestAlerts +
            weatherAlerts;

        const tasksToday = activities.filter(
            (activity) =>
                dateIsToday(activity.date) &&
                ["Pending", "In Progress"].includes(
                    activity.status
                )
        ).length;

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
                value: loading
                    ? "…"
                    : String(totalLivestock),
                className: "livestock",
            },
            {
                id: 3,
                title: "Active Alerts",
                value: loading
                    ? "…"
                    : String(activeAlerts),
                className: "alerts",
            },
            {
                id: 4,
                title: "Total Area",
                value: loading
                    ? "…"
                    : `${Number(totalArea.toFixed(2))} ha`,
                className: "area",
            },
            {
                id: 5,
                title: "Tasks Today",
                value: activitiesLoading
                    ? "…"
                    : String(tasksToday),
                className: "tasks",
            },
        ];
    }, [
        activities,
        activitiesLoading,
        alertSettings,
        crops,
        inventory,
        livestock,
        loading,
        weatherData,
    ]);

    const handlePeriodChange = (nextPeriod) => {
        setDashboardPeriod(nextPeriod);

        localStorage.setItem(
            "joross-dashboard-period",
            nextPeriod
        );

        window.dispatchEvent(
            new CustomEvent(
                "joross:dashboard-period-changed",
                {
                    detail: {
                        period: nextPeriod,
                    },
                }
            )
        );
    };

    return (
        <div className="dashboard-layout">
            <Sidebar />

            <main className="page-content">
                <header className="dashboard-header">
                    <div className="welcome-text">
                        <h1>Welcome to Joross Farm!</h1>

                        <p>
                            View and analyze farm performance and
                            activities.
                        </p>
                    </div>

                    <div className="dashboard-header-right">
                        <PhoneAccessButton />
                        <DashboardPeriodControl
                            value={dashboardPeriod}
                            onChange={handlePeriodChange}
                        />

                        <AppHeaderActions />
                    </div>
                </header>

                {loadError && (
                    <p
                        role="status"
                        style={{
                            margin: "0 0 14px",
                            color: "#b42318",
                            fontSize: "14px",
                        }}
                    >
                        {loadError}
                    </p>
                )}

                <section className="summary-grid">
                    {summaryCards.map((card) => (
                        <article
                            key={card.id}
                            className={`summary-card ${card.className}`}
                        >
                            <h3>{card.title}</h3>
                            <h2>{card.value}</h2>
                        </article>
                    ))}
                </section>

                <DashboardWeatherStrip
                    weatherData={weatherData}
                    weatherError={weatherError}
                >
                    <WeatherReadiness weather={weatherData} error={weatherError} settings={alertSettings?.weather} />
                </DashboardWeatherStrip>

                <section className="dashboard-grid">
                    <DashboardCharts
                        period={dashboardPeriod}
                        crops={crops}
                        livestock={livestock}
                    />

                    <DashboardCalendar
                        period={dashboardPeriod}
                        eventCreationRequest={eventCreationRequest}
                    />

                    <DashboardActivity
                        period={dashboardPeriod}
                        onAddEvent={requestFarmEvent}
                    />

                    <DashboardExtras
                        period={dashboardPeriod}
                        inventoryItems={inventory}
                        crops={crops}
                        weatherData={weatherData}
                        weatherSettings={alertSettings?.weather}
                    />
                </section>
            </main>
        </div>
    );
}

export default Dashboard;
