"use client";

import { useEffect, useMemo, useState } from "react";
import { Bar, Line } from "react-chartjs-2";
import {
    BarElement,
    CategoryScale,
    Chart as ChartJS,
    Legend,
    LinearScale,
    LineElement,
    PointElement,
    Tooltip,
} from "chart.js";

import { trendAnalyticsService } from "../../../services/trendAnalyticsService.js";

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    BarElement,
    Tooltip,
    Legend
);

const TREND_CHART_COLORS = {
    green: "#2e7d32",
    greenFill: "rgba(46, 125, 50, 0.14)",
    blue: "#1976d2",
    blueFill: "rgba(25, 118, 210, 0.14)",
    purple: "#7e57c2",
    purpleFill: "rgba(126, 87, 194, 0.14)",
    teal: "#00838f",
    tealFill: "rgba(0, 131, 143, 0.14)",
    orange: "#ef8f00",
    orangeFill: "rgba(239, 143, 0, 0.16)",
};

function productionSeriesColor(seriesName, index) {
    const name = String(seriesName || "").toLowerCase();
    if (name.includes("egg")) return { border: TREND_CHART_COLORS.purple, fill: "rgba(126, 87, 194, 0.72)" };
    if (name.includes("meat")) return { border: TREND_CHART_COLORS.orange, fill: "rgba(239, 143, 0, 0.74)" };
    if (name.includes("milk")) return { border: TREND_CHART_COLORS.blue, fill: "rgba(25, 118, 210, 0.72)" };
    const fallback = [
        { border: TREND_CHART_COLORS.green, fill: "rgba(46, 125, 50, 0.72)" },
        { border: TREND_CHART_COLORS.teal, fill: "rgba(0, 131, 143, 0.72)" },
        { border: TREND_CHART_COLORS.purple, fill: "rgba(126, 87, 194, 0.72)" },
    ];
    return fallback[index % fallback.length];
}

function formatNumber(value, digits = 2) {
    if (value == null || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return number.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function formatMoney(value) {
    return `₱${Number(value || 0).toLocaleString("en-PH", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    })}`;
}

function correlationLabel(item) {
    if (item?.correlation == null) return "Needs more history";
    return `${item.strength} ${String(item.direction || "").toLowerCase()}`;
}

export default function TrendsPanel() {
    const [months, setMonths] = useState(12);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");

    useEffect(() => {
        let cancelled = false;
        async function load() {
            try {
                setLoading(true);
                setError("");
                const result = await trendAnalyticsService.getTrends(months);
                if (!cancelled) setData(result);
            } catch (loadError) {
                console.error("Unable to load trend analytics:", loadError);
                if (!cancelled) setError(loadError?.message || "Unable to load production trends.");
            } finally {
                if (!cancelled) setLoading(false);
            }
        }
        load();
        return () => { cancelled = true; };
    }, [months]);

    const monthly = data?.monthly || [];
    const coverage = data?.data_coverage || {};
    const reproduction = data?.reproduction_summary || {};

    const totals = useMemo(() => ({
        cropYield: monthly.reduce((sum, row) => sum + Number(row.crop_yield_kg || 0), 0),
        feed: monthly.reduce((sum, row) => sum + Number(row.feed_consumption_kg || 0), 0),
        grossSales: monthly.reduce((sum, row) => sum + Number(row.gross_sales_value || 0), 0),
        cropSales: monthly.reduce((sum, row) => sum + Number(row.crop_sales_value || 0), 0),
        livestockSales: monthly.reduce((sum, row) => sum + Number(row.livestock_sales_value || 0), 0),
        cashCollected: monthly.reduce((sum, row) => sum + Number(row.cash_collected || 0), 0),
    }), [monthly]);

    const cropWeatherChart = useMemo(() => ({
        labels: monthly.map((row) => row.label),
        datasets: [
            {
                label: "Crop Yield (kg)",
                data: monthly.map((row) => row.crop_yield_kg),
                yAxisID: "y",
                borderColor: TREND_CHART_COLORS.green,
                backgroundColor: TREND_CHART_COLORS.green,
                pointBackgroundColor: TREND_CHART_COLORS.green,
                pointBorderColor: "#ffffff",
                pointBorderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2.5,
                tension: 0.3,
            },
            {
                label: "Avg. Recorded Rainfall (mm)",
                data: monthly.map((row) => row.average_rainfall_mm),
                yAxisID: "y1",
                borderColor: TREND_CHART_COLORS.blue,
                backgroundColor: TREND_CHART_COLORS.blue,
                pointBackgroundColor: TREND_CHART_COLORS.blue,
                pointBorderColor: "#ffffff",
                pointBorderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2.5,
                tension: 0.3,
            },
        ],
    }), [monthly]);

    const feedGrowthChart = useMemo(() => ({
        labels: monthly.map((row) => row.label),
        datasets: [
            {
                label: "Feed Consumed (kg)",
                data: monthly.map((row) => row.feed_consumption_kg),
                yAxisID: "y",
                borderColor: TREND_CHART_COLORS.green,
                backgroundColor: TREND_CHART_COLORS.green,
                pointBackgroundColor: TREND_CHART_COLORS.green,
                pointBorderColor: "#ffffff",
                pointBorderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2.5,
                tension: 0.3,
            },
            {
                label: "Avg. Daily Gain (kg/day)",
                data: monthly.map((row) => row.average_daily_gain_kg),
                yAxisID: "y1",
                borderColor: TREND_CHART_COLORS.purple,
                backgroundColor: TREND_CHART_COLORS.purple,
                pointBackgroundColor: TREND_CHART_COLORS.purple,
                pointBorderColor: "#ffffff",
                pointBorderWidth: 2,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderWidth: 2.5,
                tension: 0.3,
            },
        ],
    }), [monthly]);

    const salesChart = useMemo(() => ({
        labels: monthly.map((row) => row.label),
        datasets: [
            {
                label: "Crop Sales (PHP)",
                data: monthly.map((row) => row.crop_sales_value),
                borderColor: TREND_CHART_COLORS.green,
                backgroundColor: TREND_CHART_COLORS.green,
                pointBackgroundColor: TREND_CHART_COLORS.green,
                borderWidth: 2.5,
                pointRadius: 3,
                tension: 0.3,
            },
            {
                label: "Livestock Sales (PHP)",
                data: monthly.map((row) => row.livestock_sales_value),
                borderColor: TREND_CHART_COLORS.blue,
                backgroundColor: TREND_CHART_COLORS.blue,
                pointBackgroundColor: TREND_CHART_COLORS.blue,
                borderWidth: 2.5,
                pointRadius: 3,
                tension: 0.3,
            },
            {
                label: "Cash Collected (PHP)",
                data: monthly.map((row) => row.cash_collected),
                borderColor: TREND_CHART_COLORS.teal,
                backgroundColor: TREND_CHART_COLORS.teal,
                pointBackgroundColor: TREND_CHART_COLORS.teal,
                borderWidth: 2.5,
                pointRadius: 3,
                tension: 0.3,
            },
        ],
    }), [monthly]);

    const productionChart = useMemo(() => {
        const series = data?.production_series || [];
        return {
            labels: monthly.map((row) => row.label),
            datasets: series.map((seriesName, index) => {
                const color = productionSeriesColor(seriesName, index);
                return {
                    label: seriesName,
                    data: monthly.map((row) => Number(row.production?.[seriesName] || 0)),
                    borderColor: color.border,
                    backgroundColor: color.fill,
                    borderWidth: 1.5,
                    borderRadius: 5,
                    maxBarThickness: 34,
                };
            }),
        };
    }, [data?.production_series, monthly]);

    const seasonalInsight = useMemo(() => {
        const rows = (data?.seasonal || []).filter((row) => Number(row.crop_yield_kg || 0) > 0);
        return rows.length > 0
            ? [...rows].sort((a, b) => Number(b.crop_yield_kg || 0) - Number(a.crop_yield_kg || 0))[0]
            : null;
    }, [data?.seasonal]);

    const strongestFactor = useMemo(() => {
        const rows = (data?.factor_analysis || []).filter((row) => row.correlation != null);
        return rows.length > 0
            ? [...rows].sort((a, b) => Math.abs(Number(b.correlation || 0)) - Math.abs(Number(a.correlation || 0)))[0]
            : null;
    }, [data?.factor_analysis]);

    const topCrop = data?.top_crops?.[0] || null;

    const chartLegend = {
        labels: {
            color: "#526159",
            usePointStyle: true,
            pointStyle: "circle",
            boxWidth: 9,
            boxHeight: 9,
            padding: 16,
            font: { size: 12, weight: "600" },
        },
    };

    const chartGrid = { color: "rgba(22, 101, 52, 0.10)", drawBorder: false };
    const chartTicks = { color: "#6b756f", font: { size: 11 } };

    const dualAxisOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: chartLegend },
        scales: {
            x: { grid: chartGrid, ticks: chartTicks },
            y: { beginAtZero: true, position: "left", grid: chartGrid, ticks: chartTicks },
            y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, ticks: chartTicks },
        },
    };

    const standardOptions = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: chartLegend },
        scales: {
            x: { grid: chartGrid, ticks: chartTicks },
            y: { beginAtZero: true, grid: chartGrid, ticks: chartTicks },
        },
    };

    if (loading) {
        return (
            <section className="fi-card fi-trends-state">
                <span className="material-symbols-outlined">progress_activity</span>
                <p>Loading farm trend analysis...</p>
            </section>
        );
    }

    if (error) {
        return (
            <section className="fi-card fi-trends-state error">
                <span className="material-symbols-outlined">error</span>
                <p>{error}</p>
            </section>
        );
    }

    return (
        <div className="fi-stack fi-trends-panel">
            <section className="fi-card">
                <div className="fi-section-heading fi-trends-heading">
                    <div>
                        <h3>Production Trends &amp; Seasonal Analysis</h3>
                        <p>
                            Uses historical farm records to compare crop yield, livestock growth,
                            production, crop/livestock sales, collections, season, and recorded weather.
                            Relationships are descriptive and should not be treated as proof of cause.
                        </p>
                    </div>
                    <label className="fi-trends-period">
                        <span>Analysis Period</span>
                        <select value={months} onChange={(event) => setMonths(Number(event.target.value))}>
                            <option value={6}>Last 6 months</option>
                            <option value={12}>Last 12 months</option>
                            <option value={24}>Last 24 months</option>
                            <option value={36}>Last 36 months</option>
                        </select>
                    </label>
                </div>

                <div className="fi-trend-kpis fi-trend-kpis-eight">
                    <article><span className="material-symbols-outlined">agriculture</span><div><small>Recorded Crop Yield</small><strong>{formatNumber(totals.cropYield)} kg</strong><p>{coverage.crop_yield_records || 0} harvest records</p></div></article>
                    <article><span className="material-symbols-outlined">nutrition</span><div><small>Confirmed Feed Use</small><strong>{formatNumber(totals.feed, 3)} kg</strong><p>{coverage.feeding_records || 0} feeding records</p></div></article>
                    <article><span className="material-symbols-outlined">monitor_weight</span><div><small>Growth Measurements</small><strong>{coverage.livestock_growth_records || 0}</strong><p>historical weight entries</p></div></article>
                    <article><span className="material-symbols-outlined">egg</span><div><small>Production Records</small><strong>{coverage.livestock_production_records || 0}</strong><p>livestock output records</p></div></article>
                    <article><span className="material-symbols-outlined">payments</span><div><small>Gross Sales</small><strong>{formatMoney(totals.grossSales)}</strong><p>crop + livestock sales</p></div></article>
                    <article><span className="material-symbols-outlined">eco</span><div><small>Crop Sales</small><strong>{formatMoney(totals.cropSales)}</strong><p>{coverage.crop_sales_records || 0} crop sale records</p></div></article>
                    <article><span className="material-symbols-outlined">pets</span><div><small>Livestock Sales</small><strong>{formatMoney(totals.livestockSales)}</strong><p>{coverage.livestock_sales_records || 0} livestock sale records</p></div></article>
                    <article><span className="material-symbols-outlined">account_balance_wallet</span><div><small>Cash Collected</small><strong>{formatMoney(totals.cashCollected)}</strong><p>cash recorded in period</p></div></article>
                </div>
            </section>

            <section className="fi-trend-insight-grid">
                <article className="fi-card fi-trend-insight"><small>Top Historical Crop</small><strong>{topCrop?.crop || "Needs harvest history"}</strong><p>{topCrop ? `${formatNumber(topCrop.yield_kg)} kg recorded yield` : "No crop yield record is available for this period."}</p></article>
                <article className="fi-card fi-trend-insight"><small>Highest-Yield Season</small><strong>{seasonalInsight?.season || "Needs seasonal history"}</strong><p>{seasonalInsight ? `${formatNumber(seasonalInsight.crop_yield_kg)} kg within the selected period` : "No seasonal crop-yield comparison is available."}</p></article>
                <article className="fi-card fi-trend-insight"><small>Strongest Recorded Association</small><strong>{strongestFactor ? correlationLabel(strongestFactor) : "Needs more history"}</strong><p>{strongestFactor ? `${strongestFactor.factor} · r = ${Number(strongestFactor.correlation).toFixed(3)}` : "At least three usable paired months are needed for correlation."}</p></article>
                <article className="fi-card fi-trend-insight"><small>Usable Factor Pairs</small><strong>{(coverage.rainfall_yield_pair_months || 0) + (coverage.feed_growth_pair_months || 0)}</strong><p>{coverage.rainfall_yield_pair_months || 0} rainfall/yield · {coverage.feed_growth_pair_months || 0} feed/growth</p></article>
            </section>

            <section className="fi-trend-chart-grid">
                <article className="fi-card fi-trend-chart-card">
                    <div className="fi-section-heading"><h3>Crop Yield &amp; Recorded Rainfall</h3><p>Monthly harvest output compared with stored weather observations.</p></div>
                    <div className="fi-trend-chart-canvas"><Line data={cropWeatherChart} options={dualAxisOptions} /></div>
                </article>
                <article className="fi-card fi-trend-chart-card">
                    <div className="fi-section-heading"><h3>Feed Consumption &amp; Livestock Growth</h3><p>Confirmed feed usage compared with measured average daily gain.</p></div>
                    <div className="fi-trend-chart-canvas"><Line data={feedGrowthChart} options={dualAxisOptions} /></div>
                </article>
            </section>

            <section className="fi-card fi-trend-chart-card fi-trend-sales-card">
                <div className="fi-section-heading"><h3>Crop &amp; Livestock Sales and Collections</h3><p>Monthly sales values are separated by source; cash collected reflects recorded payments in the period.</p></div>
                <div className="fi-trend-chart-canvas large">
                    {(coverage.sales_records || 0) > 0 ? <Line data={salesChart} options={standardOptions} /> : <div className="fi-trend-empty">No crop or livestock sales records in this period.</div>}
                </div>
            </section>

            <section className="fi-card fi-trend-chart-card fi-trend-production-card">
                <div className="fi-section-heading"><h3>Livestock Production Output by Month</h3><p>Different units stay as separate series so eggs, meat, milk, and other outputs are not incorrectly added together.</p></div>
                <div className="fi-trend-chart-canvas large">
                    {(data?.production_series || []).length > 0 ? <Bar data={productionChart} options={standardOptions} /> : <div className="fi-trend-empty">No livestock production records in this period.</div>}
                </div>
            </section>

            {(coverage.reproduction_records || 0) > 0 && (
                <section className="fi-card">
                    <div className="fi-section-heading"><h3>Reproduction Outcomes</h3><p>Summarizes actual breeding, pregnancy/incubation, birth/hatch, and offspring records in the selected period.</p></div>
                    <div className="fi-signal-grid compact">
                        <article><small>Reproduction Events</small><strong>{formatNumber(reproduction.events, 0)}</strong></article>
                        <article><small>Birth / Hatch Events</small><strong>{formatNumber(reproduction.birth_hatch_events, 0)}</strong></article>
                        <article><small>Confirmed Pregnant</small><strong>{formatNumber(reproduction.confirmed_pregnant, 0)}</strong></article>
                        <article><small>Eggs Set</small><strong>{formatNumber(reproduction.eggs_set, 0)}</strong></article>
                        <article><small>Fertility</small><strong>{reproduction.fertility_percent == null ? "N/A" : `${formatNumber(reproduction.fertility_percent, 1)}%`}</strong></article>
                        <article><small>Offspring Recorded</small><strong>{formatNumber(reproduction.offspring_recorded, 0)}</strong></article>
                        <article><small>Alive Offspring</small><strong>{formatNumber(reproduction.alive_offspring, 0)}</strong></article>
                        <article><small>Offspring Survival</small><strong>{reproduction.offspring_survival_percent == null ? "N/A" : `${formatNumber(reproduction.offspring_survival_percent, 1)}%`}</strong></article>
                    </div>
                </section>
            )}

            <section className="fi-card">
                <div className="fi-section-heading"><h3>Seasonal Pattern Summary</h3><p>Cool Dry: December–February, Hot Dry: March–May, Rainy: June–November.</p></div>
                <div className="fi-trend-table-wrap">
                    <table className="fi-trend-table">
                        <thead><tr><th>Season</th><th>Months</th><th>Crop Yield</th><th>Feed Used</th><th>Avg. Daily Gain</th><th>Gross Sales</th><th>Cash Collected</th></tr></thead>
                        <tbody>
                            {(data?.seasonal || []).map((row) => (
                                <tr key={row.season}>
                                    <td><strong>{row.season}</strong></td><td>{row.months_in_period}</td><td>{formatNumber(row.crop_yield_kg)} kg</td><td>{formatNumber(row.feed_consumption_kg, 3)} kg</td>
                                    <td>{row.average_daily_gain_kg == null ? "—" : `${formatNumber(row.average_daily_gain_kg, 4)} kg/day`}</td>
                                    <td>{formatMoney(row.gross_sales_value)}</td><td>{formatMoney(row.cash_collected)}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading"><h3>Factors Associated With Performance</h3><p>Statistical relationships are only calculated when enough historical monthly records exist.</p></div>
                <div className="fi-factor-grid">
                    {(data?.factor_analysis || []).map((item) => (
                        <article key={item.factor}><div><small>{item.factor}</small><strong>{correlationLabel(item)}</strong></div><span>{item.correlation == null ? "—" : `r = ${Number(item.correlation).toFixed(3)}`}</span><p>{item.note}</p></article>
                    ))}
                </div>
            </section>

            <section className="fi-card">
                <div className="fi-section-heading"><h3>Livestock Growth Performance</h3><p>Uses actual batch/animal measurements. Sample size and weight range are shown when recorded.</p></div>
                <div className="fi-trend-table-wrap fi-growth-scroll">
                    <table className="fi-trend-table fi-growth-table">
                        <thead><tr><th>Livestock</th><th>Type</th><th>Measurements</th><th>Animals Measured</th><th>Latest Range</th><th>Start Weight</th><th>Latest Avg.</th><th>Total Change</th><th>Avg. Daily Gain</th></tr></thead>
                        <tbody>
                            {(data?.growth_summary || []).length > 0 ? data.growth_summary.map((row) => (
                                <tr key={row.livestock_id}>
                                    <td><strong>{row.record_name}</strong></td><td>{row.animal_type}</td><td>{row.measurements}</td>
                                    <td>{row.animals_measured == null ? "—" : row.animals_measured}</td>
                                    <td>{row.min_weight_kg == null && row.max_weight_kg == null ? "—" : `${formatNumber(row.min_weight_kg)}–${formatNumber(row.max_weight_kg)} kg`}</td>
                                    <td>{formatNumber(row.start_weight_kg)} kg</td><td>{formatNumber(row.latest_weight_kg)} kg</td><td>{formatNumber(row.total_change_kg)} kg</td>
                                    <td>{row.average_daily_gain_kg == null ? "—" : `${formatNumber(row.average_daily_gain_kg, 4)} kg/day`}</td>
                                </tr>
                            )) : (
                                <tr><td colSpan="9" className="fi-trend-empty">Add at least two weight measurements for a livestock batch to calculate growth rate.</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    );
}
