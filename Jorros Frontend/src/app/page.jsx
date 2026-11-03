"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import PageState from "../components/Common/PageState.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getHomeRoute } from "../utils/accessControl.js";

export default function HomePage() {
    const router = useRouter();
    const { isAuthenticated, isLoading, user } = useAuth();

    useEffect(() => {
        if (isLoading) {
            return;
        }

        const destination = isAuthenticated ? getHomeRoute(user) : "/login";
        router.replace(destination);

        // On some phones using the Next development server over a farm WLAN,
        // client navigation can occasionally fail to commit even though the
        // page hydrated. Fall back to a normal navigation instead of leaving
        // the employee on the session-check screen forever.
        const fallbackTimer = window.setTimeout(() => {
            if (window.location.pathname === "/") {
                window.location.replace(destination);
            }
        }, 1200);

        return () => window.clearTimeout(fallbackTimer);
    }, [isAuthenticated, isLoading, router, user]);

    return (
        <PageState
            type="loading"
            title="Loading Joross Farm"
            message="Checking your current session."
        />
    );
}
