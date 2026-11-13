"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { productionSalesService } from "../../services/productionSalesService.js";

export default function useSaleStock({ open, kind, search }) {
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const [page, setPage] = useState({ key: "", items: [], total: 0 });
    const [loading, setLoading] = useState(false), [error, setError] = useState("");
    const sequence = useRef(0), controller = useRef(null), busy = useRef(false);
    const query = useMemo(() => ({ kind, search: debouncedSearch, limit: 25 }), [kind, debouncedSearch]);
    const key = JSON.stringify(query);
    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
        return () => window.clearTimeout(timer);
    }, [search]);

    const load = useCallback(async (offset = 0) => {
        if (!open) return;
        const id = ++sequence.current;
        controller.current?.abort();
        const request = new AbortController(); controller.current = request; busy.current = true;
        setLoading(true); setError("");
        try {
            const data = await productionSalesService.getStock({ ...query, offset }, { signal: request.signal });
            if (id !== sequence.current || request.signal.aborted) return;
            setPage(previous => ({ key, total: data.total, items: offset && previous.key === key
                ? [...previous.items, ...data.items.filter(row => !previous.items.some(item => item.id === row.id))] : data.items }));
        } catch (failure) {
            if (id === sequence.current && !request.signal.aborted) setError(failure?.message || "Unable to load available stock.");
        } finally {
            if (id === sequence.current) { setLoading(false); busy.current = false; controller.current = null; }
        }
    }, [open, query, key]);
    useEffect(() => {
        if (open) void load();
        return () => { sequence.current++; controller.current?.abort(); busy.current = false; };
    }, [open, load]);
    const pendingSearch = search.trim() !== debouncedSearch;
    const matching = page.key === key && !pendingSearch;
    const loadMore = () => {
        if (open && matching && !busy.current && page.items.length < page.total) void load(page.items.length);
    };
    return { items: matching ? page.items : [], total: matching ? page.total : 0,
        loading: open && (pendingSearch || loading || (!matching && !error)), error: pendingSearch ? "" : error,
        loadMore, retry: () => load() };
}
