import { useEffect, useMemo, useState } from "react";

// Page filters, tabs, and summary values
export default function useReportsPageState() {
    const [activeTab, setActiveTab] = useState("All Reports");
    const [searchText, setSearchText] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("All");
    const [statusFilter, setStatusFilter] = useState("All");
    const [startDateFilter, setStartDateFilter] = useState("");
    const [endDateFilter, setEndDateFilter] = useState("");
    const [settledSearch, setSettledSearch] = useState("");

    useEffect(() => {
        const timer = window.setTimeout(() => setSettledSearch(searchText.trim()), 250);
        return () => window.clearTimeout(timer);
    }, [searchText]);

    const reportQuery = useMemo(() => ({
        tab: activeTab === "All Reports" ? undefined : activeTab,
        search: settledSearch || undefined,
        category: categoryFilter === "All" ? undefined : categoryFilter,
        status: statusFilter === "All" ? undefined : statusFilter,
        startDate: startDateFilter || undefined,
        endDate: endDateFilter || undefined,
    }), [
        activeTab,
        settledSearch,
        categoryFilter,
        statusFilter,
        startDateFilter,
        endDateFilter,
    ]);

    const clearFilters = () => {
        setSearchText("");
        setCategoryFilter("All");
        setStatusFilter("All");
        setStartDateFilter("");
        setEndDateFilter("");
    };

    return {
        activeTab,
        setActiveTab,
        searchText,
        setSearchText,
        categoryFilter,
        setCategoryFilter,
        statusFilter,
        setStatusFilter,
        startDateFilter,
        setStartDateFilter,
        endDateFilter,
        setEndDateFilter,
        reportQuery,
        clearFilters,
    };
}
