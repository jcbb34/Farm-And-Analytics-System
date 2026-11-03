"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Alerts = dynamic(
    () => import("../../../views/Alerts/Alerts.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Alerts"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function AlertsPage() {
    return (
        <ProtectedRoute permission="alerts:view">
            <Alerts />
        </ProtectedRoute>
    );
}
