"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { reportService } from "../../../services/reportService.js";

export default function useReportPdfJobs(reports) {
    const key = [...new Set(reports.map(report => Number(report.id)).filter(id => id > 0))].sort((a, b) => a - b).join(",");
    const [data, setData] = useState({ key: "", rows: [] });
    const [pdfJobsError, setError] = useState("");
    const sequence = useRef(0), requestRef = useRef(null);
    const refreshPdfJobs = useCallback(({ force = false } = {}) => {
        if (!key) return Promise.resolve();
        if (!force && requestRef.current?.key === key) return requestRef.current.promise;
        requestRef.current?.controller.abort();
        const controller = new AbortController(), id = ++sequence.current;
        const pending = reportService.getPdfJobs(key, controller.signal).then(rows => {
            if (!Array.isArray(rows)) throw new Error("Invalid PDF status response.");
            if (id !== sequence.current || controller.signal.aborted) return;
            setData({ key, rows }); setError("");
        }).catch(failure => {
            if (id === sequence.current && !controller.signal.aborted) setError(failure?.message || "Unable to load PDF progress.");
        }).finally(() => { if (id === sequence.current) requestRef.current = null; });
        requestRef.current = { key, controller, promise: pending };
        return pending;
    }, [key]);
    useEffect(() => {
        setError("");
        if (!document.hidden) void refreshPdfJobs();
        const visible = () => { if (!document.hidden) void refreshPdfJobs(); };
        document.addEventListener("visibilitychange", visible);
        return () => {
            ++sequence.current; requestRef.current?.controller.abort(); requestRef.current = null;
            document.removeEventListener("visibilitychange", visible);
        };
    }, [refreshPdfJobs]);
    const rows = data.key === key ? data.rows : [];
    const pending = rows.some(row => ["Queued", "Generating"].includes(row.status));
    useEffect(() => {
        if (!pending || pdfJobsError) return;
        const timer = window.setInterval(() => { if (!document.hidden) void refreshPdfJobs(); }, 2000);
        return () => window.clearInterval(timer);
    }, [pending, pdfJobsError, refreshPdfJobs]);
    return { pdfJobs: Object.fromEntries(rows.map(row => [row.report_id, row])), pdfJobsError, refreshPdfJobs };
}
