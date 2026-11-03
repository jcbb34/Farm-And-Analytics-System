"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Livestock = dynamic(
    () => import("../../../views/Livestock/Livestock.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Livestock"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function LivestockPage() {
    return (
        <ProtectedRoute permission="livestock:view">
            <Livestock />
        </ProtectedRoute>
    );
}
