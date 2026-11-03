"use client";

import { useRouter } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import { getAccessDeniedFallback } from "../../utils/accessControl.js";
import "./AccessDenied.css";

function AccessDenied({ permission }) {
    const router = useRouter();
    const { user } = useAuth();
    const fallback = getAccessDeniedFallback(user);

    return (
        <main className="app-access-denied-page">
            <section className="app-access-denied-card">
                <span className="material-symbols-outlined">
                    lock
                </span>

                <h1>Access Restricted</h1>

                <p>
                    The <strong>{user?.role || "current"}</strong>{" "}
                    account does not have permission to open this area.
                </p>

                {permission && (
                    <small>Required permission: {permission}</small>
                )}

                <button
                    type="button"
                    onClick={() => router.replace(fallback.destination)}
                >
                    {fallback.label}
                </button>
            </section>
        </main>
    );
}

export default AccessDenied;
