"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const FarmIntelligence = dynamic(
    () => import("../../../views/FarmIntelligence/FarmIntelligence.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading FarmIntelligence"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function FarmIntelligencePage() {
    return (
        <ProtectedRoute permission="intelligence:view">
            <FarmIntelligence />
        </ProtectedRoute>
    );
}
