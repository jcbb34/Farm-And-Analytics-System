"use client";
import dynamic from "next/dynamic";
import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";
const View = dynamic(() => import("../../../views/MyTasks/MyTasks.jsx"), { ssr:false, loading:()=> <PageState type="loading" title="Loading My Tasks" message="Preparing your assigned farm work."/> });
export default function Page(){return <ProtectedRoute permission="workforce:submit"><View/></ProtectedRoute>}
