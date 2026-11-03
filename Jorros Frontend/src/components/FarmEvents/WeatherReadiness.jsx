"use client";

import { useId, useState } from "react";
import { useAuth } from "../../context/AuthContext.jsx";
import { eventCreatePath } from "./eventView.js";
import { weatherSignals } from "../../services/weatherPolicy.js";
import { DEFAULT_FARM_TIMEZONE, farmDateKey } from "../../utils/farmCalendar.js";
import "./FarmEvents.css";
import "./WeatherReadiness.css";

function weatherTime(value, short = false) {
    if (!value || Number.isNaN(new Date(value).getTime())) return "Unknown";
    return new Intl.DateTimeFormat("en-PH", {
        timeZone: DEFAULT_FARM_TIMEZONE,
        ...(short ? {} : { month: "short", day: "numeric", year: "numeric" }),
        hour: "numeric", minute: "2-digit",
    }).format(new Date(value));
}

export default function WeatherReadiness({ weather, error, settings }) {
    const { hasPermission } = useAuth();
    const [detailsOpen, setDetailsOpen] = useState(false);
    const detailsId = useId();
    const signals = weatherSignals(weather, settings);
    const official = (weather?.officialAlerts || []).filter((x) => new Date(x.ends_at).getTime() > Date.now());
    const stale = !weather || ["Stale", "Unknown", "Unavailable"].includes(weather.dataStatus) || Boolean(error);
    const needsReview = signals.length > 0 || official.length > 0;
    const canReview = hasPermission("workforce:manage");
    const reviewPath = (warning) => eventCreatePath({
        kind: "Emergency Suspension", date: farmDateKey(),
        title: warning ? `Review: ${warning.event}` : "Weather work review",
        source: warning?.source || "OpenWeather / manual review", reference: warning?.reference || "",
        reason: warning ? `${warning.event}. Valid ${warning.starts_at} to ${warning.ends_at}. ${warning.description}` : signals.join("; "),
    });
    const feedStatus = weather?.officialAlertsStatus || "Unavailable";

    return (
        <section className={`weather-readiness ${stale ? "weather-data-stale" : ""} ${needsReview ? "has-advisory" : ""}`} aria-label="Weather status and official advisories">
            <div className="weather-status-row">
                <div className="weather-status-copy" aria-live="polite" aria-atomic="true">
                    <span className="weather-data-badge">
                        <span className="material-symbols-outlined" aria-hidden="true">{stale ? "info" : "schedule"}</span>
                        {stale ? "Weather needs verification" : `${weather.dataStatus} weather`}
                    </span>
                    {weather?.location && <span className="weather-status-location">{weather.location}</span>}
                    <span className="weather-status-time" title={`Observed ${weatherTime(weather?.current?.observedAt)}`}>
                        Observed {weatherTime(weather?.current?.observedAt, true)}
                    </span>
                </div>
                <div className="weather-status-actions">
                    {needsReview && canReview && <a className="workforce-button secondary" href={reviewPath(official[0])}>Review Farm Work</a>}
                    <button type="button" className="weather-details-toggle" aria-expanded={detailsOpen} aria-controls={detailsId} onClick={() => setDetailsOpen((open) => !open)}>
                        Details<span className="material-symbols-outlined" aria-hidden="true">{detailsOpen ? "expand_less" : "expand_more"}</span>
                    </button>
                </div>
            </div>

            {signals.length > 0 && <p className="weather-attention-summary"><span className="material-symbols-outlined" aria-hidden="true">warning</span>{signals.join(" · ")}</p>}

            {official.map((warning) => (
                <details className="weather-official-warning" key={warning.id}>
                    <summary><span className="material-symbols-outlined" aria-hidden="true">warning</span><span><strong>{warning.event}</strong><small>{warning.source} · Until {weatherTime(warning.ends_at)}</small></span><span className="material-symbols-outlined weather-advisory-chevron" aria-hidden="true">expand_more</span></summary>
                    <div className="weather-advisory-body">
                        <p>{warning.source} via {warning.provider} · {warning.location}</p>
                        <p>Valid: {weatherTime(warning.starts_at)} → {weatherTime(warning.ends_at)}</p>
                        <p className="farm-event-preserve">{warning.description}</p>
                        {canReview && <a className="workforce-button secondary" href={reviewPath(warning)}>Review This Advisory</a>}
                    </div>
                </details>
            ))}

            <div id={detailsId} className="weather-expanded-details" hidden={!detailsOpen}>
                <dl className="weather-details-grid">
                    <div><dt>Source</dt><dd>{weather?.source || "OpenWeather"}</dd></div>
                    <div><dt>Observed</dt><dd>{weatherTime(weather?.current?.observedAt)}</dd></div>
                    <div><dt>Last fetched</dt><dd>{weatherTime(weather?.fetchedAt)}</dd></div>
                    <div><dt>Configured coordinates</dt><dd>{weather?.latitude != null && weather?.longitude != null ? `${weather.latitude}, ${weather.longitude}` : "Not available"}</dd></div>
                    <div><dt>Wind gusts</dt><dd>{weather?.current?.windGustKph != null ? `${weather.current.windGustKph} km/h` : "Not supplied"}</dd></div>
                    <div><dt>Official warning feed</dt><dd>{feedStatus}</dd></div>
                </dl>
                {stale && <p className="weather-detail-message">{error || weather?.lastFetchError || "The current observation could not be verified. Manual declarations remain available while offline."}</p>}
                {feedStatus === "Available" && !official.length && <p>No active warning was returned for the configured coordinates.</p>}
                <p className="weather-source-note">Verify current PAGASA and LGU advisories for the farm's location. Weather readings do not identify a typhoon track or declare work safe. Work changes require Owner/Admin approval.</p>
                {!needsReview && canReview && <a className="workforce-button secondary" href={reviewPath()}>Review Farm Work</a>}
            </div>
        </section>
    );
}
