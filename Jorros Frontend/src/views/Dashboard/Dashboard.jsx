"use client";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { useAuth } from "../../context/AuthContext.jsx";
import dynamic from "next/dynamic";
import DeferredSection from "../../components/DeferredSection/DeferredSection.jsx";
import DashboardResourceOverview from "./components/DashboardResourceOverview.jsx";
import useDashboardResources from "./hooks/useDashboardResources.js";
import { resourcePeriodRange } from "./resourceOverview.js";
import { farmDateKey } from "../../utils/farmCalendar.js";
import WeatherReadiness from "../../components/FarmEvents/WeatherReadiness.jsx";
import { weatherSignals } from "../../services/weatherPolicy.js";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
const DashboardCharts = dynamic(() => import("../../components/DashboardCharts/DashboardCharts.jsx"), {
    ssr: false, loading: () => <p role="status">Loading farm charts…</p>,
});
import DashboardCalendar from "../../components/DashboardCalendar/DashboardCalendar.jsx";
import DashboardActivity from "../../components/DashboardActivity/DashboardActivity.jsx";
import DashboardExtras, {
    DashboardWeatherStrip,
} from "../../components/DashboardExtras/DashboardExtras.jsx";
import PhoneAccessButton from "../../components/PhoneAccess/PhoneAccessButton.jsx";
import DashboardPeriodControl from "../../components/DashboardPeriodControl/DashboardPeriodControl.jsx";

import { cropService } from "../../services/cropService.js";
import { farmPlanService } from "../../services/farmPlanService.js";
import Link from "next/link";
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
    const { hasPermission } = useAuth();
    const resourceAccess = useMemo(() => ({ crop: hasPermission("crops:view"), livestock: hasPermission("livestock:view"), inventory: hasPermission("inventory:view") }), [hasPermission]);
    const [dashboardPeriod, setDashboardPeriod] = useState(
        getSavedDashboardPeriod
    );

    const [crops, setCrops] = useState([]);
    const [livestock, setLivestock] = useState([]);
    const [inventory, setInventory] = useState([]);
    const [taskCount, setTaskCount] = useState(null);
    const [activitiesError, setActivitiesError] = useState("");
    const [cropOverview, setCropOverview] = useState(null);
    const [farmLandPlan, setFarmLandPlan] = useState(null);
    const [livestockOverview, setLivestockOverview] = useState(null);
    const [inventoryOverview, setInventoryOverview] = useState(null);
    const [alertCount, setAlertCount] = useState(null);
    const [sourceErrors, setSourceErrors] = useState({});
    const coreRequestRef = useRef(0), tasksRequestRef = useRef(0);
    const range = useMemo(() => resourcePeriodRange(dashboardPeriod), [dashboardPeriod]);
    const [eventCreationRequest, setEventCreationRequest] = useState(0);
    const requestFarmEvent = useCallback(() => setEventCreationRequest((value) => value + 1), []);
    const weatherRequestRef = useRef(false);
    const [weatherData, setWeatherData] = useState(null);
    const [alertSettings, setAlertSettings] = useState(null);

    const [loading, setLoading] = useState(true);
    const [activitiesLoading, setActivitiesLoading] =
        useState(true);
    const [inventoryError, setInventoryError] = useState("");
    const [loadError, setLoadError] = useState("");
    const [weatherError, setWeatherError] = useState("");

    const resourceOverview = useDashboardResources({ period: dashboardPeriod, inventory, inventoryError, inventoryLoading: loading, stockSummary: inventoryOverview, access: resourceAccess });

    // Totals are independent of the bounded rows used by preview charts.
    const loadCoreDashboardData = useCallback(async () => {
        const requestId = ++coreRequestRef.current;
        setLoading(true); setLoadError("");
        const options = { startDate: range.startDate, endDate: range.endDate };
        const results = await Promise.allSettled([
            cropService.getOverview(options), livestockService.getOverview(options),
            inventoryService.getInventorySummary(), alertService.getAlertSummary(),
        ]);
        if (requestId !== coreRequestRef.current) return;
        const errors = {};
        const [crop, animal, stock, alerts] = results;
        if (crop.status === "fulfilled") { setCropOverview(crop.value); setCrops(crop.value.chart_records); }
        else { setCropOverview(null); setCrops([]); errors.crops = crop.reason?.message || "Crop totals are unavailable."; }
        if (animal.status === "fulfilled") { setLivestockOverview(animal.value); setLivestock(animal.value.chart_records); }
        else { setLivestockOverview(null); setLivestock([]); errors.livestock = animal.reason?.message || "Livestock totals are unavailable."; }
        if (stock.status === "fulfilled") {
            setInventoryOverview(stock.value); setInventoryError("");
            setInventory((stock.value.preview_items || []).map(item => ({ ...item, reorderLevel: item.reorder_level, expirationDate: item.expiration_date })));
        } else {
            setInventoryOverview(null); setInventory([]);
            errors.inventory = stock.reason?.message || "Inventory totals are unavailable."; setInventoryError(errors.inventory);
        }
        if (alerts.status === "fulfilled") setAlertCount(alerts.value.active);
        else { setAlertCount(null); errors.alerts = alerts.reason?.message || "Alert totals are unavailable."; }
        setSourceErrors(errors);
        setLoadError(Object.keys(errors).length ? "Some dashboard data is unavailable. A dash means it could not be loaded." : "");
        setLoading(false);
    }, [range.startDate, range.endDate]);

    const loadDashboardActivities = useCallback(async () => {
        const requestId = ++tasksRequestRef.current;
        setActivitiesLoading(true); setActivitiesError("");
        try {
            const data = await activityService.getSummary(farmDateKey());
            if (requestId === tasksRequestRef.current) setTaskCount(data.tasks_today);
        } catch (error) {
            if (requestId === tasksRequestRef.current) { setTaskCount(null); setActivitiesError(error?.message || "Today's task count is unavailable."); }
        } finally { if (requestId === tasksRequestRef.current) setActivitiesLoading(false); }
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
        if (!resourceAccess.crop) return;
        let alive = true;
        farmPlanService.overview().then(result => { if (alive) setFarmLandPlan(result); })
            .catch(() => { if (alive) setFarmLandPlan(null); });
        return () => { alive = false; };
    }, [resourceAccess.crop]);

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
        const value = (source, count) => loading ? "…" : sourceErrors[source] || count == null ? "—" : String(count);
        return [
            { id: 1, title: "Total Crops", value: value("crops", cropOverview?.total), className: "crops" },
            { id: 2, title: "Total Livestock", value: value("livestock", livestockOverview?.total), className: "livestock" },
            { id: 3, title: "Active Alerts", value: value("alerts", alertCount), className: "alerts" },
            { id: 4, title: "Total Area", value: cropOverview && !sourceErrors.crops && !loading ? `${Number(Number(cropOverview.area).toFixed(2))} ha` : value("crops", null), className: "area" },
            { id: 5, title: "Tasks Today", value: activitiesLoading ? "…" : activitiesError || taskCount == null ? "—" : String(taskCount), className: "tasks" },
        ];
    }, [cropOverview, livestockOverview, alertCount, sourceErrors, loading, activitiesLoading, activitiesError, taskCount]);

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
                        {loadError} <button type="button" onClick={loadCoreDashboardData}>Retry dashboard data</button>
                    </p>
                )}

                {activitiesError && <p className="dashboard-resource-error" role="alert">Today's task count is unavailable. {activitiesError} <button type="button" onClick={loadDashboardActivities}>Retry task count</button></p>}
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

                {resourceAccess.crop && farmLandPlan && <section className="dashboard-farm-plan-strip" aria-label="Farm land allocation plan">
                    <div><span className="material-symbols-outlined" aria-hidden="true">landscape</span>
                        <strong>Farm Land &amp; Facilities</strong>
                        <small>Crop fields: {Number(farmLandPlan.proposed_crop_m2).toLocaleString()} m² · Facilities: {Number(farmLandPlan.proposed_facility_m2).toLocaleString()} m²</small>
                    </div>
                    <Link href="/farm-plan">View area plan</Link>
                </section>}

                {(resourceAccess.crop || resourceAccess.livestock) && <DashboardResourceOverview {...resourceOverview} stockError={resourceAccess.inventory ? inventoryError : ""} onRetry={() => { resourceOverview.retry(); void loadCoreDashboardData(); }} />}

                <DashboardWeatherStrip
                    weatherData={weatherData}
                    weatherError={weatherError}
                >
                    <WeatherReadiness weather={weatherData} error={weatherError} settings={alertSettings?.weather} />
                </DashboardWeatherStrip>

                <section className="dashboard-grid">
                    {loading ? <p role="status">Loading farm charts…</p> : sourceErrors.crops || sourceErrors.livestock ? <article className="dashboard-card"><p role="status">Farm charts are unavailable until the resource data can be loaded.</p><button type="button" onClick={loadCoreDashboardData}>Retry charts</button></article> : <DeferredSection label="farm charts"><DashboardCharts
                        period={dashboardPeriod} crops={crops} livestock={livestock}
                        cropStatusCounts={cropOverview?.status_counts} healthCounts={livestockOverview?.health_counts}
                    /></DeferredSection>}

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
                        crops={cropOverview?.recommendation_crops || []}
                        inventoryLoading={loading}
                        inventoryError={inventoryError}
                        recommendationInventory={inventoryOverview?.seed_items || []}
                        weatherData={weatherData}
                        weatherSettings={alertSettings?.weather}
                    />
                </section>
            </main>
        </div>
    );
}

export default Dashboard;
