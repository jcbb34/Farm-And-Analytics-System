"use client";

import dynamic from "next/dynamic";

import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const Inventory = dynamic(
    () => import("../../../views/Inventory/Inventory.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Inventory"
                message="Preparing this Joross Farm module."
            />
        ),
    }
);

export default function InventoryPage() {
    return (
        <ProtectedRoute permission="inventory:view">
            <Inventory />
        </ProtectedRoute>
    );
}
