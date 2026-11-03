"use client";
import dynamic from "next/dynamic";
import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";
const View = dynamic(() => import("../../../views/TaskManagement/TaskManagement.jsx"), { ssr:false, loading:()=> <PageState type="loading" title="Loading Task Management" message="Preparing employee assignments and reviews."/> });
export default function Page(){return <ProtectedRoute permission="workforce:manage"><View/></ProtectedRoute>}
