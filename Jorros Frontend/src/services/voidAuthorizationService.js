import { httpClient } from "./httpClient.js";
export const voidAuthorizationService = Object.freeze({
    preview: (action, recordId, signal) => httpClient.get("/void-authorizations/preview", { query: { action, record_id: recordId }, cache: "no-store", signal }),
    authorize: (payload) => httpClient.post("/void-authorizations", payload),
});
