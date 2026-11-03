"use client";

import { useEffect } from "react";

const SAFE_CACHE_PREFIX = "joross-safe-assets-";

async function clearDevelopmentPwaState() {
    if ("serviceWorker" in navigator) {
        const registrations = await navigator.serviceWorker.getRegistrations();
        await Promise.all(registrations.map((registration) => registration.unregister()));
    }
    if ("caches" in window) {
        const keys = await caches.keys();
        await Promise.all(
            keys
                .filter((key) => key.startsWith(SAFE_CACHE_PREFIX))
                .map((key) => caches.delete(key)),
        );
    }
}

export default function PwaBootstrap() {
    useEffect(() => {
        if (!("serviceWorker" in navigator)) return undefined;

        // Never let a development localhost session be controlled by a stale PWA
        // worker. Next.js dev chunk URLs can stay the same while source changes,
        // which otherwise makes the browser render an older UI after a restart.
        if (process.env.NODE_ENV !== "production") {
            clearDevelopmentPwaState().catch(() => {});
            return undefined;
        }

        if (!window.isSecureContext && window.location.hostname !== "localhost") return undefined;

        let cancelled = false;
        const register = async () => {
            try {
                const registration = await navigator.serviceWorker.register("/sw.js", { scope: "/" });
                if (!cancelled) registration.update().catch(() => {});
            } catch {
                // The web app remains fully usable when service workers are unavailable.
            }
        };
        register();
        return () => { cancelled = true; };
    }, []);

    return null;
}
