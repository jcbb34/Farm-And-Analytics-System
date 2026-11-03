"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Reports = dynamic(
    () => import("../../../views/Reports/Reports.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Reports"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function ReportsPage() {
    return (
        <ProtectedRoute permission="reports:view">
            <Reports />
        </ProtectedRoute>
    );
}
