import { httpClient } from "./httpClient.js";

const base = "/production-sales";

export const productionSalesService = Object.freeze({
    getOverview() {
        return httpClient.get(`${base}/overview`);
    },

    getReproduction(options = {}) {
        return httpClient.get(`${base}/reproduction`, { query: options });
    },
    createReproduction(payload, { idempotencyKey = null } = {}) {
        return httpClient.post(`${base}/reproduction`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
    },

    getProduction(options = {}) {
        return httpClient.get(`${base}/production`, { query: options });
    },
    createProduction(payload, { idempotencyKey = null } = {}) {
        return httpClient.post(`${base}/production`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
    },

    getProcessing(options = {}) {
        return httpClient.get(`${base}/processing`, { query: options });
    },
    createProcessing(payload, { idempotencyKey = null } = {}) {
        return httpClient.post(`${base}/processing`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
    },
    voidProcessing(processingId, reason) {
        return httpClient.post(`${base}/processing/${processingId}/void`, { reason });
    },

    getSales(options = {}) {
        return httpClient.get(`${base}/sales`, { query: options });
    },
    createSale(payload, { idempotencyKey = null } = {}) {
        return httpClient.post(`${base}/sales`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
    },
    getSalePayments(saleId) {
        return httpClient.get(`${base}/sales/${saleId}/payments`);
    },
    getSaleReceipt(saleId) {
        return httpClient.get(`${base}/sales/${saleId}/receipt`);
    },
    addSalePayment(saleId, payload, { idempotencyKey = null } = {}) {
        return httpClient.post(`${base}/sales/${saleId}/payments`, payload, {
            headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
        });
    },
    voidSale(saleId, reason) {
        return httpClient.post(`${base}/sales/${saleId}/void`, { reason });
    },
});
