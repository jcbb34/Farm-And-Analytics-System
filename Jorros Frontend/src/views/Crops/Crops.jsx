"use client";

import ArchiveWorkspace from "../../components/Archives/Archives.jsx";

import dynamic from "next/dynamic";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import CropsSummaryCards from "./components/CropsSummaryCards.jsx";
import CropsToolbar from "./components/CropsToolbar.jsx";
import CropsRecordsTable from "./components/CropsRecordsTable.jsx";
import useCropsPage from "./hooks/useCropsPage.js";
import CropAnalytics from "../../components/CropAnalytics/CropAnalytics.jsx";

// Load large forms only when they are opened.
const AddCropModal = dynamic(
    () =>
        import("../../components/CropModals/CropModals.jsx").then(
            (module) => module.AddCropModal
        ),
    { ssr: false }
);
const EditCropModal = dynamic(
    () =>
        import("../../components/CropModals/CropModals.jsx").then(
            (module) => module.EditCropModal
        ),
    { ssr: false }
);
const CropDetailsModal = dynamic(
    () =>
        import("../../components/CropModals/CropModals.jsx").then(
            (module) => module.CropDetailsModal
        ),
    { ssr: false }
);
const AddYieldModal = dynamic(
    () =>
        import("../../components/CropActionModals/CropActionModals.jsx").then(
            (module) => module.AddYieldModal
        ),
    { ssr: false }
);
const ReopenCropModal = dynamic(
    () => import("./components/ReopenCropModal.jsx"),
    { ssr: false }
);

import "./Crops.css";

function Crops() {
    const page = useCropsPage();

    return (
        <div className="crops-layout">
            <Sidebar />

            <main className="crops-page">
                <header className="crops-header">
                    <div className="crops-heading">
                        <h1>Crops Management</h1>
                        <p>
                            Monitor automatic crop progress, planting schedules,
                            harvest status, and field records.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <CropsSummaryCards cards={page.cropSummary} />

                <ArchiveWorkspace module="Crop" before={<>
                <section className="crop-priority-strip" aria-label="Harvest priority">
                    <button type="button" onClick={() => page.setStatusFilter("Ready for Harvest")}>
                        <span className="material-symbols-outlined" aria-hidden="true">agriculture</span>
                        Ready for Harvest ({page.readyForHarvestCount})
                    </button>
                    <small>Confirmed and estimated-ready crops are prioritized in the active list. Confirmed physical readiness is labelled separately.</small>
                </section>

                <CropsToolbar
                    searchText={page.searchText}
                    setSearchText={page.setSearchText}
                    cropType={page.cropType}
                    setCropType={page.setCropType}
                    cropTypes={page.cropTypes}
                    statusFilter={page.statusFilter}
                    setStatusFilter={page.setStatusFilter}
                    fieldFilter={page.fieldFilter}
                    setFieldFilter={page.setFieldFilter}
                    cropFields={page.cropFields}
                    dateFilter={page.dateFilter}
                    setDateFilter={page.setDateFilter}
                    onClear={page.clearFilters}
                />

                </>}>
                {(navigation) => <>
                <CropsRecordsTable
                    navigation={navigation}
                    crops={page.filteredCrops}
                    loading={page.cropsLoading}
                    error={page.cropsError}
                    canUpdateCrops={page.canUpdateCrops}
                    canFullEditCrops={page.canFullEditCrops}
                    onAddYield={() => page.setAddYieldOpen(true)}
                    onAddCrop={() => page.setAddCropOpen(true)}
                    onViewCrop={page.setSelectedCrop}
                    onEditCrop={page.setEditCrop}
                    onArchiveCrop={page.handleArchiveCrop}
                    onHarvestCrop={page.openHarvestForCrop}
                    onOpenHarvestTask={page.openPendingHarvestTask}
                    onConfirmReady={page.handleConfirmReady}
                    onReopenCrop={page.setReopenCropTarget}
                />

                <CropAnalytics
                    crops={page.crops}
                    yieldRecords={page.yieldRecords}
                />
                </>}
                </ArchiveWorkspace>
            </main>

            {page.addCropOpen && (
                <AddCropModal
                    fieldOptions={page.crops.filter((crop) => !crop.isArchived).map((crop) => crop.field)}
                    open
                    onClose={() => page.setAddCropOpen(false)}
                    onSave={page.handleAddCrop}
                />
            )}

            {page.editCrop && (
                <EditCropModal
                    fieldOptions={page.crops.filter((crop) => !crop.isArchived).map((crop) => crop.field)}
                    open
                    crop={page.editCrop}
                    onClose={() => page.setEditCrop(null)}
                    onSave={page.handleEditCrop}
                />
            )}

            {page.selectedCrop && (
                <CropDetailsModal
                    crop={page.selectedCrop}
                    onClose={() => page.setSelectedCrop(null)}
                    onSavePestDisease={page.handleSavePestDisease}
                    onUpdatePestDisease={page.handleUpdatePestDisease}
                    onSaveGrowthCheck={page.handleSaveGrowthCheck}
                    canEditResources={page.canUpdateCrops}
                />
            )}

            {page.addYieldOpen && (
                <AddYieldModal
                    open
                    crops={page.harvestEligibleCrops}
                    employees={page.employees}
                    initialCropId={page.harvestCropId}
                    onClose={() => { page.setAddYieldOpen(false); page.setHarvestCropId(null); }}
                    onSave={page.handleAddYield}
                />
            )}

            {page.reopenCropTarget && (
                <ReopenCropModal
                    crop={page.reopenCropTarget}
                    onClose={() => page.setReopenCropTarget(null)}
                    onSave={page.handleReopenCrop}
                />
            )}
        </div>
    );
}

export default Crops;
