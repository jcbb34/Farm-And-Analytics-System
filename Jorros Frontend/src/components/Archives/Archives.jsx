"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createPortal } from "react-dom";
import { archiveModules, archiveRecordPath, archiveService, safeArchiveReturn } from "../../services/archiveService.js";
import { confirmAction, notifyError, notifySuccess } from "../../context/NotificationContext.jsx";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import useModalScrollLock from "../../hooks/useModalScrollLock.js";
import { reportService } from "../../services/reportService.js";
import { RecordFilters, RecordSearch, RecordDateFilter, RecordHeader, RecordTableSurface } from "../Records/RecordsLayout.jsx";
import "./Archives.css";

function dateText(value) {
    return value ? new Date(value).toLocaleString("en-PH", { timeZone: "Asia/Manila", dateStyle: "medium", timeStyle: "short" }) : "Not recorded";
}

function Details({ record, onClose }) {
    const ref = useRef(null);
    useModalScrollLock(Boolean(record));
    useEffect(() => {
        const previous = document.activeElement;
        ref.current?.querySelector("button")?.focus();
        const keyboard = (event) => {
            if (event.key === "Escape") onClose();
            if (event.key === "Tab") {
                const controls = [...ref.current.querySelectorAll("button, a[href]")];
                const first = controls[0], last = controls.at(-1);
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
        };
        document.addEventListener("keydown", keyboard);
        return () => { document.removeEventListener("keydown", keyboard); previous?.focus(); };
    }, [onClose]);
    return createPortal(<div className="archive-dialog-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-details-title" ref={ref}>
        <header><div><h2 id="archive-details-title">{record.recordName}</h2><p>Archived {record.module.toLowerCase()} record · Read only</p></div><button type="button" aria-label="Close archived record details" onClick={onClose}><span className="material-symbols-outlined" aria-hidden="true">close</span></button></header>
        <dl>{Object.entries({ ...record.details, archive_reason: record.reason, archived_date: dateText(record.archivedDate), archived_by: record.archivedBy }).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>
        {record.module === "Report" && <button type="button" className="archive-button" onClick={async () => { try { await reportService.downloadPdf({ id: record.sourceId, title: record.recordName }); } catch (error) { notifyError(error.message); } }}>Download PDF</button>}
    </section></div>, document.body);
}

export function ArchiveRecords({ module: fixedModule, moduleOptions, onCounts, central = false, navigation }) {
    const router = useRouter();
    const params = useSearchParams();
    const incomingModule = params.get("archive_module"), incomingRecord = params.get("record");
    const [ready, setReady] = useState(false), [module, setModule] = useState(fixedModule || "All");
    const [search, setSearch] = useState(""), [querySearch, setQuerySearch] = useState(""), [from, setFrom] = useState(""), [to, setTo] = useState("");
    const [offset, setOffset] = useState(0), [focusId, setFocusId] = useState(null), [returnTo, setReturnTo] = useState("");
    const [data, setData] = useState({ items: [], total: 0, counts: {} }), [loading, setLoading] = useState(true), [error, setError] = useState("");
    const [busy, setBusy] = useState(null), [selected, setSelected] = useState(null), [highlight, setHighlight] = useState(null);
    const highlighted = useRef("");
    const sequence = useRef(0), countsCallback = useRef(onCounts); countsCallback.current = onCounts;
    useEffect(() => {
        const q = new URLSearchParams(window.location.search);
        const savedModule = q.get("archive_module");
        if (savedModule && archiveModules[savedModule] && (!fixedModule || savedModule === fixedModule || moduleOptions?.includes(savedModule))) setModule(savedModule);
        setSearch(q.get("archive_search") || ""); setQuerySearch(q.get("archive_search") || ""); setFrom(q.get("archive_from") || ""); setTo(q.get("archive_to") || "");
        setOffset(Math.max(0, Number(q.get("archive_offset")) || 0));
        const id = Number(q.get("record")); if (Number.isInteger(id) && id > 0) setFocusId(id);
        setReturnTo(safeArchiveReturn(q.get("return_to"))); setReady(true);
    }, [fixedModule, incomingModule, incomingRecord]);
    useEffect(() => { const timer = setTimeout(() => setQuerySearch(search), 250); return () => clearTimeout(timer); }, [search]);
    useEffect(() => {
        if (!ready) return;
        const q = new URLSearchParams(window.location.search);
        if (central) q.set("section", "archive");
        for (const [key, value] of Object.entries({ archive_module: module === "All" ? "" : module, archive_search: search, archive_from: from, archive_to: to, archive_offset: offset || "", record: focusId || "" })) {
            if (value) q.set(key, String(value)); else q.delete(key);
        }
        window.history.replaceState(window.history.state, "", `${window.location.pathname}?${q}`);
    }, [ready, module, search, from, to, offset, focusId, central]);
    const load = useCallback(async ({ ignoreFocus = false } = {}) => {
        if (!ready) return;
        const requestId = ++sequence.current;
        setLoading(true); setError("");
        try {
            const result = await archiveService.list({ module: module === "All" ? undefined : module, search: querySearch, date_from: from || undefined, date_to: to || undefined, offset, limit: 25, focus_id: !ignoreFocus && focusId ? focusId : undefined });
            if (requestId !== sequence.current) return;
            if (Number.isInteger(result.offset) && result.offset !== offset) setOffset(result.offset);
            setData(result); countsCallback.current?.(result.counts || {});
        } catch (err) { if (requestId === sequence.current) { setError(err.message || "Unable to load archived records."); if ([403, 404, 409].includes(err.status)) setData((current) => ({ ...current, items: [], total: 0 })); } }
        finally { if (requestId === sequence.current) setLoading(false); }
    }, [ready, module, querySearch, from, to, offset, focusId]);
    useEffect(() => { void load(); }, [load]);
    useFarmModuleUpdates(["archives", "settings"], load, { editing: Boolean(selected) || Boolean(busy) });
    useEffect(() => {
        if (!focusId) { highlighted.current = ""; return; }
        const key = `${module}:${focusId}`;
        if (highlighted.current === key || !data.items.some((row) => row.sourceId === focusId && row.module === module)) return;
        const row = document.getElementById(`archive-record-${module}-${focusId}`);
        row?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
        if (!row) return;
        highlighted.current = key;
        row.focus({ preventScroll: true }); setHighlight(focusId);
        const timer = setTimeout(() => setHighlight(null), 3000); return () => clearTimeout(timer);
    }, [focusId, data.items, module]);
    const reset = () => { setModule(fixedModule || "All"); setSearch(""); setFrom(""); setTo(""); setOffset(0); setFocusId(null); };
    const act = async (record, remove = false) => {
        if (busy) return;
        const accepted = await confirmAction({ title: remove ? "Permanently Delete Record" : "Restore Archived Record", type: remove ? "error" : "warning",
            message: remove ? `Permanently delete ${record.recordName}? Linked records and historical reports are protected.` : `Restore ${record.recordName}? Existing history and previous report status will be preserved. Cancelled tasks will remain cancelled.`,
            confirmText: remove ? "Delete Permanently" : "Restore", cancelText: "Cancel" });
        if (!accepted) return;
        setBusy(record.id);
        try { await (remove ? archiveService.remove(record) : archiveService.restore(record)); setSelected(null); setFocusId(null); await load({ ignoreFocus: true }); notifySuccess(remove ? "Archived record deleted." : "Record restored. History preserved."); }
        catch (err) { notifyError(err.message); await load(); }
        finally { setBusy(null); }
    };
    const open = (record) => {
        const returnPath = central ? `${window.location.pathname}${window.location.search}` : returnTo;
        const path = archiveRecordPath(record, returnPath); if (path) router.push(path);
    };
    const allCount = Object.values(data.counts).reduce((sum, value) => sum + Number(value || 0), 0);
    const heading = (<div className="archive-heading"><div className={navigation ? "archive-record-title" : undefined}>{navigation || <h2>{central ? "Archived Records" : archiveModules[module]?.archived || `Archived ${module} Records`}</h2>}<p>{central ? "Archived records across all permitted modules." : "Read-only archived records. Summary cards above show current operational data."}</p></div>
            {returnTo && <button type="button" className="archive-button" onClick={() => router.push(returnTo)}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>Back to Archived Records</button>}</div>);
    const centralFilters = (<div className="archive-filters">
            <label className="archive-search">Search archived records<input type="search" value={search} placeholder="Search record, code, reason or archived by..." onChange={(event) => { setSearch(event.target.value); setOffset(0); setFocusId(null); }}/></label>
            {(!fixedModule || moduleOptions?.length > 1) && <label>Module<select value={module} onChange={(event) => { setModule(event.target.value); setOffset(0); setFocusId(null); }}>{!fixedModule && <option value="All">All Modules</option>}{(moduleOptions || Object.keys(archiveModules)).filter((name) => data.counts[name] !== undefined || name === module).map((name) => <option key={name}>{name}</option>)}</select></label>}
            <label>Archived from<input type="date" value={from} onChange={(event) => { setFrom(event.target.value); setOffset(0); setFocusId(null); }}/></label><label>Archived to<input type="date" value={to} min={from || undefined} onChange={(event) => { setTo(event.target.value); setOffset(0); setFocusId(null); }}/></label>
            <button type="button" className="archive-button" onClick={reset}>Clear Filters</button>
        </div>);
    const filters = navigation ? <RecordFilters className="archive-filters" label={`${module} archive filters`}>
        <RecordSearch className="archive-search" label="Search archived records" placeholder="Search record, code, reason or archived by..." value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); setFocusId(null); }}/>
        {moduleOptions?.length > 1 && <select aria-label="Archive module" value={module} onChange={(event) => { setModule(event.target.value); setOffset(0); setFocusId(null); }}>{moduleOptions.filter((name) => data.counts[name] !== undefined || name === module).map((name) => <option key={name}>{name}</option>)}</select>}
        <RecordDateFilter label="Archived from" prefix="From" value={from} onChange={(event) => { setFrom(event.target.value); setOffset(0); setFocusId(null); }}/>
        <RecordDateFilter label="Archived to" prefix="To" value={to} min={from || undefined} onChange={(event) => { setTo(event.target.value); setOffset(0); setFocusId(null); }}/>
        <button type="button" className="archive-button" onClick={reset}>Clear Filters</button>
    </RecordFilters> : centralFilters;
    const moduleHeading = <RecordHeader navigation={navigation}
        summary={`${error ? "Archived records could not be loaded" : loading ? "Loading archived records…" : `${data.total} archived records found`} · Read only. Summary cards above show current operational data.`}
        actions={returnTo ? <button type="button" className="archive-button" onClick={() => router.push(returnTo)}><span className="material-symbols-outlined" aria-hidden="true">arrow_back</span>Back to Archived Records</button> : null}/>;
    const footer = (<footer className={`archive-footer${navigation ? " records-footer" : ""}`}><span>{error ? "Archived records could not be loaded." : loading && !data.items.length ? "Loading archived records…" : <>Showing {data.items.length ? offset + 1 : 0}–{offset + data.items.length} of {data.total} matching records · {module === "All" ? allCount : data.counts[module] || 0} archived records{module === "Livestock" ? " (records, not animal quantity)" : ""}</>}</span><div><button type="button" className="archive-button" disabled={loading || Boolean(error) || offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>Previous</button><button type="button" className="archive-button" disabled={loading || Boolean(error) || offset + 25 >= data.total} onClick={() => setOffset(offset + 25)}>Next</button></div></footer>);
    return <section className={`archive-records${navigation ? " archive-records-has-navigation" : ""}`} aria-label={central ? "All Archived Records" : `Archived ${module} Records`}>
        {navigation ? <>{filters}{moduleHeading}</> : <>{heading}{filters}</>}
        {focusId && <p className="archive-focus-note">Showing the selected archived record. <button type="button" onClick={reset}>Show all archived records</button></p>}
        {error && <div role="alert" className="archive-error">{error} <button type="button" className="archive-button" onClick={() => { if (focusId) setFocusId(null); else void load(); }}>Retry</button>{focusId && <button type="button" className="archive-button" onClick={reset}>Show current archive list</button>}</div>}
        <RecordTableSurface className="archive-table-wrap" scrollClassName="archive-table-scroll" busy={loading} footer={navigation ? footer : null}><table className={`archive-table${navigation && fixedModule === "Crop" ? " crop-table" : ""}`}><thead><tr><th>Record Name</th><th>Module</th><th>Reason</th><th>Archived Date</th><th>Archived By</th><th>Actions</th></tr></thead><tbody>
            {data.items.map((record) => <tr id={`archive-record-${record.module}-${record.sourceId}`} key={record.id} tabIndex={-1} className={highlight === record.sourceId ? "archive-highlight" : ""}>
                <td data-label="Record Name">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Record Name</span>}<button type="button" className="archive-record-link" onClick={() => central ? open(record) : setSelected(record)}>{record.recordName}</button></td><td data-label="Module">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Module</span>}<span className="archive-module-badge">{record.module}</span></td><td data-label="Reason">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Reason</span>}{record.reason}</td><td data-label="Archived Date">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Archived Date</span>}{dateText(record.archivedDate)}</td><td data-label="Archived By">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Archived By</span>}{record.archivedBy}</td>
                <td data-label="Actions">{navigation && fixedModule === "Crop" && <span className="crop-mobile-label">Actions</span>}<div className="archive-actions records-row-actions">{central && <button type="button" className="archive-button" onClick={() => open(record)}><span className="material-symbols-outlined" aria-hidden="true">open_in_new</span>Go to Record</button>}<button type="button" className="archive-button" onClick={() => setSelected(record)}>View Details</button>{record.canRestore && <button type="button" className="archive-button" disabled={Boolean(busy)} onClick={() => act(record)}>Restore</button>}{record.canDelete && <button type="button" className="archive-button danger" disabled={Boolean(busy)} onClick={() => act(record, true)}>Delete</button>}</div></td>
            </tr>)}
            {!data.items.length && <tr><td colSpan={6} className="archive-empty">{loading ? "Loading archived records…" : error ? "Archive data could not be loaded." : "No archived records match these filters."}</td></tr>}
        </tbody></table></RecordTableSurface>
        {!navigation && footer}
        {selected && <Details record={selected} onClose={() => setSelected(null)}/>}
    </section>;
}

export default function ArchiveWorkspace({ module, before, children }) {
    const query = useSearchParams();
    const archiveFlag = query.get("archive");
    const [active, setActive] = useState(archiveFlag === "1"), [counts, setCounts] = useState({});
    const [countsError, setCountsError] = useState("");
    const config = archiveModules[module];
    useEffect(() => {
        const read = () => setActive(new URLSearchParams(window.location.search).get("archive") === "1");
        read(); window.addEventListener("popstate", read);
        return () => window.removeEventListener("popstate", read);
    }, [archiveFlag]);
    const loadCounts = useCallback(async () => {
        try { const data = await archiveService.list({ module, counts_only: true }); setCounts(data.counts || {}); setCountsError(""); }
        catch (error) { setCounts({}); setCountsError(error.code === "ARCHIVE_API_UNAVAILABLE" ? error.message : ""); }
    }, [module]);
    useEffect(() => { void loadCounts(); }, [loadCounts]);
    useFarmModuleUpdates(["archives"], loadCounts);
    const change = (archived) => {
        if (archived === active) return;
        const q = new URLSearchParams(window.location.search);
        // Manual tab entry starts with the complete module archive list. Direct
        // record links and returning from Settings keep their saved query state.
        for (const key of ["archive", "archive_module", "record", "return_to", "archive_search", "archive_from", "archive_to", "archive_offset"]) q.delete(key);
        if (archived) { q.set("archive", "1"); q.set("archive_module", module); }
        window.history.replaceState(window.history.state, "", `${window.location.pathname}${q.size ? `?${q}` : ""}`);
        setActive(archived);
    };
    const navigation = <><nav className="archive-tabs" aria-label={`${module} record views`}>
        <button type="button" className={!active ? "active" : ""} aria-pressed={!active} onClick={() => change(false)}>
            <span className="material-symbols-outlined" aria-hidden="true">{config.icon}</span>{config.current}
        </button>
        <button type="button" className={active ? "active" : ""} aria-pressed={active} onClick={() => change(true)}>
            <span className="material-symbols-outlined" aria-hidden="true">archive</span>{config.archived}
            {counts[module] !== undefined && <span className="archive-count">{counts[module]}</span>}
        </button>
    </nav>{countsError && !active && <div className="archive-error" role="alert">{countsError} <button type="button" className="archive-button" onClick={loadCounts}>Retry</button></div>}</>;
    return <div className="archive-workspace records-workspace">{active
        ? <ArchiveRecords module={module} moduleOptions={module === "Livestock" ? ["Livestock", "Pen"] : undefined} onCounts={setCounts} navigation={navigation}/>
        : <>{before}{typeof children === "function" ? children(navigation) : <>{navigation}{children}</>}</>}
    </div>;
}
