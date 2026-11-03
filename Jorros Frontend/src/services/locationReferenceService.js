import { httpClient } from "./httpClient.js";

// Public PSA reference only. Personal addresses and validation stay in the API.
export const LOCATION_CATALOGUE_PATH = "/reference-data/philippine_locations.2026-Q3.json";
const levels = new Set(["provinces", "cities", "barangays"]);
let bundledCatalogue;

function isChoice(row) {
    return row && /^\d{10}$/.test(row.code) && typeof row.name === "string" && row.name.trim();
}

function readBundledCatalogue() {
    if (!bundledCatalogue) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 8000);
        bundledCatalogue = fetch(LOCATION_CATALOGUE_PATH, {
            signal: controller.signal,
            credentials: "omit",
            cache: "no-cache",
        }).then(async (response) => {
            if (!response.ok) throw new Error("The bundled address reference could not be loaded.");
            const data = await response.json();
            if (data.version !== "2026-Q3" || [...levels].some((level) => !Array.isArray(data[level]) || !data[level].length || !data[level].every(isChoice))) {
                throw new Error("The bundled address reference is invalid.");
            }
            return data;
        }).catch((error) => {
            // A failed fetch must not poison Retry list or later form openings.
            bundledCatalogue = undefined;
            throw error;
        }).finally(() => clearTimeout(timer));
    }
    return bundledCatalogue;
}

export async function getLocationChoices(level, parentCode = null) {
    if (!levels.has(level)) throw new Error("Unknown address level.");
    if (level !== "provinces" && !parentCode) return [];

    try {
        // Serve suggestions from Next.js itself, independent of backend route
        // deployment, proxy/auth latency and internet connectivity.
        const data = await readBundledCatalogue();
        const parentField = level === "cities" ? "province_code" : "city_code";
        return data[level]
            .filter((row) => level === "provinces" || row[parentField] === parentCode)
            .map(({ code, name }) => ({ code, name }))
            .sort((left, right) => left.name.localeCompare(right.name));
    } catch {
        // Retain compatibility with deployments whose public files have not
        // been copied yet. Never substitute a partial or invented catalogue.
        const result = await httpClient.get("/reference/locations", {
            query: { level, parent_code: parentCode || undefined },
            cache: "no-store",
        });
        if (!Array.isArray(result?.items) || !result.items.every(isChoice)) {
            throw new Error("Address suggestions could not be loaded.");
        }
        return result.items;
    }
}
