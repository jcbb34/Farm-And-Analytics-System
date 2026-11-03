import { RecordFilters, RecordSearch, RecordDateFilter } from "../../../components/Records/RecordsLayout.jsx";

// Search and filters for crop records.
function CropsToolbar({
    searchText,
    setSearchText,
    cropType,
    setCropType,
    cropTypes,
    statusFilter,
    setStatusFilter,
    fieldFilter,
    setFieldFilter,
    cropFields,
    dateFilter,
    setDateFilter,
    onClear,
}) {
    return (
        <RecordFilters className="crop-toolbar" label="Crops filters">
            <RecordSearch className="crop-search-box" label="Search crops" placeholder="Search crop, variety, or field..." value={searchText} onChange={(event) => setSearchText(event.target.value)}/>

            <select aria-label="Crop type"
                value={cropType}
                onChange={(event) => setCropType(event.target.value)}
            >
                <option value="All">All Crop Types</option>
                {cropTypes.map((type) => (
                    <option value={type} key={type}>
                        {type}
                    </option>
                ))}
            </select>

            <select aria-label="Crop status"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
            >
                <option value="Active Crops">Active Crops</option>
                <option value="Ready for Harvest">Ready for Harvest</option>
                <option value="Harvesting">Harvesting</option>
                <option value="Growing">Growing</option>
                <option value="Fully Harvested/Completed">Fully Harvested/Completed</option>
                <option value="Archived">Archived</option>
                <option value="All">All</option>
            </select>

            <select aria-label="Crop field"
                value={fieldFilter}
                onChange={(event) => setFieldFilter(event.target.value)}
            >
                <option value="All">All Fields</option>
                {cropFields.map((field) => (
                    <option value={field} key={field}>
                        {field}
                    </option>
                ))}
            </select>

            <RecordDateFilter label="Planting date" prefix="Planted" value={dateFilter} onChange={(event) => setDateFilter(event.target.value)}/>

            <button
                type="button"
                className="crop-clear-button"
                onClick={onClear}
            >
                Clear
            </button>
        </RecordFilters>
    );
}

export default CropsToolbar;
