"use client";

import dynamic from "next/dynamic";
import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";

const EmployeeProfile = dynamic(() => import("../../../views/EmployeeProfile/EmployeeProfile.jsx"), {
    ssr: false,
    loading: () => <PageState type="loading" title="Loading Profile" message="Preparing your employee profile." />,
});

export default function ProfilePage() {
    return <ProtectedRoute permission="workforce:submit"><EmployeeProfile /></ProtectedRoute>;
}
