import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import nextConfig from "../next.config.mjs";
import { appConfig } from "../src/config/appConfig.js";
import { createRequestUrl } from "../src/services/httpClient.js";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("Next.js dev server allows local access and clean current-network origins", () => {
    assert.ok(nextConfig.allowedDevOrigins.includes("localhost"));
    assert.ok(nextConfig.allowedDevOrigins.includes("127.0.0.1"));
    assert.ok(nextConfig.allowedDevOrigins.every((origin) => origin === origin.trim()));
});

test("browser API calls use the same-origin proxy instead of a Wi-Fi IP", async () => {
    const rewrites = await nextConfig.rewrites();
    const apiProxy = rewrites.find((rule) => rule.source === "/api/v1/:path*");

    assert.ok(apiProxy, "the backend API proxy must be configured");
    assert.equal(
        apiProxy.destination,
        "http://127.0.0.1:8000/api/v1/:path*"
    );

    for (const envFile of ["../.env.local", "../.env.local.example"]) {
        // Clean source archives intentionally omit the machine's private env.
        if (!existsSync(new URL(envFile, import.meta.url))) continue;
        const env = read(envFile);
        assert.match(env, /^NEXT_PUBLIC_API_BASE_URL=\/api\/v1$/m);
        assert.match(env, /^BACKEND_API_ORIGIN=http:\/\/127\.0\.0\.1:8000$/m);
        assert.doesNotMatch(env, /^NEXT_PUBLIC_API_BASE_URL=https?:\/\//m);
    }

    const originalWindow = globalThis.window;
    globalThis.window = { location: { origin: "http://farm-phone.local:3000" } };
    try {
        assert.equal(appConfig.apiBaseUrl, "/api/v1");
        assert.equal(createRequestUrl("/crops", { limit: 25 }),
            "http://farm-phone.local:3000/api/v1/crops?limit=25");
    } finally { globalThis.window = originalWindow; }
});
