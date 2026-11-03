"use client";

import { useEffect, useMemo, useState } from "react";
import { useAuth } from "../../../context/AuthContext.jsx";
import { trendAnalyticsService } from "../../../services/trendAnalyticsService.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";

function formatNumber(value, digits = 2) {
    if (value == null || value === "") return "N/A";
    const number = Number(value);
    if (!Number.isFinite(number)) return "N/A";
    return number.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function formatValue(value, unit = "") {
    if (value == null || value === "") return "N/A";
    const number = Number(value);
    if (!Number.isFinite(number)) return "N/A";
    const normalizedUnit = String(unit || "").trim().toUpperCase();

    if (normalizedUnit === "PHP") {
        return `₱${number.toLocaleString("en-PH", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        })}`;
    }
    if (normalizedUnit === "%") return `${formatNumber(number, 1)}%`;
    if (normalizedUnit) return `${formatNumber(number)} ${unit}`;
    return formatNumber(number);
}

function severityClass(value) {
    return String(value || "low").trim().toLowerCase();
}

function comparisonRows(comparison) {
    const rows = comparison?.rows || comparison?.metrics || [];
    return Array.isArray(rows) ? rows : [];
}

function displayMetricName(value) {
    return String(value || "")
        .replaceAll("_", " ")
        .replace(/\b\w/g, (character) => character.toUpperCase());
}

function varianceReferenceText(item) {
    const label = String(item?.label || item?.metric || "").toLowerCase();
    if (label.includes("harvest schedule variance")) {
        const amount = Number(item?.actual || item?.variance || 0);
        if (Math.abs(amount) < 0.005) return "Harvest timing matched the expected schedule.";
        return `Average harvest timing was ${Math.abs(amount).toFixed(2)} day(s) ${amount > 0 ? "later" : "earlier"} than the expected harvest dates.`;
    }
    return `Actual ${formatValue(item?.actual, item?.unit)} · ${item?.reference_label || "Reference"} ${formatValue(item?.reference, item?.unit)}`;
}

export default function OverviewPanel({ onNavigate }) {
    const { hasPermission } = useAuth();
    const canViewProductionSales = hasPermission?.("production_sales:view") === true;
    const [months, setMonths] = useState(12);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [updating, setUpdating] = useState(false);
    const [refreshVersion, setRefreshVersion] = useState(0);
    useFarmModuleUpdates(["intelligence", "crops", "livestock", "inventory", "weather"],
        () => setRefreshVersion((value) => value + 1));

    useEffect(() => {
        let cancelled = false;
        async function load() {
            try {
                if (!data) setLoading(true);
                else setUpdating(true);
                setError("");
                const result = await trendAnalyticsService.getOverview(months);
                if (!cancelled) setData(result);
            } catch (loadError) {
                console.error("Unable to load Farm Intelligence overview:", loadError);
                if (!cancelled) {
                    setError(loadError?.message || "Unable to load the farm decision overview.");
                }
            } finally {
                if (!cancelled) { setLoading(false); setUpdating(false); }
            }
        }
        load();
        return () => { cancelled = true; };
    }, [months, refreshVersion]);

    const riskSummary = data?.risk_summary || {};
    const risks = data?.risk_flags || [];
    const kpis = data?.executive_kpis || [];
    const variance = data?.performance_variance || [];
    const readiness = data?.data_readiness || {};
    const salesSignals = data?.sales_signals || [];
    const reproduction = data?.reproduction_signals || {};
    const actions = data?.management_actions || [];
    const findings = data?.findings || [];
    const comparisons = useMemo(
        () => comparisonRows(data?.comparison).slice(0, 10),
        [data?.comparison]
    );

    if (loading) {
        return (
            <section className="fi-card fi-trends-state">
                <span className="material-symbols-outlined">progress_activity</span>
                <p>Building the live farm decision overview...</p>
            </section>
        );
    }

    if (error && !data) {
        return (
            <section className="fi-card fi-trends-state error">
                <span className="material-symbols-outlined">error</span>
                <p>{error}</p>
            </section>
        );
    }

    return (
        <div className="fi-stack fi-overview-panel">
            {updating && <div role="status" className="fi-card">Updating farm insights…</div>}
            {error && <div role="status" className="fi-card">Latest update failed: {error}</div>}
            <section className="fi-card fi-decision-hero">
                <div className="fi-decision-hero-copy">
                    <div className="fi-decision-status-row">
                        <h2>Farm Decision Overview</h2>
                        <span className={`fi-decision-status ${severityClass(riskSummary.status_level)}`}>
                            {riskSummary.status || "Stable"}
                        </span>
                    </div>
                    <p>{riskSummary.message}</p>
                    <div className="fi-decision-period-copy">
                        Analysis period: {data?.period?.start_date || "—"} to {data?.period?.end_date || "—"}
                    </div>
                </div>

                <label className="fi-trends-period">
                    <span>Decision Period</span>
                    <select value={months} onChange={(event) => setMonths(Number(event.target.value))}>
                        <option value={3}>Last 3 months</option>
                        <option value={6}>Last 6 months</option>
                        <option value={12}>Last 12 months</option>
                        <option value={24}>Last 24 months</option>
                        <option value={36}>Last 36 months</option>
                    </select>
                </label>
            </section>

            <section className="fi-overview-kpis">
                {kpis.map((item, index) => (
                    <article className="fi-card fi-overview-kpi" key={`${item.label}-${index}`}>
                        <small>{item.label}</small>
                        <strong>{formatValue(item.value, item.unit)}</strong>
                        {item.note && <p>{item.note}</p>}
                    </article>
                ))}
            </section>

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>Production &amp; Sales Signals</h3>
                        <p>Crop and livestock sales are kept separate while financial totals remain farm-wide.</p>
                    </div>
                    {canViewProductionSales && (
                        <a className="fi-secondary-button fi-link-button" href="/production-sales">
                            <span className="material-symbols-outlined">point_of_sale</span>
                            Open Production &amp; Sales
                        </a>
                    )}
                </div>
                <div className="fi-signal-grid">
                    {salesSignals.map((item) => (
                        <article key={item.label}>
                            <small>{item.label}</small>
                            <strong>{formatValue(item.value, item.unit)}</strong>
                        </article>
                    ))}
                </div>
            </section>

            <section className="fi-overview-grid">
                <article className="fi-card">
                    <div className="fi-section-heading fi-heading-row">
                        <div>
                            <h3>What Needs Attention Now</h3>
                            <p>Risk flags use the same rules as the Farm Performance Report.</p>
                        </div>
                        <span className="fi-count-chip">
                            {riskSummary.high || 0} high · {riskSummary.medium || 0} medium
                        </span>
                    </div>

                    <div className="fi-risk-list fi-scroll-region fi-risk-scroll">
                        {risks.length > 0 ? risks.map((risk, index) => {
                            const severity = risk.severity || risk.level || "Low";
                            return (
                                <article className={`fi-risk-item ${severityClass(severity)}`} key={`${risk.area}-${index}`}>
                                    <div className="fi-risk-title-row">
                                        <span>{severity}</span>
                                        <strong>{risk.area || risk.category || "Farm"}</strong>
                                    </div>
                                    <p>{risk.issue || risk.message || risk.finding}</p>
                                    {(risk.action || risk.recommendation) && <small>{risk.action || risk.recommendation}</small>}
                                </article>
                            );
                        }) : (
                            <div className="fi-trend-empty">No active risk flags were returned.</div>
                        )}
                    </div>
                </article>

                <article className="fi-card">
                    <div className="fi-section-heading">
                        <h3>Data Readiness</h3>
                        <p>Shows whether enough historical records exist for stronger trend interpretation.</p>
                    </div>
                    <div className="fi-readiness-summary">
                        <strong>{readiness.checks_passed || 0}/{readiness.checks_total || 0}</strong>
                        <span>minimum history checks passed</span>
                    </div>
                    <div className="fi-readiness-list fi-scroll-region fi-readiness-scroll">
                        {(readiness.checks || []).map((item) => (
                            <div key={item.key}>
                                <span className={`material-symbols-outlined ${item.ready ? "ready" : "missing"}`}>
                                    {item.ready ? "check_circle" : "info"}
                                </span>
                                <div>
                                    <strong>{item.label}</strong>
                                    <small>{item.count} record(s) · recommended minimum {item.recommended_minimum}</small>
                                </div>
                            </div>
                        ))}
                    </div>
                    {(data?.data_quality || []).length > 0 && (
                        <div className="fi-data-quality-note">
                            <span className="material-symbols-outlined">data_alert</span>
                            <p>{data.data_quality.length} data-quality notice(s) should be considered before final decisions.</p>
                        </div>
                    )}
                </article>
            </section>

            {reproduction.has_data && (
                <section className="fi-card">
                    <div className="fi-section-heading fi-heading-row">
                        <div>
                            <h3>Reproduction Signals</h3>
                            <p>Uses recorded breeding, pregnancy/incubation, birth/hatch, and offspring outcomes.</p>
                        </div>
                        <a className="fi-secondary-button fi-link-button" href="/livestock">
                            <span className="material-symbols-outlined">family_history</span>
                            Open Livestock
                        </a>
                    </div>
                    <div className="fi-signal-grid compact">
                        <article><small>Reproduction Events</small><strong>{formatNumber(reproduction.events, 0)}</strong></article>
                        <article><small>Offspring Recorded</small><strong>{formatNumber(reproduction.offspring_recorded, 0)}</strong></article>
                        <article><small>Alive Offspring</small><strong>{formatNumber(reproduction.alive_offspring, 0)}</strong></article>
                        <article><small>Offspring Survival</small><strong>{reproduction.offspring_survival_percent == null ? "N/A" : `${formatNumber(reproduction.offspring_survival_percent, 1)}%`}</strong></article>
                    </div>
                </section>
            )}

            <section className="fi-card">
                <div className="fi-section-heading fi-heading-row">
                    <div>
                        <h3>Performance vs Previous Period</h3>
                        <p>Compares period-based farm results with {data?.previous_period?.start_date || "—"} to {data?.previous_period?.end_date || "—"}.</p>
                    </div>
                    {onNavigate && (
                        <button type="button" className="fi-secondary-button" onClick={() => onNavigate("trends")}>
                            <span className="material-symbols-outlined">query_stats</span>
                            Open Trends
                        </button>
                    )}
                </div>

                <div className="fi-trend-table-wrap fi-comparison-scroll">
                    <table className="fi-trend-table">
                        <thead>
                            <tr><th>Metric</th><th>Current</th><th>Previous</th><th>Change</th><th>Direction</th></tr>
                        </thead>
                        <tbody>
                            {comparisons.length > 0 ? comparisons.map((row, index) => {
                                const comparable = row.comparable !== false && row.previous != null;
                                return (
                                    <tr key={`${row.metric || row.key}-${index}`}>
                                        <td><strong>{row.label || displayMetricName(row.metric || row.key)}</strong></td>
                                        <td>{formatNumber(row.current ?? row.current_value)}</td>
                                        <td>{comparable ? formatNumber(row.previous ?? row.previous_value) : "N/A"}</td>
                                        <td>
                                            {!comparable ? "N/A" : row.percent_change != null
                                                ? `${Number(row.percent_change) >= 0 ? "+" : ""}${formatNumber(row.percent_change, 1)}%`
                                                : formatNumber(row.change ?? row.difference)}
                                        </td>
                                        <td>{!comparable ? "No comparable history" : row.interpretation || row.direction || "—"}</td>
                                    </tr>
                                );
                            }) : (
                                <tr><td colSpan="5" className="fi-trend-empty">No comparable period metrics are available yet.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="fi-overview-grid">
                <article className="fi-card">
                    <div className="fi-section-heading">
                        <h3>Performance &amp; Variance</h3>
                        <p>Actual values compared with recorded plans, expected schedules, or biological references where available.</p>
                    </div>
                    <div className="fi-variance-list fi-scroll-region fi-variance-scroll">
                        {variance.length > 0 ? variance.map((item, index) => (
                            <div key={`${item.metric || item.label}-${index}`}>
                                <strong>{item.label || displayMetricName(item.metric)}</strong>
                                <span className={`fi-variance-assessment ${item.assessment || "neutral"}`}>
                                    {item.variance_percent == null
                                        ? `${Number(item.variance || 0) >= 0 ? "+" : ""}${formatNumber(item.variance, 2)} ${item.unit || ""}`
                                        : `${Number(item.variance_percent) >= 0 ? "+" : ""}${formatNumber(item.variance_percent, 1)}%`}
                                </span>
                                <small>{varianceReferenceText(item)}</small>
                            </div>
                        )) : (
                            <div className="fi-trend-empty">No defensible variance baseline is available for this period.</div>
                        )}
                    </div>
                </article>

                <article className="fi-card">
                    <div className="fi-section-heading">
                        <h3>Recommended Management Actions</h3>
                        <p>Actions are generated from recorded farm performance, risks, comparisons, and data quality.</p>
                    </div>
                    <div className="fi-action-list fi-scroll-region fi-action-scroll">
                        {actions.length > 0 ? actions.map((item, index) => (
                            <article className="fi-action-item" key={`${index}-${item.text}`}>
                                <div>
                                    <strong>{item.area || "Farm"}</strong>
                                    <p>{item.text}</p>
                                </div>
                                <a href={item.href || "/dashboard"}>{item.link_label || "Open Source"}</a>
                            </article>
                        )) : (
                            <div className="fi-trend-empty">No additional management action is required from the recorded data.</div>
                        )}
                    </div>
                </article>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading">
                    <h3>Key Findings</h3>
                    <p>Concise observations from the same analytics used by formal Farm Performance reports.</p>
                </div>
                <div className="fi-findings-grid fi-scroll-region fi-findings-scroll">
                    {findings.map((item, index) => (
                        <article key={`${index}-${typeof item === "string" ? item : item?.finding || item?.text}`}>
                            <span className="material-symbols-outlined">insights</span>
                            <p>{typeof item === "string" ? item : item?.finding || item?.text || item?.message || JSON.stringify(item)}</p>
                        </article>
                    ))}
                </div>
            </section>
        </div>
    );
}
