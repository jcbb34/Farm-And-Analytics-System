"use client";

import ProtectedRoute from "../../components/Auth/ProtectedRoute.jsx";

export default function ProtectedLayout({ children }) {
    return (
        <ProtectedRoute>
            {children}
        </ProtectedRoute>
    );
}
