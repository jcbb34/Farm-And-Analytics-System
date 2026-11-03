"use client";

const alertTabs = ["All Alerts", "Active Alerts", "High Priority"];

// Tabs, actions, search, and filters for the alert table.
export default function AlertsToolbar({
    activeTab,
    onTabChange,
    onOpenSettings,
    onAddAlert,
    searchText,
    onSearchChange,
    categoryFilter,
    onCategoryChange,
    statusFilter,
    onStatusChange,
    categories = [],
    onReset,
}) {
    return (
        <>
            <div className="alerts-page-tabs-row">
                <div className="alerts-page-tabs">
                    {alertTabs.map((tab) => (
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

                <div className="alerts-page-top-buttons">
                    <button
                        type="button"
                        className="alerts-page-settings-button"
                        onClick={onOpenSettings}
                    >
                        <span className="material-symbols-outlined">settings</span>
                        Alert Settings
                    </button>

                    <button
                        type="button"
                        className="alerts-page-add-button"
                        onClick={onAddAlert}
                    >
                        <span className="material-symbols-outlined">add</span>
                        Add Alert
                    </button>
                </div>
            </div>

            <div className="alerts-page-filter-row">
                <div className="alerts-page-search-box">
                    <span className="material-symbols-outlined">search</span>
                    <input
                        type="text"
                        placeholder="Search alerts..."
                        value={searchText}
                        onChange={(event) => onSearchChange(event.target.value)}
                    />
                </div>

                <select
                    value={categoryFilter}
                    onChange={(event) => onCategoryChange(event.target.value)}
                >
                    <option value="All">All Categories</option>
                    {categories.map((category) => (
                        <option key={category} value={category}>
                            {category}
                        </option>
                    ))}
                </select>

                <select
                    value={statusFilter}
                    onChange={(event) => onStatusChange(event.target.value)}
                >
                    <option value="All">All Status</option>
                    <option value="Active">Active</option>
                    <option value="Disabled">Disabled</option>
                </select>

                <button
                    type="button"
                    className="alerts-page-reset-button"
                    onClick={onReset}
                >
                    <span className="material-symbols-outlined">restart_alt</span>
                    Reset
                </button>
            </div>
        </>
    );
}
