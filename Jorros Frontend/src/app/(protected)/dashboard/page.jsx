"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Dashboard = dynamic(
    () => import("../../../views/Dashboard/Dashboard.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Dashboard"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function DashboardPage() {
    return (
        <ProtectedRoute permission="dashboard:view">
            <Dashboard />
        </ProtectedRoute>
    );
}
