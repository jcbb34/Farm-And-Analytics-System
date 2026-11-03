"use client";

import { RecordHeader, RecordTableSurface } from "../../../components/Records/RecordsLayout.jsx";


import { MonitoringStatus } from "../../../components/Monitoring/Monitoring.jsx";

import "../../../components/Monitoring/Monitoring.css";

// Crop records table and row actions.
function formatDate(dateValue) {
    if (!dateValue) {
        return "—";
    }

    const [year, month, day] =
        dateValue.split("-").map(Number);

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

function getGrowthClass(growth) {
    if (growth >= 80) {
        return "high";
    }

    if (growth >= 40) {
        return "medium";
    }

    return "low";
}

function getStatusClass(status = "") {
    return status
        .toLowerCase()
        .replaceAll(" ", "-");
}

function CropsRecordsTable({
    navigation,
    crops,
    loading,
    error,
    canUpdateCrops,
    canFullEditCrops,
    onAddYield,
    onAddCrop,
    onViewCrop,
    onEditCrop,
    onArchiveCrop,
    onHarvestCrop,
    onOpenHarvestTask,
    onConfirmReady,
    onReopenCrop,
}) {
    return (
        <>
            <RecordHeader className="crop-action-row" title="Crop Records" navigation={navigation}
                summary={`${crops.length} crop records found`} actions={<>{canUpdateCrops && (
                        <button
                            type="button"
                            className="crop-secondary-button"
                            onClick={onAddYield}
                        >
                            <span className="material-symbols-outlined">
                                add_chart
                            </span>
                            Add Yield Record
                        </button>
                    )}

                    {canUpdateCrops && (
                        <button
                            type="button"
                            className="crop-primary-button"
                            onClick={onAddCrop}
                        >
                            <span className="material-symbols-outlined">
                                add
                            </span>
                            Add Crop
                        </button>
                    )}</>}/>


            <RecordTableSurface className="crop-table-card" scrollClassName="crop-table-wrapper" busy={loading}>
                    <table className="crop-table">
                        <colgroup>
                            {[16, 8, 6, 18, 9, 16, 8, 8, 11].map((width, index) => <col key={index} style={{ width: `${width}%` }} />)}
                        </colgroup>

                        <thead>
                            <tr>
                                <th>Crop Name</th>
                                <th>Field</th>
                                <th>Area</th>
                                <th>Growth</th>
                                <th>Surviving</th>
                                <th>Status</th>
                                <th>Planting Date</th>
                                <th>Last Update</th>
                                <th className="crop-actions-header">Actions</th>
                            </tr>
                        </thead>

                        <tbody>
                            {loading ? (
                                <tr className="crop-placeholder-row">
                                    <td
                                        colSpan="9"
                                        className="crop-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            progress_activity
                                        </span>
                                        <p>Loading crop records...</p>
                                    </td>
                                </tr>
                            ) : error ? (
                                <tr className="crop-placeholder-row">
                                    <td
                                        colSpan="9"
                                        className="crop-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            error
                                        </span>
                                        <p>{error}</p>
                                    </td>
                                </tr>
                            ) : crops.length > 0 ? (
                                crops.map((crop) => (
                                    <tr key={crop.id} className={crop.status === "Ready for Harvest" ? "crop-ready-row" : ""}>
                                        <td data-label="Crop Name">
                                            <span className="crop-mobile-label">Crop Name</span>
                                            <div className="crop-name-cell">
                                                <span className="crop-table-icon">
                                                    <span className="material-symbols-outlined">
                                                        eco
                                                    </span>
                                                </span>

                                                <div>
                                                    <strong>{crop.name}</strong>
                                                    <small>{crop.variety}</small>
                                                </div>
                                            </div>
                                        </td>

                                        <td data-label="Field"><span className="crop-mobile-label">Field</span>{crop.field}</td>
                                        <td data-label="Area"><span className="crop-mobile-label">Area</span>{crop.area} ha</td>

                                        <td data-label="Growth">
                                            <span className="crop-mobile-label">Growth</span>
                                            <div className="crop-growth-cell">
                                                <div className="crop-progress-track">
                                                    <span
                                                        className={`crop-progress-bar ${getGrowthClass(
                                                            (crop.estimatedProgress ?? crop.growth)
                                                        )}`}
                                                        style={{
                                                            width: `${crop.estimatedProgress ?? crop.growth}%`,
                                                        }}
                                                    />
                                                </div>

                                                <div className="crop-growth-info">
                                                    <div className="crop-growth-heading">
                                                        <strong>
                                                            {crop.observedGrowthStage ? `Observed: ${crop.observedGrowthStage}` : `${crop.readinessStatus === "Confirmed Ready" ? "Confirmed" : "Estimated"}: ${crop.growthStage || "Seeded"}`}
                                                        </strong>
                                                        <span>{crop.estimatedProgress ?? crop.growth}% estimated</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </td>

                                        <td data-label="Surviving">
                                            <span className="crop-mobile-label">Surviving</span>
                                            <strong>{crop.currentSurviving ?? 0} / {crop.quantityPlanted ?? 0}</strong>
                                            {crop.survivalCountDate && <small className="monitoring-estimate-label">As of {formatDate(crop.survivalCountDate)}</small>}
                                        </td>

                                        <td data-label="Status">
                                            <span className="crop-mobile-label">Status</span>
                                            <div className="crop-status-stack">
                                                <span
                                                    className={`crop-table-status ${getStatusClass(
                                                        crop.status
                                                    )}`}
                                                >
                                                    {crop.status === "Harvested" ? "Fully Harvested" : crop.status}
                                                </span>
                                                {["Ready for Harvest", "Harvesting"].includes(crop.status) && (
                                                    <small className={`crop-readiness-label ${crop.readinessStatus === "Confirmed Ready" ? "confirmed" : "estimated"}`}>
                                                        {crop.readinessStatus || "Estimated Ready"}
                                                    </small>
                                                )}
                                                <MonitoringStatus summary={crop.monitoringSummary} />
                                                {crop.pendingHarvestMessage && (
                                                    <small className="crop-harvest-waiting-label">
                                                        {crop.pendingHarvestMessage}
                                                        {crop.pendingHarvestTaskCode ? ` · ${crop.pendingHarvestTaskCode}` : ""}
                                                    </small>
                                                )}
                                            </div>
                                        </td>

                                        <td data-label="Planting Date"><span className="crop-mobile-label">Planting Date</span>{formatDate(crop.plantingDate)}</td>
                                        <td data-label="Last Update"><span className="crop-mobile-label">Last Update</span>{formatDate(crop.lastUpdate)}</td>

                                        <td data-label="Actions" className="crop-actions-cell">
                                            <span className="crop-mobile-label">Actions</span>
                                            <div className="crop-row-actions records-row-actions">
                                                <button
                                                    type="button"
                                                    title="View crop"
                                                    onClick={() => onViewCrop(crop)}
                                                >
                                                    <span className="material-symbols-outlined">
                                                        visibility
                                                    </span>
                                                </button>

                                                {canUpdateCrops && crop.pendingHarvestTaskId && !crop.isArchived ? (
                                                    <button
                                                        type="button"
                                                        title={crop.pendingHarvestMessage || "Open harvest task"}
                                                        aria-label={`Open harvest task ${crop.pendingHarvestTaskCode || ""} for ${crop.name}`}
                                                        onClick={() => onOpenHarvestTask?.(crop)}
                                                    >
                                                        <span className="material-symbols-outlined">assignment</span>
                                                    </button>
                                                ) : canUpdateCrops && ["Ready for Harvest", "Harvesting"].includes(crop.status) && !crop.isArchived && (
                                                    <button
                                                        type="button"
                                                        title="Record harvest"
                                                        aria-label={`Record harvest for ${crop.name}`}
                                                        onClick={() => onHarvestCrop?.(crop)}
                                                    >
                                                        <span className="material-symbols-outlined">agriculture</span>
                                                    </button>
                                                )}

                                                {canUpdateCrops && crop.status === "Ready for Harvest" && crop.readinessStatus !== "Confirmed Ready" && !crop.isArchived && (
                                                    <button
                                                        type="button"
                                                        title="Confirm physical harvest readiness"
                                                        aria-label={`Confirm ${crop.name} is physically ready for harvest`}
                                                        onClick={() => onConfirmReady?.(crop)}
                                                    >
                                                        <span className="material-symbols-outlined">verified</span>
                                                    </button>
                                                )}

                                                {canFullEditCrops && crop.status === "Harvested" && !crop.isArchived && (
                                                    <button
                                                        type="button"
                                                        title="Reopen crop cycle"
                                                        aria-label={`Reopen crop cycle for ${crop.name}`}
                                                        onClick={() => onReopenCrop?.(crop)}
                                                    >
                                                        <span className="material-symbols-outlined">restart_alt</span>
                                                    </button>
                                                )}

                                                {canFullEditCrops && (
                                                    <button
                                                        type="button"
                                                        title="Edit crop information"
                                                        data-permission="crops:full-edit"
                                                        onClick={() => onEditCrop(crop)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            edit
                                                        </span>
                                                    </button>
                                                )}

                                                {canUpdateCrops && (
                                                    <button
                                                        type="button"
                                                        className="delete"
                                                        title="Archive crop"
                                                        onClick={() => onArchiveCrop(crop.id)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            archive
                                                        </span>
                                                    </button>
                                                )}
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr className="crop-placeholder-row">
                                    <td
                                        colSpan="9"
                                        className="crop-empty-table"
                                    >
                                        <span className="material-symbols-outlined">
                                            search_off
                                        </span>
                                        <p>
                                            No crop records match the selected filters.
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

export default CropsRecordsTable;
