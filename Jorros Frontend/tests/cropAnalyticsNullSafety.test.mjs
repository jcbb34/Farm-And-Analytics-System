import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { asFiniteAnalyticsNumber, formatAnalyticsDecimal, formatAnalyticsQuantity } from "../src/components/CropAnalytics/analyticsNumbers.mjs";

const root = path.resolve(import.meta.dirname, "..");

test("a crop without a harvest estimate has no estimated growth, rather than a fake 0%", () => {
    for (const missing of [null, undefined, "", "  ", "NaN", "abc", Infinity, Number.NaN]) {
        assert.equal(asFiniteAnalyticsNumber(missing), null);
        assert.equal(formatAnalyticsDecimal(missing, 1, "%", "Not estimated"), "Not estimated");
    }
});

test("valid numeric estimates including zero remain readable", () => {
    assert.equal(formatAnalyticsDecimal(0, 1, "%", "Not estimated"), "0.0%");
    assert.equal(formatAnalyticsDecimal(67.89, 1, "%"), "67.9%");
    assert.equal(formatAnalyticsDecimal("1.75", 2, " ha"), "1.75 ha");
    assert.equal(formatAnalyticsDecimal(null, 2, " ha"), "No data");
    assert.equal(formatAnalyticsQuantity(1004.5, " kg", "No data", 2), "1,004.5 kg");
    assert.equal(formatAnalyticsQuantity(null, " kg"), "No data");
});

test("crop analytics never calls toFixed directly on nullable API values", () => {
    const component = fs.readFileSync(path.join(root, "src/components/CropAnalytics/CropAnalytics.jsx"), "utf8");
    const route = fs.readFileSync(path.join(root, "src/views/Crops/Crops.jsx"), "utf8");
    for (const access of ["item.area.toFixed", "productivityStats.totalArea.toFixed", "productivityStats.averageGrowth.toFixed", "productivityStats.averageSurvival.toFixed"]) {
        assert.ok(!component.includes(access), `${access} is unsafe when the API returns null`);
    }
    assert.match(component, /formatAnalyticsDecimal\(productivityStats\.averageGrowth, 1, "%", "Not estimated"\)/);
    assert.match(route, /<CropAnalyticsErrorBoundary><CropAnalytics/);
});


test("missing growth observations are excluded from fallback averages", () => {
    const component = fs.readFileSync(path.join(root, "src/components/CropAnalytics/CropAnalytics.jsx"), "utf8");
    assert.match(component, /\.map\(\(crop\) => asFiniteAnalyticsNumber\(crop\.growth\)\)/);
    assert.match(component, /: null;\s+const survivalRates/);
    assert.match(component, /Array\.isArray\(analytics\?\.yieldByCrop\)/);
    assert.match(component, /String\(quality \|\| "unknown"\)/);
});

test("a successful crop creation is not misreported as failed after refresh", () => {
    const hook = fs.readFileSync(path.join(root, "src/views/Crops/hooks/useCropsPage.js"), "utf8");
    const saveFlow = hook.slice(hook.indexOf("const handleAddCrop ="), hook.indexOf("const handleEditCrop ="));
    assert.ok(saveFlow.indexOf('notify("Crop record added successfully.")') < saveFlow.indexOf('await refreshCrops()'));
    assert.match(saveFlow, /catch \(refreshError\)/);
    assert.match(saveFlow, /clearStableIdempotencyKey\(cropCreateRequestRef\)/);
});
