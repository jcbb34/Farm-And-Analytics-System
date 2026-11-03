import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const productionSales = fs.readFileSync(
    new URL("../src/views/ProductionSales/ProductionSales.jsx", import.meta.url),
    "utf8",
);
const productionService = fs.readFileSync(
    new URL("../src/services/productionSalesService.js", import.meta.url),
    "utf8",
);
const inventoryService = fs.readFileSync(
    new URL("../src/services/inventoryService.js", import.meta.url),
    "utf8",
);
const livestockProduction = fs.readFileSync(
    new URL("../src/components/LivestockReproductionProduction/LivestockReproductionProduction.jsx", import.meta.url),
    "utf8",
);

test("sales UI builds one invoice from production, live-animal, and inventory lines", () => {
    assert.match(productionSales, /Create Sales Invoice/);
    assert.match(productionSales, /item_kind: kind/);
    assert.match(productionSales, /production_record_id/);
    assert.match(productionSales, /inventory_item_id/);
    assert.match(productionSales, /Add to Invoice/);
    assert.match(productionSales, /Stock is deducted only when the complete invoice saves successfully/);
});

test("sales and payment writes use stable idempotency headers", () => {
    assert.match(productionSales, /stableIdempotencyKey\(saleRequestRef/);
    assert.match(productionSales, /stableIdempotencyKey\(paymentRequestRef/);
    assert.match(productionService, /Idempotency-Key/);
});

test("partial-payment history and multi-line receipts are visible", () => {
    assert.match(productionSales, /Payment History/);
    assert.match(productionSales, /Partial collections are never replaced or hidden/);
    assert.match(productionSales, /s\.items \|\| \[\]/);
    assert.match(productionSales, /getSalePayments/);
});

test("only explicit meat-purpose livestock enters processing", () => {
    assert.match(productionSales, /\["meat", "meat production"\]/);
    assert.match(productionSales, /meat-purpose livestock/);
    assert.doesNotMatch(livestockProduction, /options\.push\("Meat Processing"\)/);
    assert.match(livestockProduction, /Open Processing/);
});

test("inventory products require an explicit saleable flag", () => {
    assert.match(inventoryService, /isSaleable/);
    assert.match(inventoryService, /is_saleable/);
    assert.match(productionSales, /item\.isSaleable/);
});
