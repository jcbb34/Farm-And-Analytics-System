"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useAuth } from "./AuthContext.jsx";
import { createRequestUrl, getStoredAccessToken, invalidateReadCache } from "../services/httpClient.js";
import { parseEventFrames } from "../services/eventFrames.js";

const VISIBLE_MODULES = {
    "/dashboard": ["dashboard", "tasks", "crops", "livestock", "inventory", "production_sales", "weather", "alerts"],
    "/task-management": ["archives", "tasks", "employees", "calendar", "care_templates", "inventory", "crops", "livestock"],
    "/my-tasks": ["my_tasks", "calendar"],
    "/staff-calendar": ["calendar", "tasks", "employees"],
    "/crops": ["archives", "crops", "production_sales"], "/livestock": ["archives", "livestock", "inventory"],
    "/inventory": ["archives", "inventory"], "/production-sales": ["production_sales", "crops", "livestock"],
    "/intelligence": ["intelligence", "crops", "livestock", "inventory", "weather"],
    "/alerts": ["alerts"], "/reports": ["archives", "reports"], "/settings": ["archives", "settings", "users"],
};

export default function RealTimeProvider({ children }) {
    const { isAuthenticated, isLoading, user } = useAuth();
    const pathname = usePathname();
    const pathnameRef = useRef(pathname);
    pathnameRef.current = pathname;
    const [disconnected, setDisconnected] = useState(false);

    useEffect(() => {
        if (isLoading || !isAuthenticated) return undefined;
        let stopped = false;
        let connected = false;
        let hadFailure = false;
        let lastEventId = "";
        let backoff = 1000;
        let warningTimer = null;
        let debounceTimer = null;
        const controller = new AbortController();
        const seen = new Set();
        const pendingModules = new Set();
        const visible = () => VISIBLE_MODULES[pathnameRef.current] || [];
        const dispatchUpdates = (modules) => {
            if (document.visibilityState === "hidden") return;
            if (modules.includes("alerts") || modules.includes("notifications")) {
                invalidateReadCache();
                window.dispatchEvent(new CustomEvent("joross:alerts-updated"));
            }
            const affected = modules.filter((name) => visible().includes(name));
            if (!affected.length) return;
            invalidateReadCache();
            window.dispatchEvent(new CustomEvent("joross:modules-updated", { detail: { modules: affected } }));
            if (affected.some((name) => ["tasks", "my_tasks"].includes(name))) {
                window.dispatchEvent(new CustomEvent("joross:activities-updated"));
            }
            if (affected.includes("livestock")) window.dispatchEvent(new CustomEvent("joross:livestock-updated"));
            if (affected.some((name) => ["crops", "dashboard", "production_sales", "inventory"].includes(name))) {
                window.dispatchEvent(new CustomEvent("joross:farm-data-updated", { detail: { sourceModule: "Committed Change" } }));
            }
        };
        const queue = (modules) => {
            modules.forEach((name) => pendingModules.add(name));
            if (debounceTimer) return;
            debounceTimer = window.setTimeout(() => {
                debounceTimer = null;
                const changed = [...pendingModules];
                pendingModules.clear();
                dispatchUpdates(changed);
            }, 250);
        };
        const onOnline = () => { if (!connected) queue(visible()); };
        const onVisibility = () => { if (document.visibilityState === "visible") queue(visible()); };
        window.addEventListener("online", onOnline);
        document.addEventListener("visibilitychange", onVisibility);
        const fallback = window.setInterval(() => {
            if (!connected && navigator.onLine && document.visibilityState !== "hidden") queue(visible());
        }, 20000);

        const connect = async () => {
            while (!stopped) {
                const attempt = new AbortController();
                const abort = () => attempt.abort();
                controller.signal.addEventListener("abort", abort, { once: true });
                try {
                    const token = getStoredAccessToken();
                    if (!token) break;
                    const response = await fetch(createRequestUrl("/events/stream"), {
                        headers: { Accept: "text/event-stream", Authorization: `Bearer ${token}`,
                            ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) },
                        credentials: "include", cache: "no-store", signal: attempt.signal,
                    });
                    if (!response.ok || !response.body) throw new Error(`Event stream ${response.status}`);
                    const wasDisconnected = hadFailure;
                    connected = true;
                    hadFailure = false;
                    backoff = 1000;
                    setDisconnected(false);
                    window.dispatchEvent(new CustomEvent("joross:realtime-connection", { detail: { connected: true } }));
                    if (warningTimer) window.clearTimeout(warningTimer);
                    warningTimer = null;
                    if (wasDisconnected) queue(visible());
                    const reader = response.body.getReader();
                    const decoder = new TextDecoder();
                    let buffer = "";
                    while (!stopped) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        buffer = parseEventFrames(buffer + decoder.decode(value, { stream: true }), (frame) => {
                            if (frame.event === "reconnect") { attempt.abort(); return; }
                            if (frame.event === "ready") { queue(visible()); return; }
                            if (frame.event !== "change" || !frame.data) return;
                            const notice = JSON.parse(frame.data);
                            if (seen.has(notice.id)) return;
                            seen.add(notice.id);
                            if (seen.size > 300) seen.delete(seen.values().next().value);
                            lastEventId = String(notice.id);
                            queue(notice.modules || []);
                        });
                    }
                } catch {
                    // A network interruption uses bounded polling until reconnect.
                } finally {
                    controller.signal.removeEventListener("abort", abort);
                    if (!stopped) {
                        connected = false;
                        hadFailure = true;
                        window.dispatchEvent(new CustomEvent("joross:realtime-connection", { detail: { connected: false } }));
                        if (!warningTimer) warningTimer = window.setTimeout(() => {
                            if (!stopped && !connected) setDisconnected(true);
                        }, 5000);
                    }
                }
                if (stopped) break;
                await new Promise((resolve) => window.setTimeout(resolve, backoff));
                backoff = Math.min(backoff * 2, 30000);
            }
        };
        void connect();
        return () => {
            stopped = true;
            controller.abort();
            window.clearInterval(fallback);
            if (debounceTimer) window.clearTimeout(debounceTimer);
            if (warningTimer) window.clearTimeout(warningTimer);
            window.removeEventListener("online", onOnline);
            document.removeEventListener("visibilitychange", onVisibility);
        };
    }, [isAuthenticated, isLoading, user?.id]);

    return <>{children}{disconnected && <div role="status" className="farm-reconnect-notice">
        Farm updates are reconnecting. Changes will sync when the local network returns.
    </div>}</>;
}
