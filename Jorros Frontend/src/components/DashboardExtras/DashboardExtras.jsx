"use client";

import {
    useEffect,
    useMemo,
    useState,
} from "react";

import {
    RECOMMENDATION_CONDITIONS_EVENT,
    buildCropRecommendations,
    getStoredRecommendationConditions,
} from "../../services/cropRecommendationEngine.js";

import { weatherFarmTip } from "../../services/weatherPolicy.js";
import "./DashboardExtras.css";
import "./DashboardRecommendationSync.css";

function getInventoryStatus(item) {
    const quantity = Number(item.quantity) || 0;
    const reorderLevel = Number(item.reorderLevel) || 0;

    if (quantity <= 0) {
        return {
            label: "Out of Stock",
            className: "out-of-stock",
            rank: 0,
        };
    }

    if (quantity <= reorderLevel) {
        return {
            label: "Low Stock",
            className: "low",
            rank: 1,
        };
    }

    return {
        label: "Normal",
        className: "normal",
        rank: 2,
    };
}

function inventoryIcon(item) {
    const text = `${item.name || ""} ${item.category || ""}`.toLowerCase();

    if (text.includes("seed")) {
        return "grass";
    }

    if (text.includes("feed")) {
        return "nutrition";
    }

    if (
        text.includes("fertilizer") ||
        text.includes("compost")
    ) {
        return "compost";
    }

    if (
        text.includes("medicine") ||
        text.includes("vaccine")
    ) {
        return "vaccines";
    }

    return "inventory_2";
}

function weatherMaterialIcon(weatherCode) {
    const code = Number(weatherCode) || 0;

    if (code >= 200 && code <= 232) {
        return "thunderstorm";
    }

    if (
        (code >= 300 && code <= 321) ||
        (code >= 500 && code <= 531)
    ) {
        return "rainy";
    }

    if (code >= 600 && code <= 622) {
        return "weather_snowy";
    }

    if (code >= 701 && code <= 781) {
        return "foggy";
    }

    if (code === 800) {
        return "sunny";
    }

    if (code >= 801 && code <= 804) {
        return "partly_cloudy_day";
    }

    return "partly_cloudy_day";
}

function titleCase(value) {
    return String(value || "")
        .split(" ")
        .filter(Boolean)
        .map(
            (part) =>
                part.charAt(0).toUpperCase() +
                part.slice(1)
        )
        .join(" ");
}

export function DashboardWeatherStrip({
    weatherData = null,
    weatherError = "",
    children,
}) {
    const currentWeather = weatherData?.current;
    const next24 = weatherData?.next24Hours;

    const weatherItems = [
        {
            id: 1,
            title: "Weather",
            value: currentWeather
                ? `${currentWeather.temperatureC == null ? "Unknown" : Math.round(currentWeather.temperatureC)}°C • ${titleCase(currentWeather.description)}`
                : weatherError || "Weather unavailable",
            icon: weatherMaterialIcon(
                currentWeather?.weatherCode
            ),
        },
        {
            id: 2,
            title: "Humidity",
            value: currentWeather
                ? currentWeather.humidityPercent == null ? "Unknown" : `${Math.round(currentWeather.humidityPercent)}%`
                : "—",
            icon: "humidity_percentage",
        },
        {
            id: 3,
            title: "Rain Chance",
            value: next24
                ? next24.maxRainProbabilityPercent == null ? "Unknown" : `${Math.round(next24.maxRainProbabilityPercent)}%`
                : "—",
            icon: "rainy",
        },
        {
            id: 4,
            title: "Wind",
            value: currentWeather
                ? currentWeather.windSpeedKph == null ? "Unknown" : `${Math.round(currentWeather.windSpeedKph)} km/h`
                : "—",
            icon: "air",
        },
    ];

    return (
        <section
            className="dashboard-weather-card"
            title={weatherData?.location || "Joross Farm weather"}
            aria-label="Current farm weather"
        >
            <div className="weather-strip">
            {weatherItems.map((item) => (
                <div className="weather-item" key={item.id}>
                    <div className="weather-icon">
                        <span className="material-symbols-outlined">
                            {item.icon}
                        </span>
                    </div>

                    <div>
                        <strong>{item.title}</strong>
                        <p>{item.value}</p>
                    </div>
                </div>
            ))}
            </div>
            {children}
        </section>
    );
}

function DashboardExtras({
    period = "month",
    inventoryItems = [],
    crops = [],
    weatherData = null,
    weatherSettings = {},
}) {
    const [showFarmTip, setShowFarmTip] = useState(true);
    const [recommendationConditions, setRecommendationConditions] =
        useState(getStoredRecommendationConditions);

    const inventoryOverview = useMemo(() => {
        return inventoryItems
            .map((item) => ({
                ...item,
                stockStatus: getInventoryStatus(item),
            }))
            .sort((a, b) => {
                if (a.stockStatus.rank !== b.stockStatus.rank) {
                    return a.stockStatus.rank - b.stockStatus.rank;
                }

                return Number(a.quantity) - Number(b.quantity);
            })
            .slice(0, 3);
    }, [inventoryItems]);

    useEffect(() => {
        const syncRecommendationConditions = (event) => {
            setRecommendationConditions(
                event?.detail || getStoredRecommendationConditions()
            );
        };

        window.addEventListener(
            RECOMMENDATION_CONDITIONS_EVENT,
            syncRecommendationConditions
        );

        return () => {
            window.removeEventListener(
                RECOMMENDATION_CONDITIONS_EVENT,
                syncRecommendationConditions
            );
        };
    }, []);

    const recommendations = useMemo(
        () =>
            buildCropRecommendations(
                recommendationConditions,
                {
                    crops,
                    inventory: inventoryItems,
                    weather: weatherData,
                }
            ),
        [
            crops,
            inventoryItems,
            recommendationConditions,
            weatherData,
        ]
    );

    const recommendation = recommendations[0] || null;
    const recommendationReasons = (
        recommendation?.reasons || []
    ).slice(0, 3);

    const farmTip = useMemo(
        () => weatherFarmTip(weatherData, weatherSettings),
        [weatherData, weatherSettings]
    );

    return (
        <>
            <article className="dashboard-card inventory-card">
                <div className="card-title">
                    <h3>Inventory Overview</h3>
                </div>

                <div className="inventory-list">
                    {inventoryOverview.length === 0 ? (
                        <div className="inventory-item">
                            <div className="inventory-info">
                                <div className="inventory-icon">
                                    <span className="material-symbols-outlined">
                                        inventory_2
                                    </span>
                                </div>
                                <div className="inventory-text">
                                    <strong>No inventory records</strong>
                                    <p>Add an inventory item to display it here.</p>
                                </div>
                            </div>
                        </div>
                    ) : (
                        inventoryOverview.map((item) => (
                            <div
                                className="inventory-item"
                                key={item.id}
                            >
                                <div className="inventory-info">
                                    <div className="inventory-icon">
                                        <span className="material-symbols-outlined">
                                            {inventoryIcon(item)}
                                        </span>
                                    </div>

                                    <div className="inventory-text">
                                        <strong>{item.name}</strong>
                                        <p>
                                            {Number(item.quantity) || 0}{" "}
                                            {item.unit || "unit"}
                                            {Number(item.quantity) === 1
                                                ? ""
                                                : "s"}{" "}
                                            Available
                                        </p>
                                    </div>
                                </div>

                                <span
                                    className={`inventory-status ${item.stockStatus.className}`}
                                >
                                    {item.stockStatus.label}
                                </span>
                            </div>
                        ))
                    )}
                </div>
            </article>

            <article className="dashboard-card recommendation-card recommendation-sync-card">
                <div className="card-title recommendation-sync-title">
                    <div>
                        <h3>Crop Recommendation</h3>
                        <small>Same ranking used by Farm Intelligence</small>
                    </div>

                    {recommendation && (
                        <span
                            className={`recommendation-sync-suitability ${String(
                                recommendation.suitability || ""
                            )
                                .toLowerCase()
                                .replaceAll(" ", "-")}`}
                        >
                            {recommendation.suitability}
                        </span>
                    )}
                </div>

                <div className="recommendation-body">
                    <div className="recommendation-content">
                        {recommendation ? (
                            <>
                                <div className="recommendation-sync-name-row">
                                    <h2>{recommendation.name}</h2>
                                    <strong>{Math.round(Number(recommendation.score) || 0)}%</strong>
                                </div>

                                <div
                                    className="recommendation-sync-score-track"
                                    aria-label={`Recommendation score ${Math.round(
                                        Number(recommendation.score) || 0
                                    )} percent`}
                                >
                                    <span
                                        style={{
                                            width: `${Math.max(
                                                0,
                                                Math.min(
                                                    100,
                                                    Number(recommendation.score) || 0
                                                )
                                            )}%`,
                                        }}
                                    />
                                </div>

                                <span className="recommendation-sync-origin">
                                    {recommendation.evidenceLevel || "Limited evidence"}
                                </span>

                                <p>
                                    {recommendation.notes ||
                                        "Recommended from the same season, weather, farm crop history, and inventory conditions used in Farm Intelligence."}
                                </p>

                                <ul>
                                    {recommendationReasons.length > 0 ? (
                                        recommendationReasons.map((reason) => (
                                            <li key={reason}>
                                                <span className="material-symbols-outlined">
                                                    check_circle
                                                </span>
                                                <span>{reason}</span>
                                            </li>
                                        ))
                                    ) : (
                                        <li>
                                            <span className="material-symbols-outlined">
                                                info
                                            </span>
                                            <span>
                                                Open Farm Intelligence for the full recommendation explanation.
                                            </span>
                                        </li>
                                    )}
                                </ul>

                                <div className="recommendation-sync-footer">
                                    <span>
                                        {recommendation.farmStatus ||
                                            "Farm recommendation data available"}
                                    </span>
                                    <a
                                        className="recommendation-view-link"
                                        href="/intelligence"
                                    >
                                        View Farm Intelligence
                                        <span className="material-symbols-outlined">
                                            arrow_forward
                                        </span>
                                    </a>
                                </div>
                            </>
                        ) : (
                            <>
                                <h2>No recommendation available</h2>
                                <p>
                                    Farm Intelligence does not currently have enough crop-guide data to rank a crop for these conditions.
                                </p>
                            </>
                        )}
                    </div>
                </div>
            </article>

            {showFarmTip && (
                <div className="farm-tips-banner">
                    <div className="tips-content">
                        <span className="material-symbols-outlined tip-icon">
                            notifications_active
                        </span>

                        <span>
                            <strong>Farm Tips:</strong>{" "}
                            {farmTip}
                        </span>
                    </div>

                    <button
                        type="button"
                        className="close-banner-btn"
                        aria-label="Close farm tip"
                        onClick={() => setShowFarmTip(false)}
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </div>
            )}
        </>
    );
}

export default DashboardExtras;
