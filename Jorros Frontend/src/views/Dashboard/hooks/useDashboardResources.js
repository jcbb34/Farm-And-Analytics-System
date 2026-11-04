"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { resourceUsageService } from "../../../services/resourceUsageService.js";
import { buildResourceCards, resourcePeriodRange } from "../resourceOverview.js";

export default function useDashboardResources({ period, inventory, inventoryError, inventoryLoading, access }) {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState("");
    const [reload, setReload] = useState(0);
    const retry = useCallback(() => setReload((value) => value + 1), []);
    const range = useMemo(() => resourcePeriodRange(period), [period]);
    const enabled = access.crop || access.livestock;
    useEffect(() => {
        let active = true;
        setLoading(true);
        setError("");
        if (!enabled) { setRows([]); setLoading(false); return; }
        resourceUsageService.getUsages({ startDate: range.startDate, endDate: range.endDate }).then((records) => {
            // Reject malformed quantities before they can look like a valid zero.
            buildResourceCards(records, null, { crop: true, livestock: true });
            if (active) setRows(records);
        }).catch((failure) => {
            if (active) { setRows([]); setError(failure?.message || "Unable to load resource consumption."); }
        }).finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [range.startDate, range.endDate, enabled, reload]);
    useEffect(() => {
        window.addEventListener("joross:farm-data-updated", retry);
        window.addEventListener("joross:activities-updated", retry);
        window.addEventListener("joross:resource-usages-updated", retry);
        return () => {
            window.removeEventListener("joross:farm-data-updated", retry);
            window.removeEventListener("joross:activities-updated", retry);
            window.removeEventListener("joross:resource-usages-updated", retry);
        };
    }, [retry]);
    const cards = useMemo(() => {
        const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
        const limit = new Date(`${today}T00:00:00+08:00`);
        limit.setUTCDate(limit.getUTCDate() + 30);
        const end = limit.toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
        const stock = inventoryError || inventoryLoading ? null : {
            lowStockItems: inventory.filter((item) => Number(item.quantity) <= Number(item.reorderLevel)).length,
            expiringItems: inventory.filter((item) => item.expirationDate && item.expirationDate >= today && item.expirationDate <= end).length,
        };
        const result = buildResourceCards(rows, stock, access);
        return inventoryLoading ? result.map((card) => card.id === "stock-watch" ? { ...card, value: "Loading…" } : card) : result;
    }, [rows, inventory, inventoryError, inventoryLoading, access]);
    return { cards, loading, error, retry, totalRecords: rows.length, periodLabel: range.label };
}
