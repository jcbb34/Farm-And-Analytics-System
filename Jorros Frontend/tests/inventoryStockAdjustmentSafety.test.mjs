import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const read = async (path) => readFile(new URL(path, root), "utf8");

const modalSource = await read("src/components/InventoryModals/InventoryModals.jsx");
const modalCss = await read("src/components/InventoryModals/InventoryModals.css");
const serviceSource = await read("src/services/inventoryService.js");
const hookSource = await read("src/views/Inventory/hooks/useInventoryPage.js");

test("stock adjustment has an immediate one-flight guard and visible saving state", () => {
    assert.match(modalSource, /const adjustmentSubmittingRef = useRef\(false\)/);
    assert.match(modalSource, /if \(adjustmentSubmittingRef\.current\) \{\s*return;\s*\}/);
    assert.match(modalSource, /adjustmentSubmittingRef\.current = true/);
    assert.match(modalSource, /disabled=\{adjustmentSaving\}/);
    assert.match(modalSource, /Saving Stock Adjustment\.\.\./);
    assert.match(modalCss, /\.inventory-stock-form-footer button:disabled/);
});

test("stock adjustment retries use a stable idempotency key end to end", () => {
    assert.match(modalSource, /stableIdempotencyKey\(/);
    assert.match(modalSource, /`inventory-stock-adjust:\$\{item\.id\}`/);
    assert.match(modalSource, /onAdjustStock\(\s*item\.id,\s*payload,\s*idempotencyKey/);
    assert.match(serviceSource, /addStockAdjustment\(\s*inventoryId,\s*adjustment,\s*\{ idempotencyKey = null \} = \{\}/);
    assert.match(serviceSource, /"Idempotency-Key": idempotencyKey/);
    assert.match(hookSource, /\{ idempotencyKey \}/);
});

test("successful adjustment applies POST result locally instead of waiting for a second item GET", () => {
    const start = hookSource.indexOf("const handleAdjustStock");
    const end = hookSource.indexOf("const archiveInventoryItem", start);
    const block = hookSource.slice(start, end);
    assert.match(block, /const stockRecord = await inventoryService\.addStockAdjustment/);
    assert.match(block, /quantity: stockRecord\.newQuantity/);
    assert.doesNotMatch(block, /getInventoryItem\(/);
});
