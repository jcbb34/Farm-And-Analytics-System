"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { httpClient } from "../../services/httpClient.js";
import "./LivestockAnalytics.css";

const number = value => Number(value || 0).toLocaleString("en-PH", { maximumFractionDigits: 3 });
const money = value => Number(value || 0).toLocaleString("en-PH", { style: "currency", currency: "PHP" });

function Distribution({ title, values = {}, unit = "" }) {
    const entries = Object.entries(values).sort((a, b) => b[1] - a[1]);
    const max = Math.max(1, ...entries.map(([, value]) => Number(value)));
    return <article className="livestock-chart-card">
        <div className="livestock-chart-header"><h3>{title}</h3></div>
        <div className="livestock-aggregate-list">{entries.length ? entries.map(([label, value]) => <div key={label}>
            <span>{label}</span><strong>{number(value)}{unit && ` ${unit}`}</strong>
            <meter min="0" max={max} value={value} aria-label={`${label}: ${number(value)} ${unit}`} />
        </div>) : <p>No records available.</p>}</div>
    </article>;
}

function RecordDisclosure({ kind, title, onOpenAnimal, revision }) {
    const [open, setOpen] = useState(false), [rows, setRows] = useState([]), [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false), [error, setError] = useState("");
    const requestRef = useRef(0), busyRef = useRef(false);
    const load = useCallback(async (offset = 0) => {
        const requestId = ++requestRef.current;
        busyRef.current = true; setLoading(true); setError("");
        try {
            const data = await httpClient.get("/display/livestock/records", { query: { kind, offset, limit: 25 }, cache: "no-store" });
            if (requestId !== requestRef.current) return;
            setRows(current => offset ? [...current, ...data.items.filter(row => !current.some(item => item.id === row.id))] : data.items);
            setTotal(data.total);
        } catch (failure) { if (requestId === requestRef.current) setError(failure?.message || "Unable to load these records."); }
        finally { if (requestId === requestRef.current) { setLoading(false); busyRef.current = false; } }
    }, [kind]);
    useEffect(() => {
        if (open) void load();
        return () => { requestRef.current += 1; busyRef.current = false; };
    }, [open, load, revision]);
    const vaccinations = kind === "vaccinations";
    return <details className="livestock-paged-disclosure" onToggle={event => setOpen(event.currentTarget.open)}>
        <summary>{title}</summary>
        {open && <div>
            {error && <div className="workforce-error" role="alert">{error} <button type="button" className="workforce-button secondary" onClick={() => load()}>Retry records</button></div>}
            {loading && <p role="status">Loading records…</p>}
            {!error && <><p className="livestock-list-caption">Showing {rows.length} of {total} records across active livestock.</p>
                <div className="livestock-paged-table"><table><thead><tr><th>Livestock</th><th>{vaccinations ? "Date" : "Schedule"}</th><th>{vaccinations ? "Vaccine" : "Feed"}</th><th>{vaccinations ? "Next due" : "Planned per day"}</th><th>Action</th></tr></thead>
                <tbody>{rows.map(row => <tr key={row.id}><td><strong>{row.record_name}</strong><small>{row.animal_code}</small></td>
                    <td>{vaccinations ? row.date_administered : row.feed_times || "Not scheduled"}</td>
                    <td>{vaccinations ? row.vaccine : row.feed_type || "Not specified"}</td>
                    <td>{vaccinations ? row.next_due || "—" : `${number(row.daily_feed_kg)} kg / animal`}</td>
                    <td><button type="button" className="workforce-button secondary compact" onClick={() => onOpenAnimal({ id: row.livestock_id })}>Open record</button></td></tr>)}</tbody></table></div>
                {!loading && !rows.length && <p>No records available.</p>}
                {rows.length < total && <button type="button" className="workforce-button secondary" disabled={loading} onClick={() => { if (!busyRef.current) void load(rows.length); }}>{loading ? "Loading…" : "Load more records"}</button>}
            </>}
        </div>}
    </details>;
}

export default function LivestockAnalytics({ summary, onOpenAnimal }) {
    const analytics = summary.analytics;
    return <section className="livestock-insights">
        <div className="livestock-insights-heading"><div><h2>Livestock Analytics</h2><p>Current totals across all active livestock records.</p></div></div>
        <div className="livestock-analytics-grid">
            <Distribution title="Livestock by Type" values={analytics.population} />
            <Distribution title="Age Distribution" values={analytics.age_groups} />
            <Distribution title="Planned Feed per Day" values={analytics.planned_feed} unit="kg" />
            <article className="livestock-chart-card"><div className="livestock-chart-header"><h3>Estimated Monthly Feed Budget</h3></div>
                <div className="livestock-aggregate-list"><strong>{money(analytics.estimated_monthly_budget)}</strong><p>Planning estimate using saved feed amounts, 30 days, and standard feed prices. Actual consumption is recorded separately.</p></div>
            </article>
        </div>
        <RecordDisclosure kind="vaccinations" title="Vaccination Records" onOpenAnimal={onOpenAnimal} revision={summary} />
        <RecordDisclosure kind="feeding" title="Feeding Schedules" onOpenAnimal={onOpenAnimal} revision={summary} />
    </section>;
}
