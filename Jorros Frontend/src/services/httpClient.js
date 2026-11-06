import { appConfig, storageKeys } from "../config/appConfig.js";

import { publishSessionSignal, sessionIdentity } from "./sessionPolicy.js";

export class ApiError extends Error {
    constructor(
        message,
        {
            status = 0,
            code = "API_ERROR",
            details = null,
            response = null,
        } = {}
    ) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.code = code;
        this.details = details;
        this.response = response;
    }
}

export function getStoredAccessToken() {
    try {
        return JSON.parse(sessionStorage.getItem(storageKeys.authSession) || "null")?.accessToken || "";
    } catch { return ""; }

}


function clearStoredAuthSession() {
    if (typeof window === "undefined") {
        return;
    }

    try {
        const current = JSON.parse(sessionStorage.getItem(storageKeys.authSession) || "null");
        publishSessionSignal("logout", sessionIdentity(current));
    } catch { /* Corrupt browser state must still be cleared below. */ }
    for (const storageName of ["localStorage", "sessionStorage"]) {
        for (const key of [storageKeys.authSession, storageKeys.legacyAuthenticated, storageKeys.profile]) {
            try { (storageName === "localStorage" ? localStorage : sessionStorage).removeItem(key); } catch { /* Continue clearing the other storage. */ }
        }
    }

    window.dispatchEvent(
        new CustomEvent("joross:auth-changed", {
            detail: null,
        })
    );
}

export function createRequestUrl(path, query) {
    const cleanPath = String(path || "").startsWith("/")
        ? path
        : `/${path}`;
    const url = new URL(
        `${appConfig.apiBaseUrl}${cleanPath}`,
        `${window.location.origin}/`
    );

    if (query && typeof query === "object") {
        Object.entries(query).forEach(([key, value]) => {
            if (
                value === undefined ||
                value === null ||
                value === ""
            ) {
                return;
            }

            if (Array.isArray(value)) {
                value.forEach((item) =>
                    url.searchParams.append(key, item)
                );
                return;
            }

            url.searchParams.set(key, String(value));
        });
    }

    return url.toString();
}

async function parseResponse(response) {
    const contentType =
        response.headers.get("content-type") || "";

    if (response.status === 204) {
        return null;
    }

    if (contentType.includes("application/json")) {
        return response.json();
    }

    const text = await response.text();
    return text || null;
}

async function request(
    path,
    {
        method = "GET",
        query,
        body,
        headers = {},
        signal,
        timeoutMs = appConfig.requestTimeoutMs,
        includeAuth = true,
        isFormData = false,
        responseType = "auto",
        cache = "default",
    } = {}
) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(
        () => controller.abort("Request timed out"),
        timeoutMs
    );

    const abortFromExternalSignal = () =>
        controller.abort(signal?.reason);

    if (signal) {
        if (signal.aborted) {
            controller.abort(signal.reason);
        } else {
            signal.addEventListener(
                "abort",
                abortFromExternalSignal,
                { once: true }
            );
        }
    }

    const requestHeaders = {
        Accept: "application/json",
        ...headers,
    };

    if (!isFormData && body !== undefined) {
        requestHeaders["Content-Type"] =
            "application/json";
    }

    let accessToken = "";

    if (includeAuth) {
        accessToken = getStoredAccessToken();

        if (accessToken) {
            requestHeaders.Authorization =
                `Bearer ${accessToken}`;
        }
    }

    try {
        const requestUrl = createRequestUrl(path, query);
        const fetchOptions = {
            method,
            headers: requestHeaders,
            credentials: "include",
            signal: controller.signal,
            cache,
            body:
                body === undefined
                    ? undefined
                    : isFormData
                      ? body
                      : JSON.stringify(body),
        };

        let response;
        try {
            response = await fetch(requestUrl, fetchOptions);
        } catch (fetchError) {
            const mayRetryTransientGet = String(method).toUpperCase() === "GET"
                && !controller.signal.aborted
                && !(signal?.aborted);
            if (!mayRetryTransientGet) throw fetchError;

            await new Promise((resolve) => window.setTimeout(resolve, 300));
            if (controller.signal.aborted || signal?.aborted) throw fetchError;
            response = await fetch(requestUrl, fetchOptions);
        }

        const data = (response.ok && responseType === "blob")
            ? await response.blob()
            : await parseResponse(response);

        if (!response.ok) {
            if (
                response.status === 401 &&
                includeAuth &&
                accessToken &&
                // A request from the previous user can finish after a new
                // user has logged in. Only revoke the token that failed.
                getStoredAccessToken() === accessToken
            ) {
                clearStoredAuthSession();
            }

            const message =
                data?.message ||
                data?.detail ||
                `Request failed with status ${response.status}.`;

            throw new ApiError(message, {
                status: response.status,
                code: data?.code || "HTTP_ERROR",
                details:
                    data?.errors || data?.details || (response.headers.get("X-Existing-Task-Id") ? { existingTaskId: Number(response.headers.get("X-Existing-Task-Id")) } : null),
                response: data,
            });
        }

        if (String(method).toUpperCase() !== "GET") invalidateReadCache();
        return data;
    } catch (error) {
        if (error instanceof ApiError) {
            throw error;
        }

        if (controller.signal.aborted) {
            throw new ApiError(
                "The request took too long or was cancelled.",
                {
                    code: "REQUEST_ABORTED",
                }
            );
        }

        throw new ApiError(
            error?.message ||
                "The backend could not be reached.",
            {
                code: "NETWORK_ERROR",
            }
        );
    } finally {
        window.clearTimeout(timeoutId);

        if (signal) {
            signal.removeEventListener(
                "abort",
                abortFromExternalSignal
            );
        }
    }
}

// Small memory-only cache. The auth token is part of the key, and no private
// data is persisted to shared browser storage.
const inFlightReads = new Map();
const recentReads = new Map();
let readGeneration = 0;
const READ_TTL_MS = 2500;

export function invalidateReadCache() {
    readGeneration += 1;
    recentReads.clear();
    inFlightReads.clear();
}

function startRead(key, path, options) {
    const generation = readGeneration;
    const pending = request(path, { ...options, method: "GET" }).then((data) => {
        if (generation === readGeneration && options.cache !== "no-store") {
            recentReads.set(key, { data, time: Date.now() });
            if (recentReads.size > 60) recentReads.delete(recentReads.keys().next().value);
        }
        return data;
    }).finally(() => {
        if (inFlightReads.get(key) === pending) inFlightReads.delete(key);
    });
    inFlightReads.set(key, pending);
    return pending;
}

function getRead(path, options = {}) {
    if (options.signal || options.responseType === "blob" || Object.keys(options.headers || {}).length) {
        return request(path, { ...options, method: "GET" });
    }
    const token = options.includeAuth === false ? "public" : getStoredAccessToken();
    const key = `${token}|${createRequestUrl(path, options.query)}`;
    const pending = inFlightReads.get(key);
    if (pending) return pending;
    const cached = options.cache !== "no-store" ? recentReads.get(key) : null;
    const age = cached ? Date.now() - cached.time : Infinity;
    if (age < READ_TTL_MS) {
        if (age > 750) queueMicrotask(() => {
            if (!inFlightReads.has(key)) startRead(key, path, options).catch(() => {});
        });
        return Promise.resolve(cached.data);
    }
    return startRead(key, path, options);
}

if (typeof window !== "undefined") {
    window.addEventListener("joross:auth-changed", invalidateReadCache);
    window.addEventListener("storage", (event) => {
        if (event.key === storageKeys.authSession) invalidateReadCache();
    });
}

export const httpClient = Object.freeze({
    get: (path, options = {}) => getRead(path, options),

    post: (path, body, options = {}) =>
        request(path, {
            ...options,
            method: "POST",
            body,
        }),

    put: (path, body, options = {}) =>
        request(path, {
            ...options,
            method: "PUT",
            body,
        }),

    patch: (path, body, options = {}) =>
        request(path, {
            ...options,
            method: "PATCH",
            body,
        }),

    delete: (path, options = {}) =>
        request(path, {
            ...options,
            method: "DELETE",
        }),

    upload: (path, formData, options = {}) =>
        request(path, {
            ...options,
            method: options.method || "POST",
            body: formData,
            isFormData: true,
        }),

    download: (path, options = {}) =>
        request(path, {
            ...options,
            method: "GET",
            responseType: "blob",
            headers: {
                Accept: options.accept || "application/octet-stream",
                ...(options.headers || {}),
            },
        }),
});
