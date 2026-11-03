"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import PageState from "../Common/PageState.jsx";
import { getHomeRoute } from "../../utils/accessControl.js";

function PublicOnlyRoute({ children }) {
    const router = useRouter();
    const { isAuthenticated, isLoading, user } = useAuth();

    useEffect(() => {
        if (!isLoading && isAuthenticated) {
            router.replace(getHomeRoute(user));
        }
    }, [isAuthenticated, isLoading, router, user]);

    if (isLoading || isAuthenticated) {
        return (
            <PageState
                type="loading"
                title="Loading Joross Farm"
                message="Preparing the sign-in page."
            />
        );
    }

    return children;
}

export default PublicOnlyRoute;
