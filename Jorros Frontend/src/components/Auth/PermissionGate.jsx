"use client";

import { useAuth } from "../../context/AuthContext.jsx";

function PermissionGate({
    permission,
    children,
    fallback = null,
    mode = "hide",
}) {
    const { hasPermission } = useAuth();
    const allowed = hasPermission(permission);

    if (allowed) {
        return children;
    }

    if (mode === "disable" && children) {
        return (
            <span
                className="app-permission-disabled-wrapper"
                title="Your account does not have permission to use this action."
            >
                {children}
            </span>
        );
    }

    return fallback;
}

export default PermissionGate;
