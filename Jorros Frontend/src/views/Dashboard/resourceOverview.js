// @ts-check
import { getDashboardPeriodRange } from "../../services/dashboardPeriod.js";

/** @typedef {{id: string, icon: string, title: string, value: string}} ResourceCard */
/** @typedef {{usageType: string, quantity: number, unit: string, isVoided?: boolean}} UsageRow */
const numberFormat = new Intl.NumberFormat("en-PH", { maximumFractionDigits: 3 });

/** @param {string} period */
export function resourcePeriodRange(period) {
    const match = /^(\d{4}-\d{2}-\d{2}) to (\d{4}-\d{2}-\d{2})$/.exec(period);
    return match
        ? getDashboardPeriodRange("custom", { startDate: match[1], endDate: match[2] })
        : getDashboardPeriodRange(period);
}

/** @param {UsageRow[]} rows @param {string[]} types */
export function formatUsageTotal(rows, types) {
    const totals = new Map();
    for (const row of rows) {
        if (row.isVoided || !types.includes(row.usageType)) continue;
        if (!Number.isFinite(row.quantity) || row.quantity < 0 || !String(row.unit || "").trim()) {
            throw new Error("Resource quantities or units could not be read. Retry loading resource data.");
        }
        const unit = row.unit.trim();
        totals.set(unit, (totals.get(unit) || 0) + row.quantity);
    }
    return totals.size ? [...totals].map(([unit, total]) => `${numberFormat.format(total)} ${unit}`).join(" / ") : "0";
}

/**
 * @param {UsageRow[]} rows
 * @param {{lowStockItems: number, expiringItems: number} | null} stock
 * @param {{crop?: boolean, livestock?: boolean, inventory?: boolean}} access
 * @returns {ResourceCard[]}
 */
export function buildResourceCards(rows, stock, access = { crop: true, livestock: true, inventory: true }) {
    return [
        ...(access.crop ? [
            { id: "fertilizer", icon: "compost", title: "Fertilizer Used", value: formatUsageTotal(rows, ["Fertilizer"]) },
            { id: "pesticide", icon: "pest_control", title: "Crop Protection Used", value: formatUsageTotal(rows, ["Pesticide", "Herbicide"]) },
        ] : []),
        ...(access.livestock ? [
            { id: "feed", icon: "grass", title: "Livestock Feed Used", value: formatUsageTotal(rows, ["Feed"]) },
            { id: "health", icon: "vaccines", title: "Animal Health Supplies", value: formatUsageTotal(rows, ["Medicine", "Vitamin / Supplement", "Vaccine"]) },
        ] : []),
        ...(access.inventory ? [{ id: "stock-watch", icon: "inventory", title: "Stock Watch (current)",
            value: stock ? `${numberFormat.format(stock.lowStockItems)} low • ${numberFormat.format(stock.expiringItems)} expiring` : "Unavailable" }] : []),
    ];
}
