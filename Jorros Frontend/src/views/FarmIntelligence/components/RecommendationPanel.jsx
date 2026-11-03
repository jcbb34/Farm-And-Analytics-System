"use client";

import {
    useEffect,
    useMemo,
    useState,
} from "react";

import {
    MONTHS,
    PHILIPPINE_REGIONS,
    getPhilippineSeason,
} from "../../../data/philippinesCropGuide.js";

import { cropService } from "../../../services/cropService.js";
import { livestockService } from "../../../services/livestockService.js";
import { inventoryService } from "../../../services/inventoryService.js";
import { weatherService } from "../../../services/weatherService.js";
import { alertService } from "../../../services/alertService.js";
import { activityService } from "../../../services/activityService.js";

import {
    applyWeatherToConditions,
    buildCropRecommendations,
    buildLiveInsights,
    getStoredRecommendationConditions,
    saveRecommendationConditions,
} from "../../../services/cropRecommendationEngine.js";

import {
    notifySuccess,
    notifyWarning,
} from "../../../context/NotificationContext.jsx";

const emptyLiveData = {
    crops: [],
    livestock: [],
    inventory: [],
    weather: null,
    alerts: [],
    activities: [],
};

function RecommendationPanel() {
    const [form, setForm] = useState(
        getStoredRecommendationConditions
    );
    const [liveData, setLiveData] = useState(
        emptyLiveData
    );
    const [loading, setLoading] = useState(true);
    const [loadMessage, setLoadMessage] =
        useState("");

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            setLoading(true);
            setLoadMessage("");

            const results =
                await Promise.allSettled([
                    cropService.getCrops(false, true),
                    livestockService.getLivestock(false),
                    inventoryService.getInventory(false),
                    weatherService.getWeather(),
                    alertService.getAlerts(),
                    activityService.getActivities(false),
                ]);

            if (cancelled) {
                return;
            }

            const valueOr = (
                result,
                fallback
            ) =>
                result.status === "fulfilled"
                    ? result.value
                    : fallback;

            const nextData = {
                crops: valueOr(results[0], []),
                livestock: valueOr(
                    results[1],
                    []
                ),
                inventory: valueOr(
                    results[2],
                    []
                ),
                weather: valueOr(
                    results[3],
                    null
                ),
                alerts: valueOr(results[4], []),
                activities: valueOr(
                    results[5],
                    []
                ),
            };

            const failedCount = results.filter(
                (result) =>
                    result.status === "rejected"
            ).length;

            if (failedCount > 0) {
                setLoadMessage(
                    `${failedCount} live data source(s) could not be loaded. Available farm data is still being used.`
                );
            }

            setLiveData(nextData);

            setForm((current) => {
                const nextConditions =
                    applyWeatherToConditions(
                        current,
                        nextData.weather
                    );

                saveRecommendationConditions(
                    nextConditions
                );

                return nextConditions;
            });

            setLoading(false);
        };

        load();

        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        saveRecommendationConditions(form);
    }, [form]);

    const recommendations = useMemo(
        () =>
            buildCropRecommendations(
                form,
                liveData
            ),
        [form, liveData]
    );

    const liveInsights = useMemo(
        () => buildLiveInsights(liveData),
        [liveData]
    );

    const season = useMemo(
        () => getPhilippineSeason(form.month),
        [form.month]
    );

    const topRecommendations =
        recommendations.slice(0, 6);

    const handleChange = (event) => {
        const { name, value } = event.target;
        const numeric =
            name === "month" ||
            name === "temperature";
        const changesWeatherInput = [
            "month",
            "rainfall",
            "temperature",
        ].includes(name);

        setForm((current) => ({
            ...current,
            [name]: numeric
                ? Number(value)
                : value,
            useLiveWeather:
                changesWeatherInput
                    ? false
                    : current.useLiveWeather,
        }));
    };

    const applyLiveWeather = () => {
        if (!liveData.weather) {
            notifyWarning(
                "Live weather is not available right now."
            );
            return;
        }

        setForm((current) =>
            applyWeatherToConditions(
                {
                    ...current,
                    useLiveWeather: true,
                },
                liveData.weather
            )
        );

        notifySuccess(
            "Current OpenWeather conditions were applied. The Dashboard now uses the same crop recommendation conditions."
        );
    };

    return (
        <div className="fi-stack">
            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>Recommended Crops</h3>
                        <p>
                            This ranking is the single source used by both Farm Intelligence and the Dashboard.
                        </p>
                    </div>

                    <span className="fi-count-chip">
                        {loading
                            ? "Loading..."
                            : `${topRecommendations.length} suggestions`}
                    </span>
                </div>

                <div className="fi-recommendation-grid">
                    {loading ? (
                        <article className="fi-crop-card best">
                            <div className="fi-crop-top">
                                <span className="fi-crop-icon">
                                    <span className="material-symbols-outlined">
                                        sync
                                    </span>
                                </span>
                                <span className="fi-suitability conditional">
                                    Loading
                                </span>
                            </div>

                            <div className="fi-crop-title-row">
                                <div>
                                    <h4>
                                        Building recommendations
                                    </h4>
                                    <p>
                                        Reading crop, inventory, weather, and farm performance records.
                                    </p>
                                </div>
                            </div>
                        </article>
                    ) : topRecommendations.length ===
                      0 ? (
                        <article className="fi-crop-card">
                            <div className="fi-crop-title-row">
                                <div>
                                    <h4>
                                        No recommendation available
                                    </h4>
                                    <p>
                                        Check the crop guide and farm data sources.
                                    </p>
                                </div>
                            </div>
                        </article>
                    ) : (
                        topRecommendations.map(
                            (crop, index) => (
                                <article
                                    key={crop.id}
                                    className={`fi-crop-card ${
                                        index === 0
                                            ? "best"
                                            : ""
                                    }`}
                                >
                                    <div className="fi-crop-top">
                                        <span className="fi-crop-icon">
                                            <span className="material-symbols-outlined">
                                                {crop.icon}
                                            </span>
                                        </span>

                                        <span
                                            className={`fi-suitability ${crop.suitability
                                                .toLowerCase()
                                                .replaceAll(
                                                    " ",
                                                    "-"
                                                )}`}
                                        >
                                            {
                                                crop.suitability
                                            }
                                        </span>
                                    </div>

                                    <div className="fi-crop-title-row">
                                        <div>
                                            <h4>
                                                {crop.name}
                                            </h4>
                                            <p>
                                                {
                                                    crop.cycleDays
                                                }
                                            </p>
                                        </div>

                                        <strong>
                                            {crop.score}%
                                        </strong>
                                    </div>

                                    <div className="fi-score-track">
                                        <span
                                            style={{
                                                width: `${crop.score}%`,
                                            }}
                                        />
                                    </div>

                                    <p className="fi-crop-notes">
                                        <strong>
                                            {
                                                crop.farmStatus
                                            }
                                        </strong>
                                    </p>

                                    <div className="fi-evidence-line">
                                        <span className="material-symbols-outlined">verified</span>
                                        <span>{crop.evidenceLevel}</span>
                                        <small>{(crop.evidenceSources || []).join(" · ")}</small>
                                    </div>

                                    <p className="fi-crop-notes">
                                        {crop.notes}
                                    </p>

                                    <ul className="fi-reasons">
                                        {crop.reasons
                                            .slice(0, 4)
                                            .map(
                                                (
                                                    reason,
                                                    reasonIndex
                                                ) => (
                                                    <li
                                                        key={`${crop.id}-${reasonIndex}-${reason}`}
                                                    >
                                                        {
                                                            reason
                                                        }
                                                    </li>
                                                )
                                            )}
                                    </ul>

                                    <div className="fi-crop-meta">
                                        <span>
                                            Water:{" "}
                                            {
                                                crop.waterNeed
                                            }
                                        </span>
                                        <span>
                                            {
                                                crop.temperature?.[0]
                                            }
                                            –
                                            {
                                                crop.temperature?.[1]
                                            }
                                            °C
                                        </span>
                                    </div>
                                </article>
                            )
                        )
                    )}
                </div>
            </section>

            <section className="fi-card fi-season-hero">
                <div className="fi-season-copy">
                    <span className="fi-eyebrow">
                        Live Joross Farm decision support
                    </span>

                    <h2>{season.name}</h2>

                    <p>
                        {season.description}{" "}
                        Crop suitability combines Philippine seasonal rules with the selected Bicol farm conditions, live weather when enabled, current Joross crops, matching crop history, and inventory availability.
                    </p>

                    <div className="fi-disclaimer">
                        <span className="material-symbols-outlined">
                            info
                        </span>
                        <span>
                            This is rule-based decision support, not a guarantee of crop performance. New crops are clearly marked so they can be trialed before wider planting.
                        </span>
                    </div>

                    {loadMessage && (
                        <div className="fi-disclaimer">
                            <span className="material-symbols-outlined">
                                warning
                            </span>
                            <span>
                                {loadMessage}
                            </span>
                        </div>
                    )}
                </div>

                <div className="fi-season-icon">
                    <span className="material-symbols-outlined">
                        psychology_alt
                    </span>
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>
                            Live Farm Intelligence
                        </h3>
                        <p>
                            Current operational signals calculated from connected system records.
                        </p>
                    </div>

                    <span className="fi-count-chip">
                        {loading
                            ? "Loading..."
                            : "Live data"}
                    </span>
                </div>

                <div className="fi-recommendation-grid">
                    {loading ? (
                        <article className="fi-crop-card">
                            <div className="fi-crop-top">
                                <span className="fi-crop-icon">
                                    <span className="material-symbols-outlined">
                                        sync
                                    </span>
                                </span>
                                <span className="fi-suitability conditional">
                                    Loading
                                </span>
                            </div>
                        </article>
                    ) : (
                        liveInsights.map(
                            (insight) => (
                                <article
                                    className="fi-crop-card"
                                    key={
                                        insight.id
                                    }
                                >
                                    <div className="fi-crop-top">
                                        <span className="fi-crop-icon">
                                            <span className="material-symbols-outlined">
                                                {
                                                    insight.icon
                                                }
                                            </span>
                                        </span>
                                        <span
                                            className={`fi-suitability ${insight.suitability
                                                .toLowerCase()
                                                .replaceAll(
                                                    " ",
                                                    "-"
                                                )}`}
                                        >
                                            {
                                                insight.suitability
                                            }
                                        </span>
                                    </div>

                                    <div className="fi-crop-title-row">
                                        <div>
                                            <h4>
                                                {
                                                    insight.title
                                                }
                                            </h4>
                                            <p>
                                                {
                                                    insight.note
                                                }
                                            </p>
                                        </div>
                                        <strong>
                                            {
                                                insight.metric
                                            }
                                        </strong>
                                    </div>

                                    {insight.reasons
                                        ?.length >
                                        0 && (
                                        <ul className="fi-reasons">
                                            {insight.reasons.map(
                                                (
                                                    reason,
                                                    index
                                                ) => (
                                                    <li
                                                        key={`${insight.id}-${index}-${reason}`}
                                                    >
                                                        {
                                                            reason
                                                        }
                                                    </li>
                                                )
                                            )}
                                        </ul>
                                    )}
                                </article>
                            )
                        )
                    )}
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>Farm Conditions</h3>
                        <p>
                            These values are saved and shared with the Dashboard recommendation card.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="fi-secondary-button"
                        onClick={applyLiveWeather}
                        disabled={!liveData.weather}
                    >
                        <span className="material-symbols-outlined">
                            partly_cloudy_day
                        </span>
                        Use Live Weather
                    </button>
                </div>

                <div className="fi-form-grid">
                    <label>
                        <span>Month</span>
                        <select
                            name="month"
                            value={form.month}
                            onChange={handleChange}
                        >
                            {MONTHS.map(
                                (
                                    monthName,
                                    index
                                ) => (
                                    <option
                                        key={
                                            monthName
                                        }
                                        value={
                                            index + 1
                                        }
                                    >
                                        {
                                            monthName
                                        }
                                    </option>
                                )
                            )}
                        </select>
                    </label>

                    <label>
                        <span>Region</span>
                        <select
                            name="region"
                            value={form.region}
                            onChange={handleChange}
                        >
                            {PHILIPPINE_REGIONS.map(
                                (region) => (
                                    <option
                                        key={region}
                                        value={region}
                                    >
                                        {region}
                                    </option>
                                )
                            )}
                        </select>
                    </label>

                    <label>
                        <span>
                            Expected Rainfall
                        </span>
                        <select
                            name="rainfall"
                            value={form.rainfall}
                            onChange={handleChange}
                        >
                            <option>Low</option>
                            <option>Normal</option>
                            <option>High</option>
                        </select>
                    </label>

                    <label>
                        <span>Water Access</span>
                        <select
                            name="irrigation"
                            value={form.irrigation}
                            onChange={handleChange}
                        >
                            <option>
                                Rainfed
                            </option>
                            <option>
                                Limited Irrigation
                            </option>
                            <option>
                                Full Irrigation
                            </option>
                        </select>
                    </label>

                    <label>
                        <span>
                            Field Drainage
                        </span>
                        <select
                            name="drainage"
                            value={form.drainage}
                            onChange={handleChange}
                        >
                            <option>Good</option>
                            <option>
                                Moderate
                            </option>
                            <option>Poor</option>
                        </select>
                    </label>

                    <label>
                        <span>
                            Expected Temperature
                        </span>
                        <div className="fi-unit-field">
                            <input
                                type="number"
                                min="10"
                                max="45"
                                name="temperature"
                                value={
                                    form.temperature
                                }
                                onChange={
                                    handleChange
                                }
                            />
                            <span>°C</span>
                        </div>
                    </label>
                </div>

                <div className="fi-disclaimer">
                    <span className="material-symbols-outlined">
                        sync
                    </span>
                    <span>
                        Dashboard sync: {form.useLiveWeather
                            ? "Live weather mode is active."
                            : "Manual month/rainfall/temperature values are active."}
                    </span>
                </div>
            </section>
        </div>
    );
}

export default RecommendationPanel;
