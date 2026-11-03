import { httpClient } from "./httpClient.js";

export function createCrudService(resourcePath) {
    const basePath = resourcePath.startsWith("/")
        ? resourcePath
        : `/${resourcePath}`;

    return Object.freeze({
        list: (query, options = {}) =>
            httpClient.get(basePath, {
                ...options,
                query,
            }),

        getById: (id, options = {}) =>
            httpClient.get(
                `${basePath}/${encodeURIComponent(id)}`,
                options
            ),

        create: (payload, options = {}) =>
            httpClient.post(basePath, payload, options),

        update: (id, payload, options = {}) =>
            httpClient.put(
                `${basePath}/${encodeURIComponent(id)}`,
                payload,
                options
            ),

        patch: (id, payload, options = {}) =>
            httpClient.patch(
                `${basePath}/${encodeURIComponent(id)}`,
                payload,
                options
            ),

        remove: (id, options = {}) =>
            httpClient.delete(
                `${basePath}/${encodeURIComponent(id)}`,
                options
            ),

        archive: (id, reason, options = {}) =>
            httpClient.post(
                `${basePath}/${encodeURIComponent(id)}/archive`,
                { reason },
                options
            ),

        restore: (id, options = {}) =>
            httpClient.post(
                `${basePath}/${encodeURIComponent(id)}/restore`,
                {},
                options
            ),
    });
}
