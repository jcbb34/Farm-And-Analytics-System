"use client";

import dynamic from "next/dynamic";

import PublicOnlyRoute from "../../components/Auth/PublicOnlyRoute.jsx";
import PageState from "../../components/Common/PageState.jsx";

const Login = dynamic(
    () => import("../../views/Login/Login.jsx"),
    {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Joross Farm"
                message="Preparing the sign-in page."
            />
        ),
    }
);

export default function LoginPage() {
    return (
        <PublicOnlyRoute>
            <Login />
        </PublicOnlyRoute>
    );
}
