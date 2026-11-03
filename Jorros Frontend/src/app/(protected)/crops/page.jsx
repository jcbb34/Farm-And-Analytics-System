"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Crops = dynamic(
    () => import("../../../views/Crops/Crops.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Crops"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function CropsPage() {
    return (
        <ProtectedRoute permission="crops:view">
            <Crops />
        </ProtectedRoute>
    );
}
