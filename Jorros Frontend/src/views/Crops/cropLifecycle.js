export const CROP_LIFECYCLE_FILTERS = Object.freeze([
    "Active Crops",
    "Ready for Harvest",
    "Harvesting",
    "Growing",
    "Fully Harvested/Completed",
    "Archived",
    "All",
]);

export function isActiveCropCycle(crop = {}) {
    return !crop.isArchived && !["Harvested", "Failed"].includes(crop.status);
}

export function matchesCropLifecycleFilter(crop = {}, filter = "Active Crops") {
    if (filter === "All") return true;
    if (filter === "Active Crops") return isActiveCropCycle(crop);
    if (filter === "Fully Harvested/Completed") return !crop.isArchived && crop.status === "Harvested";
    if (filter === "Archived") return Boolean(crop.isArchived);
    return !crop.isArchived && crop.status === filter;
}

export function sortCropsByHarvestPriority(crops = []) {
    const rank = (crop) => {
        if (crop.status === "Ready for Harvest") return 0;
        if (crop.status === "Harvesting") return 1;
        if (crop.status === "Growing") return 2;
        if (crop.status === "Planted") return 3;
        return 4;
    };
    return [...crops].sort((a, b) => {
        const difference = rank(a) - rank(b);
        if (difference) return difference;
        if (a.status === "Ready for Harvest" && b.status === "Ready for Harvest") {
            return String(a.estimatedHarvest || "9999-12-31").localeCompare(String(b.estimatedHarvest || "9999-12-31"));
        }
        return String(a.name || "").localeCompare(String(b.name || ""));
    });
}
