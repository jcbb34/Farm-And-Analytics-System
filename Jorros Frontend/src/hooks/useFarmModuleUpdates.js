"use client";

import { useEffect, useRef } from "react";
import { notifyInfo } from "../context/NotificationContext.jsx";

/** Refresh a mounted module only; never overwrite an active unsaved form. */
export default function useFarmModuleUpdates(modules, refresh, { editing = false } = {}) {
    const refreshRef = useRef(refresh);
    const editingRef = useRef(editing);
    const pendingRef = useRef(false);
    const runningRef = useRef(false);
    const flushRef = useRef(() => {});
    refreshRef.current = refresh;
    editingRef.current = editing;
    const moduleKey = modules.join("|");

    useEffect(() => {
        const relevant = new Set(moduleKey.split("|"));
        let timer, active = true;
        const blocked = () => document.visibilityState === "hidden" || editingRef.current || Boolean(document.querySelector('[role="dialog"], dialog[open]'));
        const flush = () => {
            if (!active || !pendingRef.current || blocked() || runningRef.current) return;
            clearTimeout(timer);
            timer = setTimeout(async () => {
                if (blocked() || runningRef.current) return;
                pendingRef.current = false; runningRef.current = true;
                try { await refreshRef.current(); } catch { /* The page owns its load error and Retry action. */ }
                finally { runningRef.current = false; if (pendingRef.current) flush(); }
            }, 150);
        };
        flushRef.current = flush;
        const queue = () => { pendingRef.current = true; flush(); };
        const onUpdate = (event) => {
            if (!(event.detail?.modules || []).some((name) => relevant.has(name))) return;
            if (blocked() && !pendingRef.current && document.visibilityState !== "hidden") notifyInfo("Updates will appear when you finish or close the current form.");
            queue();
        };
        const observer = new MutationObserver(flush);
        observer.observe(document.body, { childList: true, subtree: true });
        window.addEventListener("joross:modules-updated", onUpdate);
        window.addEventListener("focus", queue);
        window.addEventListener("online", queue);
        window.addEventListener("joross:auth-changed", queue);
        window.addEventListener("joross:activities-updated", queue);
        document.addEventListener("visibilitychange", queue);
        return () => {
            active = false; clearTimeout(timer); observer.disconnect();
            window.removeEventListener("joross:modules-updated", onUpdate);
            window.removeEventListener("focus", queue); window.removeEventListener("online", queue);
            window.removeEventListener("joross:auth-changed", queue); window.removeEventListener("joross:activities-updated", queue);
            document.removeEventListener("visibilitychange", queue);
        };
    }, [moduleKey]);
    useEffect(() => { if (!editing) flushRef.current(); }, [editing]);
}
