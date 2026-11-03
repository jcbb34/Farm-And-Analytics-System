"use client";

import ReportsFilters from "./ReportsFilters.jsx";

const REPORT_TABS = [
    "All Reports",
    "Farm Performance",
    "Workforce Reports",
    "Task Reports",
    "Care Compliance",
    "Crop Reports",
    "Livestock Reports",
    "Production & Sales",
    "Trend & Seasonal Analysis",
    "Inventory Reports",
    "Audit Trail",
];

// Tabs, report actions, and filters
function ReportsToolbar({
    activeTab,
    onTabChange,
    searchText,
    onSearchChange,
    categoryFilter,
    onCategoryChange,
    statusFilter,
    onStatusChange,
    startDate,
    onStartDateChange,
    endDate,
    onEndDateChange,
    onReset,
}) {
    return (
        <>
        <section className="reports-page-management-card">
            <div className="reports-page-tabs-row">
                <div className="reports-page-tabs">
                    {REPORT_TABS.map((tab) => (
                        <button
                            type="button"
                            key={tab}
                            className={activeTab === tab ? "active" : ""}
                            onClick={() => onTabChange(tab)}
                        >
                            {tab}
                        </button>
                    ))}
                </div>


            </div>

        </section>

            <ReportsFilters
                searchText={searchText}
                onSearchChange={onSearchChange}
                categoryFilter={categoryFilter}
                onCategoryChange={onCategoryChange}
                statusFilter={statusFilter}
                onStatusChange={onStatusChange}
                startDate={startDate}
                onStartDateChange={onStartDateChange}
                endDate={endDate}
                onEndDateChange={onEndDateChange}
                onReset={onReset}
            />
        </>
    );
}

export default ReportsToolbar;
