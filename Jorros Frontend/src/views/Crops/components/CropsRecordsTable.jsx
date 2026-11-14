"use client";

import { RecordHeader, RecordTableSurface } from "../../../components/Records/RecordsLayout.jsx";


import { sectionLabelForCrop } from "./cropRecordLocation.mjs";

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
    total = crops.length,
    loadingMore = false,
    onLoadMore,
    onRetry,
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
    onInspectReadiness,
    onReopenCrop,
}) {
    return (
        <>
            <RecordHeader className="crop-action-row" title="Crop Records" navigation={navigation}
                summary={`Showing ${crops.length} of ${total} matching crop records`} actions={<>{canUpdateCrops && (
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
                                <th>Field / Section</th>
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
                                                    <small className="crop-record-code">{crop.cropCode || `Crop #${crop.id}`}</small>
                                                </div>
                                            </div>
                                        </td>

                                        <td data-label="Field">
                                            <span className="crop-mobile-label">Field / Section</span>
                                            <div className="crop-record-location">
                                                <span className="crop-record-field">{crop.field || "Field not recorded"}</span>
                                                {sectionLabelForCrop(crop) && (
                                                    <span className="crop-record-section">{sectionLabelForCrop(crop)}</span>
                                                )}
                                            </div>
                                        </td>
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
                                                            width: `${crop.estimatedProgress ?? crop.growth ?? 0}%`,
                                                        }}
                                                    />
                                                </div>

                                                <div className="crop-growth-info">
                                                    <div className="crop-growth-heading">
                                                        <strong>
                                                            {crop.observedGrowthStage ? `Observed: ${crop.observedGrowthStage}` : `${crop.readinessStatus === "Confirmed Ready" ? "Confirmed" : "Estimated"}: ${crop.growthStage || "Seeded"}`}
                                                        </strong>
                                                        <span>{crop.estimatedProgress == null && crop.growth == null ? "Not estimated" : `${crop.estimatedProgress ?? crop.growth}% estimated`}</span>
                                                    </div>
                                                </div>
                                            </div>
                                        </td>

                                        <td data-label="Surviving">
                                            <span className="crop-mobile-label">Surviving</span>
                                            <strong>{crop.currentSurviving ?? "Unknown"} / {crop.quantityPlanted ?? "Unknown"}</strong>
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
                                                {crop.lastReadinessVerdict === "not_ready" && crop.readinessStatus !== "Confirmed Ready" && (
                                                    <small className="crop-readiness-inspection-warning">
                                                        Inspected: Not yet ready{crop.lastReadinessInspectionDate ? ` (${crop.lastReadinessInspectionDate})` : ""}
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

                                                {canUpdateCrops && ["Planted", "Growing", "Ready for Harvest", "Harvesting"].includes(crop.status) && !crop.isArchived && (
                                                    <button type="button" title="Inspect harvest readiness"
                                                        aria-label={`Inspect harvest readiness for ${crop.name} ${crop.variety}, ${crop.field}, ${sectionLabelForCrop(crop) || "no section"}, ${crop.cropCode || crop.id}`}
                                                        onClick={() => onInspectReadiness?.(crop)}>
                                                        <span className="material-symbols-outlined">fact_check</span>
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
            {error && <button type="button" className="workforce-button secondary" onClick={onRetry}>Retry crops</button>}
            {!error && crops.length < total && <button type="button" className="workforce-button secondary" disabled={loading || loadingMore} onClick={onLoadMore}>{loadingMore ? "Loading…" : "Load more crops"}</button>}
        </>
    );
}

export default CropsRecordsTable;
