"use client";

import dynamic from "next/dynamic";
import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const ProductionSales = dynamic(
    () => import("../../../views/ProductionSales/ProductionSales.jsx"),
    {
        ssr: false,
        loading: () => <PageState type="loading" title="Loading Production & Sales" message="Preparing livestock production and transaction records." />,
    }
);

export default function ProductionSalesPage() {
    return <ProtectedRoute permission="production_sales:view"><ProductionSales /></ProtectedRoute>;
}
