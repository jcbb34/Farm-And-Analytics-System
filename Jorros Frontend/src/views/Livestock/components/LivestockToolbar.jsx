"use client";

// Search and filters for livestock records
export default function LivestockToolbar({
    searchText,
    setSearchText,
    typeFilter,
    setTypeFilter,
    statusFilter,
    setStatusFilter,
    penFilter,
    setPenFilter,
    livestockTypes = [],
    healthStatuses = [],
    penLocations = [],
    onClear,
}) {
    return (
        <section className="livestock-toolbar">
            <div className="livestock-search-box">
                <span className="material-symbols-outlined">search</span>

                <input
                    type="text"
                    placeholder="Search livestock, ID, breed, or pen..."
                    value={searchText}
                    onChange={(event) => setSearchText(event.target.value)}
                />
            </div>

            <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
            >
                <option value="All">All Types</option>
                {livestockTypes.map((type) => (
                    <option key={type} value={type}>
                        {type}
                    </option>
                ))}
            </select>

            <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
            >
                <option value="All">All Health Status</option>
                {healthStatuses.map((status) => (
                    <option key={status} value={status}>
                        {status}
                    </option>
                ))}
            </select>

            <select
                value={penFilter}
                onChange={(event) => setPenFilter(event.target.value)}
            >
                <option value="All">All Pens</option>
                {penLocations.map((pen) => (
                    <option key={pen} value={pen}>
                        {pen}
                    </option>
                ))}
            </select>

            <button
                type="button"
                className="livestock-clear-button"
                onClick={onClear}
            >
                Clear
            </button>
        </section>
    );
}
