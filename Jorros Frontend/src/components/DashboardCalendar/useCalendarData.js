"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { activityService } from "../../services/activityService.js";

export default function useCalendarData(ranges, agendaOpen) {
    const key = JSON.stringify({ ranges, agendaOpen });
    const [data, setData] = useState({ key: "", days: [], summary: {}, day: [], dayTotal: 0, upcoming: [], upcomingTotal: 0, agenda: [], agendaTotal: 0 });
    const [loading, setLoading] = useState(true), [error, setError] = useState("");
    const [loadingMore, setLoadingMore] = useState(false), [moreError, setMoreError] = useState("");
    const sequence = useRef(0), controller = useRef(null), moreBusy = useRef(false);
    const refresh = useCallback(async () => {
        const id = ++sequence.current;
        controller.current?.abort();
        const request = new AbortController(); controller.current = request;
        moreBusy.current = false; setLoadingMore(false); setMoreError(""); setLoading(true); setError("");
        try {
            const [summary, day, upcoming, agenda] = await Promise.all([
                activityService.getCalendarSummary(ranges.summary, request.signal),
                activityService.getCalendarEvents({ ...ranges.day, limit: 25 }, request.signal),
                activityService.getCalendarEvents({ ...ranges.upcoming, limit: 5 }, request.signal),
                agendaOpen ? activityService.getCalendarEvents({ ...ranges.agenda, limit: 25 }, request.signal) : Promise.resolve({ items: [], total: 0 }),
            ]);
            if (id === sequence.current && !request.signal.aborted) setData({ key, days: summary.days, summary: summary.summary,
                day: day.items, dayTotal: day.total, upcoming: upcoming.items, upcomingTotal: upcoming.total,
                agenda: agenda.items, agendaTotal: agenda.total });
        } catch (failure) {
            if (id === sequence.current && !request.signal.aborted) setError(failure?.message || "Unable to load calendar events.");
        } finally { if (id === sequence.current) { setLoading(false); controller.current = null; } }
    }, [key]);
    useEffect(() => {
        void refresh();
        let changedWhileHidden = false;
        const update = () => {
            if (document.visibilityState === "hidden") { changedWhileHidden = true; return; }
            changedWhileHidden = false; void refresh();
        };
        const resume = () => { if (changedWhileHidden && document.visibilityState !== "hidden") update(); };
        window.addEventListener("joross:activities-updated", update);
        document.addEventListener("visibilitychange", resume);
        return () => {
            sequence.current++; controller.current?.abort();
            window.removeEventListener("joross:activities-updated", update);
            document.removeEventListener("visibilitychange", resume);
        };
    }, [refresh]);
    const more = async kind => {
        const total = data[kind + "Total"], items = data[kind];
        if (loading || moreBusy.current || data.key !== key || items.length >= total) return;
        const id = sequence.current; moreBusy.current = true; setLoadingMore(true); setMoreError("");
        try {
            const page = await activityService.getCalendarEvents({ ...ranges[kind], offset: items.length, limit: 25 });
            if (id !== sequence.current) return;
            setData(previous => ({ ...previous, [kind + "Total"]: page.total,
                [kind]: [...previous[kind], ...page.items.filter(row => !previous[kind].some(item => item.id === row.id))] }));
        } catch (failure) { if (id === sequence.current) setMoreError(failure?.message || "Unable to load more calendar events."); }
        finally { if (id === sequence.current) { moreBusy.current = false; setLoadingMore(false); } }
    };
    const matching = data.key === key;
    return { ...data, summary: matching ? data.summary : {},
        dayTotal: matching ? data.dayTotal : 0, upcomingTotal: matching ? data.upcomingTotal : 0, agendaTotal: matching ? data.agendaTotal : 0,
        days: matching ? data.days : [], day: matching ? data.day : [], upcoming: matching ? data.upcoming : [], agenda: matching ? data.agenda : [],
        loading: loading || (!matching && !error), error, moreError, loadingMore, refresh,
        loadMoreDay: () => more("day"), loadMoreAgenda: () => more("agenda"), loadMoreUpcoming: () => more("upcoming") };
}
