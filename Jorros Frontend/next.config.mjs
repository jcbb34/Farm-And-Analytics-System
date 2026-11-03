import { hostname, networkInterfaces } from "node:os";

function getLanDevOrigins() {
    const origins = new Set([
        "localhost",
        "127.0.0.1",
    ]);

    const computerName = hostname().trim();
    if (computerName) {
        origins.add(computerName);
        if (!computerName.endsWith(".local")) origins.add(`${computerName}.local`);
    }

    // Keep the server computer's current LAN IPv4 addresses allowed.
    let interfaces = {};
    try {
        interfaces = networkInterfaces();
    } catch {
        // Some containers and restricted Windows sessions cannot enumerate
        // adapters. Explicit and environment-provided origins remain valid.
    }
    for (const addresses of Object.values(interfaces)) {
        for (const address of addresses || []) {
            if (address.family === "IPv4" && !address.internal) {
                origins.add(address.address);
            }
        }
    }

    // Optional comma-separated hostnames/IPs for other trusted development
    // devices or tunnels. Entries must be hostnames only (no scheme/port).
    for (const origin of (process.env.NEXT_ALLOWED_DEV_ORIGINS || "").split(",")) {
        const hostname = origin.trim();
        if (hostname) origins.add(hostname);
    }

    return [...origins];
}

function getBackendApiOrigin() {
    const configured = (
        process.env.BACKEND_API_ORIGIN ||
        "http://127.0.0.1:8000"
    ).trim();
    const url = new URL(configured);

    if (!["http:", "https:"].includes(url.protocol)) {
        throw new Error("BACKEND_API_ORIGIN must use http:// or https://.");
    }

    return configured.replace(/\/+$/, "");
}

/** @type {import('next').NextConfig} */
const securityHeaders = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "same-origin" },
    {
        key: "Permissions-Policy",
        value: "camera=(self), microphone=(), geolocation=()",
    },
];

const nextConfig = {
    agentRules: false,
    allowedDevOrigins: getLanDevOrigins(),
    reactStrictMode: true,
    async rewrites() {
        return [
            {
                source: "/api/v1/:path*",
                destination: `${getBackendApiOrigin()}/api/v1/:path*`,
            },
        ];
    },
    async headers() {
        return [
            {
                source: "/:path*",
                headers: securityHeaders,
            },
        ];
    },
};

export default nextConfig;
