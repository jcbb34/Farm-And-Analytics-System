"use client";

import { RecordFilters, RecordSearch, RecordDateFilter } from "../../../components/Records/RecordsLayout.jsx";

// Choices used by the report filters
const categories = [
    "Workforce",
    "Tasks",
    "Care Compliance",
    "Audit",
    "Farm",
    "Crop",
    "Livestock",
    "Production & Sales",
    "Trend & Seasonal",
    "Inventory",
];

const statuses = [
    "Draft",
    "For Review",
    "Approved",
    "In Progress",
    "Needs Review",
    "Final",
    "Revised",
    "Failed",
];

// Search and filter controls for the reports list
function ReportsFilters({
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
        <RecordFilters className="reports-page-filter-row" label="Report filters">
            <RecordSearch label="Search reports" placeholder="Search reports..." value={searchText} onChange={(event) => onSearchChange(event.target.value)}/>

            <select aria-label="Report category"
                value={categoryFilter}
                onChange={(event) =>
                    onCategoryChange(event.target.value)
                }
            >
                <option value="All">All Categories</option>

                {categories.map((category) => (
                    <option key={category} value={category}>
                        {category}
                    </option>
                ))}
            </select>

            <select aria-label="Report status"
                value={statusFilter}
                onChange={(event) =>
                    onStatusChange(event.target.value)
                }
            >
                <option value="All">All Status</option>

                {statuses.map((status) => (
                    <option key={status} value={status}>
                        {status}
                    </option>
                ))}
            </select>

            <RecordDateFilter label="Report period from" title="Start date" prefix="From" value={startDate} onChange={(event) => onStartDateChange(event.target.value)}/>

            <RecordDateFilter label="Report period to" title="End date" prefix="To" value={endDate} onChange={(event) => onEndDateChange(event.target.value)}/>

            <button
                type="button"
                className="reports-page-reset-button"
                onClick={onReset}
            >
                <span className="material-symbols-outlined">
                    restart_alt
                </span>
                Reset
            </button>
        </RecordFilters>
    );
}

export default ReportsFilters;
