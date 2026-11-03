"use client";

import { RecordHeader, RecordTableSurface } from "../../../components/Records/RecordsLayout.jsx";


// Inventory records table and row actions

function formatDate(dateValue) {
    if (!dateValue) {
        return "—";
    }

    const [year, month, day] = dateValue
        .split("-")
        .map(Number);

    return new Date(
        year,
        month - 1,
        day
    ).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function formatCurrency(value) {
    return Number(value).toLocaleString("en-PH", {
        style: "currency",
        currency: "PHP",
        minimumFractionDigits: 2,
    });
}

function getStockStatus(item) {
    if (Number(item.quantity) <= 0) {
        return "Out of Stock";
    }

    if (
        Number(item.quantity) <=
        Number(item.reorderLevel)
    ) {
        return "Low Stock";
    }

    return "In Stock";
}

function getStatusClass(status) {
    return status
        .toLowerCase()
        .replaceAll(" ", "-");
}

export default function InventoryRecordsTable({
    navigation,
    inventory,
    filteredInventory,
    total,
    loadingMore,
    onLoadMore,
    loading,
    error,
    onAdd,
    onView,
    onEdit,
    onArchive,
}) {
    return (
        <>
            <RecordHeader className="inventory-page-action-row" title="Inventory Records" navigation={navigation}
                summary={`${total} inventory records found`} actions={<><button
                        type="button"
                        className="inventory-page-primary-button"
                        onClick={onAdd}
                    >
                        <span className="material-symbols-outlined">
                            add
                        </span>
                        Add Inventory
                    </button></>}/>


            <RecordTableSurface className="inventory-page-table-card" scrollClassName="inventory-page-table-wrapper" busy={loading} footer={<div className="inventory-page-table-footer records-footer">
                    <span>
                        Showing {filteredInventory.length} of {total} matching inventory records
                    </span>
                    {filteredInventory.length < total && <button
                        type="button" className="inventory-page-clear-button"
                        disabled={loading || loadingMore} onClick={onLoadMore}
                    >{loadingMore ? "Loading..." : "Load 50 more"}</button>}
                </div>}>
                    <table className="inventory-page-table">
                        <thead>
                            <tr>
                                <th>Item Code</th>
                                <th>Item Name</th>
                                <th>Quantity</th>
                                <th>Reorder Level</th>
                                <th>Cost</th>
                                <th>Price</th>
                                <th>Supplier</th>
                                <th>Date Acquired</th>
                                <th>Stock Status</th>
                                <th>Actions</th>
                            </tr>
                        </thead>

                        <tbody>
                            {loading ? (
                                <tr>
                                    <td
                                        colSpan="10"
                                        className="inventory-page-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            progress_activity
                                        </span>
                                        <p>Loading inventory records...</p>
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr>
                                    <td
                                        colSpan="10"
                                        className="inventory-page-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            error
                                        </span>
                                        <p>{error}</p>
                                    </td>
                                </tr>
                            ) : filteredInventory.length > 0 ? (
                                filteredInventory.map((item) => {
                                    const stockStatus =
                                        getStockStatus(item);

                                    return (
                                        <tr key={item.id}>
                                            <td>
                                                <strong className="inventory-page-item-code">
                                                    {item.itemCode}
                                                </strong>
                                            </td>

                                            <td>
                                                <div className="inventory-page-name-cell">
                                                    <span className="inventory-page-table-icon">
                                                        <span className="material-symbols-outlined">
                                                            inventory_2
                                                        </span>
                                                    </span>

                                                    <div>
                                                        <strong>
                                                            {item.name}
                                                        </strong>
                                                        <small>
                                                            {item.category}
                                                            {item.batchNumber
                                                                ? ` • Batch ${item.batchNumber}`
                                                                : ""}
                                                            {" • "}
                                                            {item.location}
                                                        </small>
                                                    </div>
                                                </div>
                                            </td>

                                            <td>
                                                <strong>{item.quantity}</strong>{" "}
                                                {item.unit}
                                            </td>

                                            <td>
                                                {item.reorderLevel}{" "}
                                                {item.unit}
                                            </td>

                                            <td>
                                                {formatCurrency(item.cost)}
                                            </td>

                                            <td>
                                                {formatCurrency(item.price)}
                                            </td>

                                            <td>{item.supplier}</td>

                                            <td>
                                                {formatDate(item.dateAcquired)}
                                            </td>

                                            <td>
                                                <span
                                                    className={`inventory-page-stock-status ${getStatusClass(
                                                        stockStatus
                                                    )}`}
                                                >
                                                    {stockStatus}
                                                </span>
                                            </td>

                                            <td>
                                                <div className="inventory-page-row-actions records-row-actions">
                                                    <button
                                                        type="button"
                                                        title="View inventory"
                                                        onClick={() => onView(item)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            visibility
                                                        </span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        title="Edit inventory"
                                                        onClick={() => onEdit(item)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            edit
                                                        </span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        className="archive"
                                                        title="Archive inventory"
                                                        onClick={() => onArchive(item.id)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            archive
                                                        </span>
                                                    </button>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })
                            ) : (
                                <tr>
                                    <td
                                        colSpan="10"
                                        className="inventory-page-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            search_off
                                        </span>
                                        <p>
                                            No inventory records match the selected filters.
                                        </p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>


            </RecordTableSurface>
        </>
    );
}
