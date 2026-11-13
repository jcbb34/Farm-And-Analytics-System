"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { httpClient } from "../services/httpClient.js";

export function resourceChoiceWorkKind(module, text) {
    const work = String(text || "").trim().toLowerCase();
    if (module === "Crop") {
        if (work.includes("fertiliz")) return "fertilizer";
        if (work.includes("herbicide") || work.includes("weed control")) return "herbicide";
        if (["pesticide", "pest control", "insecticide"].some(term => work.includes(term))) return "pesticide";
        if (work.includes("fungicide") || work.includes("fungal")) return "fungicide";
    }
    if (module === "Livestock") {
        if (work.includes("feed")) return "feed";
        if (work.includes("vaccin") || work.includes("booster")) return "vaccine";
        if (["deworm", "medicat", "medicine", "treatment"].some(term => work.includes(term))) return "medicine";
        if (work.includes("vitamin") || work.includes("supplement")) return "supplement";
        if (["clean", "sanit", "disinfect"].some(term => work.includes(term))) return "disinfectant";
    }
    return "all";
}

export default function useResourceChoices({ active, domain, selectedId, workModule, workText, inventoryUse }) {
    const [search, setSearch] = useState("");
    const [settled, setSettled] = useState({ domain: "", search: "" });
    const [page, setPage] = useState({ key: "", items: [], selected: null, total: 0 });
    const [loading, setLoading] = useState(false), [error, setError] = useState("");
    const sequence = useRef(0), controller = useRef(null), busy = useRef(false);
    const enabled = Boolean(active && ["Crop", "Livestock", "Inventory"].includes(domain));
    useEffect(() => setSearch(""), [domain]);
    useEffect(() => {
        if (!search.trim()) { setSettled({ domain, search: "" }); return; }
        const timer = window.setTimeout(() => setSettled({ domain, search: search.trim() }), 250);
        return () => window.clearTimeout(timer);
    }, [search, domain]);
    const pending = settled.domain !== domain || search.trim() !== settled.search;
    const kind = resourceChoiceWorkKind(workModule, workText);
    const query = useMemo(() => ({ domain, search: settled.search, selected_id: Number(selectedId) > 0 ? Number(selectedId) : undefined,
        work_module: workModule || undefined, work_kind: kind, inventory_use: inventoryUse || undefined, limit: 25 }), [domain, settled.search, selectedId, workModule, kind, inventoryUse]);
    const key = JSON.stringify(query);
    const load = useCallback(async (offset = 0) => {
        if (!enabled || pending) return;
        const id = ++sequence.current; controller.current?.abort();
        const request = new AbortController(); controller.current = request; busy.current = true;
        setLoading(true); setError("");
        try {
            const data = await httpClient.get(query.inventory_use ? "/inventory/choices" : "/activities/resource-choices", { query: { ...query, offset }, signal: request.signal, cache: "no-store" });
            if (!Array.isArray(data?.items) || !Number.isInteger(data.total) || data.total < 0) throw new Error("Invalid farm choices response.");
            if (id !== sequence.current || request.signal.aborted) return;
            setPage(previous => ({ key, selected: data.selected, total: data.total,
                items: offset && previous.key === key ? [...previous.items, ...data.items.filter(row => !previous.items.some(item => item.id === row.id))] : data.items }));
        } catch (failure) { if (id === sequence.current && !request.signal.aborted) setError(failure?.message || "Unable to load farm choices."); }
        finally { if (id === sequence.current) { setLoading(false); busy.current = false; controller.current = null; } }
    }, [enabled, pending, query, key]);
    useEffect(() => {
        if (!enabled) setPage({ key: "", items: [], selected: null, total: 0 });
        void load();
        return () => { sequence.current++; controller.current?.abort(); busy.current = false; };
    }, [load, enabled]);
    const matching = page.key === key && !pending;
    const items = matching ? (page.selected && !page.items.some(row => row.id === page.selected.id) ? [page.selected, ...page.items] : page.items) : [];
    return { search, setSearch, items, total: matching ? page.total : 0, pageCount: matching ? page.items.length : 0,
        loading: enabled && (pending || loading || (!matching && !error)), error: enabled && !pending ? error : "", retry: () => load(),
        loadMore: () => { if (enabled && matching && !busy.current && page.items.length < page.total) void load(page.items.length); } };
}
