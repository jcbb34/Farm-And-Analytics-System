"use client";

import { useRouter } from "next/navigation";

import PageState from "../components/Common/PageState.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { getAccessDeniedFallback } from "../utils/accessControl.js";

export default function NotFound() {
    const router = useRouter();
    const { isAuthenticated, user } = useAuth();
    const fallback = getAccessDeniedFallback(user);

    return (
        <PageState
            type="empty"
            title="Page Not Found"
            message="The requested Joross Farm page does not exist or may have been moved."
            actionLabel={
                isAuthenticated
                    ? fallback.label
                    : "Return to Login"
            }
            onAction={() =>
                router.push(
                    isAuthenticated
                        ? fallback.destination
                        : "/login"
                )
            }
        />
    );
}
