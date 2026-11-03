"use client";

import "./RecordsLayout.css";

export function RecordFilters({ children, className = "", label = "Record filters" }) {
    return <section className={`records-filter-panel ${className}`} aria-label={label}>{children}</section>;
}

export function RecordSearch({ label, placeholder, value, onChange, className = "" }) {
    return <label className={`records-search ${className}`}>
        <span className="records-sr-only">{label}</span>
        <span className="material-symbols-outlined" aria-hidden="true">search</span>
        <input type="search" aria-label={label} placeholder={placeholder} value={value} onChange={onChange}/>
    </label>;
}

export function RecordDateFilter({ label, prefix, value, onChange, min, title }) {
    return <label className="records-date-filter">
        <span aria-hidden="true">{prefix}</span>
        <input type="date" aria-label={label} title={title || label} value={value} min={min} onChange={onChange}/>
    </label>;
}

export function RecordHeader({ navigation, title, summary, actions, className = "" }) {
    return <section className={`records-heading ${className}`}>
        <div className="records-toolbar">
            <div className="records-navigation">{navigation || <h2>{title}</h2>}</div>
            {actions && <div className="records-toolbar-actions">{actions}</div>}
        </div>
        {summary && <p className="records-caption">{summary}</p>}
    </section>;
}

export function RecordTableSurface({ children, className = "", scrollClassName = "", busy, footer }) {
    return <section className={`records-table-surface ${className}`}>
        <div className={`records-table-scroll ${scrollClassName}`} aria-busy={busy}>{children}</div>
        {footer}
    </section>;
}
