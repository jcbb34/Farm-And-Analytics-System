"use client";

import dynamic from "next/dynamic";

import PageState from "../components/Common/PageState.jsx";

export function createClientPage(importer) {
    return dynamic(importer, {
        ssr: false,
        loading: () => (
            <PageState
                type="loading"
                title="Loading Joross Farm"
                message="Preparing this module."
            />
        ),
    });
}
