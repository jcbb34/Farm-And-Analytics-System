'use client';
import dynamic from 'next/dynamic';
import ProtectedRoute from '../../../components/Auth/ProtectedRoute.jsx';
import PageState from '../../../components/Common/PageState.jsx';
const FarmPlan = dynamic(() => import('../../../views/FarmPlan/FarmPlan.jsx'), { ssr: false,
    loading: () => <PageState type="loading" title="Loading Farm Areas" message="Loading your crop and facility master plan." /> });
export default function FarmPlanPage() {
    return <ProtectedRoute permission="crops:view"><FarmPlan /></ProtectedRoute>;
}
