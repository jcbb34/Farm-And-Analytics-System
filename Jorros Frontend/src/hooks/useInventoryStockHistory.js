"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { inventoryService } from "../services/inventoryService.js";

export default function useInventoryStockHistory({ active, inventoryId, revision }) {
    const key = JSON.stringify([inventoryId, revision]);
    const [page, setPage] = useState({ key: "", items: [], total: 0, snapshot: null });
    const [loading, setLoading] = useState(false), [error, setError] = useState("");
    const controller = useRef(null), sequence = useRef(0), busy = useRef(false), failedOffset = useRef(0);
    const pageRef = useRef(page); pageRef.current = page;
    const load = useCallback(async (offset = 0) => {
        if (!active || !inventoryId) return;
        const requestId = ++sequence.current;
        controller.current?.abort();
        const request = new AbortController(); controller.current = request; busy.current = true;
        failedOffset.current = offset;
        setLoading(true); setError("");
        try {
            const previous = pageRef.current;
            const data = await inventoryService.getStockHistoryPage(inventoryId, {
                offset, limit: 25, signal: request.signal,
                ...(offset && previous.key === key ? { snapshot_id: previous.snapshot } : {}),
            });
            if (requestId !== sequence.current || request.signal.aborted) return;
            setPage(current => ({ key, total: data.total, snapshot: data.snapshot_id,
                items: offset && current.key === key
                    ? [...current.items, ...data.items.filter(row => !current.items.some(item => item.id === row.id))]
                    : data.items }));
        } catch (failure) {
            if (requestId === sequence.current && !request.signal.aborted) setError(failure?.message || "Unable to load stock history.");
        } finally {
            if (requestId === sequence.current) { setLoading(false); busy.current = false; controller.current = null; }
        }
    }, [active, inventoryId, key]);
    useEffect(() => {
        void load();
        return () => { ++sequence.current; controller.current?.abort(); busy.current = false; };
    }, [load]);
    const current = page.key === key;
    return { items: current ? page.items : [], total: current ? page.total : 0,
        loaded: current, loading: Boolean(active && (loading || (!current && !error))), error: active ? error : "",
        retry: () => load(failedOffset.current),
        loadMore: () => { if (current && !busy.current && page.items.length < page.total) void load(page.items.length); } };
}
