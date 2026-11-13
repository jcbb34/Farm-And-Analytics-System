"use client";

import { useEffect, useRef, useState } from "react";
import { workforceService } from "../../services/workforceService.js";

export function useNearViewport(target, identity) {
    const [visibleIdentity, setVisibleIdentity] = useState("");
    useEffect(() => {
        setVisibleIdentity("");
        if (!identity || !target.current) return;
        if (typeof IntersectionObserver === "undefined") {
            setVisibleIdentity(identity); return;
        }
        let active = true;
        const observer = new IntersectionObserver(entries => {
            if (active && entries.some(entry => entry.isIntersecting)) {
                setVisibleIdentity(identity); observer.disconnect();
            }
        }, { rootMargin: "200px" });
        observer.observe(target.current);
        return () => { active = false; observer.disconnect(); };
    }, [target, identity]);
    return Boolean(identity) && visibleIdentity === identity;
}

/** Cancel obsolete downloads and keep authenticated image bytes in memory only. */
export function useEvidenceImage(evidenceUrl, enabled) {
    const [image, setImage] = useState({ path: "", url: "", error: "", loading: false });
    const [attempt, setAttempt] = useState(0);
    const requestRef = useRef(null);
    useEffect(() => {
        if (!enabled || !evidenceUrl) return;
        const controller = new AbortController();
        const request = {};
        requestRef.current = request;
        let active = true, objectUrl = "";
        setImage({ path: evidenceUrl, url: "", error: "", loading: true, request });
        const download = async () => {
            try {
                const blob = await workforceService.downloadEvidencePhoto(evidenceUrl, { signal: controller.signal, cache: "no-store" });
                if (!active || controller.signal.aborted) return;
                objectUrl = URL.createObjectURL(blob);
                setImage({ path: evidenceUrl, url: objectUrl, error: "", loading: false, request });
            } catch (error) {
                if (active && !controller.signal.aborted) setImage({ path: evidenceUrl, url: "", loading: false, request,
                    error: error?.message || "Unable to load the evidence photo." });
            }
        };
        void download();
        return () => {
            active = false; controller.abort();
            if (requestRef.current === request) requestRef.current = null;
            if (objectUrl) URL.revokeObjectURL(objectUrl);
        };
    }, [evidenceUrl, enabled, attempt]);
    const matching = Boolean(enabled && evidenceUrl) && image.path === evidenceUrl && image.request === requestRef.current;
    return { url: matching ? image.url : "", error: matching ? image.error : "",
        loading: Boolean(enabled && evidenceUrl) && (!matching || image.loading),
        retry: () => setAttempt(value => value + 1) };
}
