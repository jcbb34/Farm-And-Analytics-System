"use client";

import { useMemo, useState } from "react";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import { useAuth } from "../../context/AuthContext.jsx";

import RecommendationPanel from "./components/RecommendationPanel.jsx";
import AuditPanel from "./components/AuditPanel.jsx";
import OverviewPanel from "./components/OverviewPanel.jsx";
import TrendsPanel from "./components/TrendsPanel.jsx";

import "./FarmIntelligence.css";

// Keep Farm Intelligence focused on analysis and decision support. Operational
// task/history/backup workflows remain in their dedicated system areas.
const baseTabs = [
    { id: "overview", label: "Decision Overview", icon: "space_dashboard" },
    { id: "recommendations", label: "Crop Recommendations", icon: "psychiatry" },
    { id: "trends", label: "Trends & Seasonal Analysis", icon: "query_stats" },
];

function FarmIntelligence() {
    const { hasPermission } = useAuth();
    const [activeTab, setActiveTab] = useState("overview");
    const canViewAudit = hasPermission?.("*") === true;
    const tabs = useMemo(
        () => canViewAudit
            ? [
                ...baseTabs,
                { id: "audit", label: "Audit Log", icon: "fact_check" },
            ]
            : baseTabs,
        [canViewAudit]
    );

    return (
        <div className="fi-layout">
            <Sidebar />

            <main className="fi-content">
                <header className="fi-page-header">
                    <div>
                        <h1>Farm Intelligence</h1>
                        <p>
                            Live farm performance, crop recommendations, livestock growth,
                            production and sales signals, seasonal trends, risks, findings,
                            recommended management actions, and data readiness.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <nav className="fi-tabs" aria-label="Farm Intelligence sections">
                    {tabs.map((tab) => (
                        <button
                            key={tab.id}
                            type="button"
                            className={activeTab === tab.id ? "active" : ""}
                            onClick={() => setActiveTab(tab.id)}
                        >
                            <span className="material-symbols-outlined">{tab.icon}</span>
                            <span>{tab.label}</span>
                        </button>
                    ))}
                </nav>

                <div className="fi-tab-content">
                    {activeTab === "overview" && (
                        <OverviewPanel onNavigate={setActiveTab} />
                    )}
                    {activeTab === "recommendations" && <RecommendationPanel />}
                    {activeTab === "trends" && <TrendsPanel />}
                    {activeTab === "audit" && <AuditPanel />}
                </div>
            </main>
        </div>
    );
}

export default FarmIntelligence;
