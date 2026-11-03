"use client";
import dynamic from "next/dynamic";
import ProtectedRoute from "../../../components/Auth/ProtectedRoute.jsx";
import PageState from "../../../components/Common/PageState.jsx";
const View = dynamic(() => import("../../../views/StaffCalendar/StaffCalendar.jsx"), { ssr:false, loading:()=> <PageState type="loading" title="Loading Staff Calendar" message="Preparing work schedules and availability."/> });
export default function Page(){return <ProtectedRoute permission={["workforce:attendance","workforce:manage"]}><View/></ProtectedRoute>}
