"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Settings = dynamic(
    () => import("../../../views/Settings/Settings.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Settings"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function SettingsPage() {
    return (
        <ProtectedRoute permission="*">
            <Settings />
        </ProtectedRoute>
    );
}
