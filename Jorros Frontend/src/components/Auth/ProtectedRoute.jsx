"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import PageState from "../Common/PageState.jsx";
import AccessDenied from "../Common/AccessDenied.jsx";
import { DASHBOARD_HOME_ROUTE } from "../../utils/accessControl.js";

function ProtectedRoute({ permission, allowedRoles = null, children }) {
    const router = useRouter();
    const pathname = usePathname();
    const {
        isAuthenticated,
        isLoading,
        hasPermission,
        user,
    } = useAuth();

    useEffect(() => {
        if (isLoading || isAuthenticated) {
            return;
        }

        const currentPath =
            typeof window !== "undefined"
                ? `${window.location.pathname}${window.location.search}`
                : pathname || DASHBOARD_HOME_ROUTE;

        router.replace(
            `/login?from=${encodeURIComponent(currentPath)}`
        );
    }, [
        isAuthenticated,
        isLoading,
        pathname,
        router,
    ]);

    if (isLoading || !isAuthenticated) {
        return (
            <PageState
                type="loading"
                title="Checking your session"
                message="Please wait while Joross Farm verifies your account."
            />
        );
    }

    const permissionAllowed = Array.isArray(permission)
        ? permission.some((item) => hasPermission(item))
        : !permission || hasPermission(permission);

    if (!permissionAllowed) {
        return <AccessDenied permission={Array.isArray(permission) ? permission.join(" or ") : permission} />;
    }

    if (Array.isArray(allowedRoles) && allowedRoles.length) {
        const currentRole = String(user?.role || "").trim();
        if (!allowedRoles.includes(currentRole)) {
            return <AccessDenied />;
        }
    }

    return children;
}

export default ProtectedRoute;
