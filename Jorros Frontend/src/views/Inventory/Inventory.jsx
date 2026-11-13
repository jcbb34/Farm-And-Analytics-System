"use client";

import ArchiveWorkspace from "../../components/Archives/Archives.jsx";

import dynamic from "next/dynamic";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import InventorySummaryCards from "./components/InventorySummaryCards.jsx";
import InventoryToolbar from "./components/InventoryToolbar.jsx";
import InventoryRecordsTable from "./components/InventoryRecordsTable.jsx";
import useInventoryPage from "./hooks/useInventoryPage.js";
import DeferredSection from "../../components/DeferredSection/DeferredSection.jsx";
const InventoryAnalytics = dynamic(() => import("../../components/InventoryAnalytics/InventoryAnalytics.jsx"), {
    ssr: false, loading: () => <p role="status">Loading inventory analytics…</p>,
});

// Load large inventory forms only when needed.
const InventoryFormModal = dynamic(
    () =>
        import("../../components/InventoryModals/InventoryModals.jsx").then(
            (module) => module.InventoryFormModal
        ),
    { ssr: false }
);
const InventoryDetailsModal = dynamic(
    () =>
        import("../../components/InventoryModals/InventoryModals.jsx").then(
            (module) => module.InventoryDetailsModal
        ),
    { ssr: false }
);

import "./Inventory.css";

function Inventory() {
    const page = useInventoryPage();

    return (
        <div className="inventory-page-layout">
            <Sidebar />

            <main className="inventory-page-content">
                <header className="inventory-page-header">
                    <div className="inventory-page-heading">
                        <h1>Inventory Management</h1>
                        <p>
                            Monitor farm supplies, equipment, stock levels,
                            suppliers, and acquired inventory records.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <InventorySummaryCards cards={page.inventorySummary} />
                {(page.summaryError || page.movementError) && <div className="workforce-error" role="alert">
                    <strong>Inventory analytics unavailable.</strong> {page.summaryError || page.movementError}{" "}
                    <button type="button" className="workforce-button secondary compact" onClick={page.loadSummary} disabled={page.summaryLoading}>Retry totals</button>
                </div>}

                <ArchiveWorkspace module="Inventory" before={<>
                <InventoryToolbar
                    searchText={page.searchText}
                    onSearchChange={page.setSearchText}
                    categoryFilter={page.categoryFilter}
                    onCategoryChange={page.setCategoryFilter}
                    statusFilter={page.statusFilter}
                    onStatusChange={page.setStatusFilter}
                    supplierFilter={page.supplierFilter}
                    onSupplierChange={page.setSupplierFilter}
                    dateFilter={page.dateFilter}
                    onDateChange={page.setDateFilter}
                    categories={page.inventoryCategories}
                    suppliers={page.inventorySuppliers}
                    onClear={page.clearFilters}
                />

                </>}>
                {(navigation) => <>
                <InventoryRecordsTable
                    navigation={navigation}
                    inventory={page.inventory}
                    filteredInventory={page.filteredInventory}
                    total={page.inventoryTotal}
                    loadingMore={page.loadingMore}
                    onLoadMore={page.loadMoreInventory}
                    loading={page.inventoryLoading}
                    error={page.inventoryError}
                    onAdd={page.openAddInventory}
                    onView={page.openViewInventory}
                    onEdit={page.openEditInventory}
                    onArchive={page.archiveInventoryItem}
                />

                {page.summaryLoading ? <p role="status">Loading inventory analytics…</p> : !page.summaryError && !page.movementError && <DeferredSection label="inventory analytics"><InventoryAnalytics inventory={page.inventory} movementSummary={page.movementSummary} summary={page.inventorySummaryData} /></DeferredSection>}
                </>}
                </ArchiveWorkspace>
            </main>

            {page.inventoryFormOpen && (
                <InventoryFormModal
                    storageOptions={page.inventory.filter((item) => !item.isArchived).map((item) => item.location)}
                    open
                    item={page.editingItem}
                    onClose={page.closeInventoryForm}
                    onSave={page.handleSaveInventory}
                />
            )}

            {page.selectedItem && (
                <InventoryDetailsModal
                    item={page.selectedItem}
                    onClose={() => page.setSelectedItem(null)}
                    onAdjustStock={page.handleAdjustStock}
                />
            )}
        </div>
    );
}

export default Inventory;
