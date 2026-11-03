import { RecordFilters, RecordSearch, RecordDateFilter } from "../../../components/Records/RecordsLayout.jsx";

// Search and filter controls for inventory records
function InventoryToolbar({
    searchText,
    onSearchChange,
    categoryFilter,
    onCategoryChange,
    statusFilter,
    onStatusChange,
    supplierFilter,
    onSupplierChange,
    dateFilter,
    onDateChange,
    categories,
    suppliers,
    onClear,
}) {
    return (
        <RecordFilters className="inventory-page-toolbar" label="Inventory filters">
            <RecordSearch className="inventory-page-search-box" label="Search inventory" placeholder="Search item, code, category, supplier, or location..." value={searchText} onChange={(event) => onSearchChange(event.target.value)}/>

            <select aria-label="Inventory category"
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

            <select aria-label="Stock status"
                value={statusFilter}
                onChange={(event) => onStatusChange(event.target.value)}
            >
                <option value="All">All Stock Status</option>
                <option>In Stock</option>
                <option>Low Stock</option>
                <option>Out of Stock</option>
            </select>

            <select aria-label="Supplier"
                value={supplierFilter}
                onChange={(event) => onSupplierChange(event.target.value)}
            >
                <option value="All">All Suppliers</option>

                {suppliers.map((supplier) => (
                    <option key={supplier} value={supplier}>
                        {supplier}
                    </option>
                ))}
            </select>

            <RecordDateFilter label="Date acquired" prefix="Acquired" value={dateFilter} onChange={(event) => onDateChange(event.target.value)}/>

            <button
                type="button"
                className="inventory-page-clear-button"
                onClick={onClear}
            >
                Clear
            </button>
        </RecordFilters>
    );
}

export default InventoryToolbar;
