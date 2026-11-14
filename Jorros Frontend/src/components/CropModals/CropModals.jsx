"use client";
import PlantingPositions from "../CropPlanning/PlantingPositions.jsx";
import CropPlanningFields, { emptyDirectSchedules } from "../CropPlanning/CropPlanningFields.jsx";
import { planningPayload, parseSnapshot, cropPlanningService, farmTodayDateKey, validScheduleStartDate } from "../../services/cropPlanningService.js";
import useRecordEditConflict from "../../hooks/useRecordEditConflict.js";
import RecordConflictNotice from "../RecordConflictNotice/RecordConflictNotice.jsx";
import { cropService } from "../../services/cropService.js";


import { HistoryDateRange, useHistoryRange } from "../Monitoring/Monitoring.jsx";
import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useRef,
    useState,
} from "react";

import ResourceUsagePanel from "../ResourceUsagePanel/ResourceUsagePanel.jsx";
import { workforceService } from "../../services/workforceService.js";

import "./CropModals.css";

const emptyCropForm = {
    registration_kind: "new", crop_reference: null, variety_reference: null, field_id: "", section_id: null,
    spacing_profile_id: null, planting_date_precision: "known", initial_status: "Growing", confirm_ready: false,
    care_schedules: emptyDirectSchedules(),
    name: "",
    variety: "",
    field: "",
    area: "",
    plantingDate: "",
    estimatedHarvest: "",
    quantityPlanted: "",
    currentSurviving: "",
    notes: "",
    assignedEmployeeId: "",
};

const initialPestForm = {
    id: null,
    dateDetected: "",
    type: "",
    severity: "Low",
    affectedArea: "",
    notes: "",
    status: "Active",
};

function getTodayDateKey() {
    const today = new Date();
    const year = today.getFullYear();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
}

function formatDate(dateValue) {
    if (!dateValue) {
        return "Not specified";
    }

    const [year, month, day] =
        dateValue.split("-").map(Number);

    return new Date(
        year,
        month - 1,
        day
    ).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
    });
}

function getStatusClass(status) {
    return String(status || "")
        .toLowerCase()
        .replaceAll(" ", "-");
}

function cropToForm(crop) {
    if (!crop) {
        return emptyCropForm;
    }

    return {
        ...emptyCropForm,
        ...planningPayload(crop),
        registration_kind: crop.registration_kind || "legacy",
        care_schedules: (() => { const saved = parseSnapshot(crop.care_schedules_json) || []; return emptyDirectSchedules().map(item => saved.find(x => x.activity === item.activity) || item); })(),
        initial_status: ["Growing", "Ready for Harvest", "Harvesting"].includes(crop.status) ? crop.status : "Growing",
        spacing_profile_id: null,
        editVersion: crop.editVersion,
        name: crop.name ?? "",
        variety: crop.variety ?? "",
        field: crop.field ?? "",
        area:
            crop.area === null ||
            crop.area === undefined
                ? ""
                : String(crop.area),
        plantingDate:
            crop.plantingDate ?? "",
        estimatedHarvest:
            crop.estimatedHarvest ?? "",
        quantityPlanted:
            crop.quantityPlanted === null ||
            crop.quantityPlanted === undefined
                ? ""
                : String(crop.quantityPlanted),
        currentSurviving:
            crop.currentSurviving === null ||
            crop.currentSurviving === undefined
                ? ""
                : String(crop.currentSurviving),
        notes:
            crop.notes ===
            "No additional notes."
                ? ""
                : crop.notes ?? "",
        assignedEmployeeId: crop.assignedEmployeeId == null ? "" : String(crop.assignedEmployeeId),
    };
}

function CropRecordFormModal({
    open,
    crop = null,
    fieldOptions = [],
    mode = "add",
    onClose,
    onSave,
}) {
    const submittingRef = useRef(false);
    const [saving, setSaving] = useState(false);
    const editing = mode === "edit";
    const [form, setForm] = useState(
        emptyCropForm
    );
    const [employees, setEmployees] = useState([]);
    const [planningPreview, setPlanningPreview] = useState(null);

    const conflict = useRecordEditConflict({
        open, id: crop?.id, loadRecord: cropService.getCrop,
        replaceForm: latest => setForm(cropToForm(latest)),
    });

    useEffect(() => {
        if (open) {
            submittingRef.current = false;
            setSaving(false);
            setPlanningPreview(null);
            setForm(
                editing
                    ? cropToForm(crop)
                    : { ...emptyCropForm, plantingDate: farmTodayDateKey() }
            );
            workforceService.getEmployees().then((employeeRows) => {
                setEmployees(employeeRows || []);
            }).catch((error) => {
                console.warn("Unable to load crop workforce choices:", error);
                setEmployees([]);
            });
            document.body.style.overflow =
                "hidden";
        }

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, crop, editing]);

    if (!open) {
        return null;
    }

    const closeForm = () => { if (!submittingRef.current) onClose(); };

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (conflict.reloading) return;
        if (submittingRef.current) return;

        if (!form.name.trim() || !form.variety.trim() || !form.field.trim() || !(Number(form.area) > 0)) {
            notify("Choose the crop, variety and measured location, and enter its allocated area."); return;
        }
        const today = farmTodayDateKey();
        if (form.registration_kind === 'new' && form.plantingDate && form.plantingDate < today
            && !(editing && form.plantingDate === crop?.plantingDate)) {
            notify('A new planting must be dated today or later. Existing crops can keep their actual historical dates.'); return;
        }
        const savedSchedules = parseSnapshot(crop?.care_schedules_json) || [];
        const invalidStart = (form.care_schedules || []).find(schedule => schedule.enabled && !validScheduleStartDate(
            schedule.start_date,
            savedSchedules.find(old => old.activity === schedule.activity)?.start_date || '', today,
        ));
        if (invalidStart) {
            notify(`${invalidStart.activity === 'watering' ? 'Watering' : 'Growth Observation'} cannot start before today.`); return;
        }
        if (form.plantingDate && form.estimatedHarvest && form.estimatedHarvest < form.plantingDate) {
            notify("Expected harvest cannot precede the planting date."); return;
        }
        const quantityPlanted = form.quantityPlanted === "" ? null : Number(form.quantityPlanted);
        const currentSurviving = form.currentSurviving === "" ? null : Number(form.currentSurviving);
        if ([quantityPlanted, currentSurviving].some(x => x !== null && (!Number.isInteger(x) || x < 0))) {
            notify("Actual plant counts must be whole, nonnegative numbers; leave unknown counts blank."); return;
        }
        const schedules = (form.care_schedules || []).filter(x => x.enabled);
        submittingRef.current = true; setSaving(true);
        try {
            const preview = await cropPlanningService.preview({ care_schedules: schedules,
                assigned_employee_id: form.assignedEmployeeId ? Number(form.assignedEmployeeId) : null,
                crop_id: crop?.id, effective_date: form.schedule_effective_date || null });
            setPlanningPreview(preview);
            if (preview.conflicts) { submittingRef.current = false; setSaving(false); notify("Resolve the conflicts shown in Upcoming Activities before saving."); return; }
        } catch (error) { submittingRef.current = false; setSaving(false); notify(error.message || "Unable to check the care schedules. Your entries are kept."); return; }
        const payload = {
            ...planningPayload(form),
            care_schedules: schedules,
            editVersion: form.editVersion,
            name: form.name.trim(), variety: form.variety.trim(), field: form.field.trim(), area: form.area,
            plantingDate: form.plantingDate || null, estimatedHarvest: form.estimatedHarvest || null,
            quantityPlanted, currentSurviving,
            notes: form.notes.trim() || null,
            assignedEmployeeId: form.assignedEmployeeId ? Number(form.assignedEmployeeId) : null,
        };
        if (editing && ["Harvested", "Failed"].includes(crop.status)) delete payload.initial_status;

        submittingRef.current = true;
        setSaving(true);
        try {
            await onSave(payload);
        } catch (error) {
            if (conflict.handleError(error)) return;
            if (error?.response?.detail?.preview) setPlanningPreview(error.response.detail.preview);
            notify(error?.message || "Unable to save crop. Your entries are kept for retry.");
        } finally {
            submittingRef.current = false;
            setSaving(false);
        }
    };

    return (
        <div
            className="crop-modal-overlay"
            onMouseDown={closeForm}
        >
            <div
                className="add-crop-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="crop-form-dialog-title"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="crop-modal-header">
                    <div>
                        <h2 id="crop-form-dialog-title">
                            {editing
                                ? "Edit Crop"
                                : "Add Crop"}
                        </h2>

                        <p>
                            {editing
                                ? "Update crop information and surviving plants. Schedule estimates remain separate from approved observations."
                                : "Register a new or existing physical planting, its usable area, actual counts and care schedules."}
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={closeForm}
                        disabled={saving}
                        aria-label={
                            editing
                                ? "Close edit crop form"
                                : "Close add crop form"
                        }
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="add-crop-form"
                    aria-busy={saving}
                    onSubmit={handleSubmit}
                >
                    <div className="add-crop-form-body">
                        <RecordConflictNotice conflict={conflict} disabled={saving} />
                        <fieldset className="crop-form-fields" disabled={saving}>
                            <CropPlanningFields form={form} setForm={setForm} crop={crop} employees={employees}
                                preview={planningPreview} setPreview={setPlanningPreview} editing={editing} />
                        </fieldset>
                    </div>
                    <footer className="crop-form-footer">
                        <button
                            type="button"
                            className="crop-modal-cancel"
                            onClick={closeForm}
                            disabled={saving}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="crop-modal-save"
                            disabled={saving}
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            {saving ? "Saving Crop..." : editing
                                ? "Save Changes"
                                : "Save Crop"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}

export function AddCropModal(props) {
    return (
        <CropRecordFormModal
            {...props}
            mode="add"
        />
    );
}

export function EditCropModal(props) {
    return (
        <CropRecordFormModal
            {...props}
            mode="edit"
        />
    );
}

export function CropDetailsModal({
    crop,
    onClose,
    onPlantingChanged,
    onSavePestDisease,
    onUpdatePestDisease,
    onSaveGrowthCheck,
    canEditResources = true,
}) {
    const growthHistory = useHistoryRange(crop?.growthRecords, "updateDate");
    const [showPestForm, setShowPestForm] =
        useState(false);

    const [pestForm, setPestForm] =
        useState(initialPestForm);

    const [showGrowthForm, setShowGrowthForm] = useState(false);
    const [growthForm, setGrowthForm] = useState({
        updateDate: getTodayDateKey(),
        currentSurviving: "",
        observation: "",
        notes: "",
    });

    useEffect(() => {
        if (!crop) {
            return;
        }

        document.body.style.overflow =
            "hidden";

        setPestForm(
            crop.activePestDisease || initialPestForm
        );

        setShowPestForm(false);
        setShowGrowthForm(false);
        setGrowthForm({
            updateDate: getTodayDateKey(),
            currentSurviving: String(crop.currentSurviving ?? ""),
            observation: "",
            notes: "",
        });

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [crop]);

    if (!crop) {
        return null;
    }

    const yieldCycle = (() => {
        const records = Array.isArray(crop.yieldRecords) ? crop.yieldRecords : [];
        const totalKg = records.reduce(
            (sum, record) => sum + Number(record.quantityKg || 0),
            0
        );
        const area = Number(crop.area || 0);
        const latest = [...records].sort((a, b) =>
            String(b.harvestDate || "").localeCompare(String(a.harvestDate || ""))
        )[0];
        return {
            records,
            count: records.length,
            totalKg: Math.round(totalKg * 100) / 100,
            yieldPerHectare: area > 0 ? Math.round((totalKg / area) * 100) / 100 : null,
            latest,
        };
    })();

    const handleGrowthChange = (event) => {
        const { name, value } = event.target;
        setGrowthForm((currentForm) => ({ ...currentForm, [name]: value }));
    };

    const handleGrowthSubmit = (event) => {
        event.preventDefault();
        const surviving = Number(growthForm.currentSurviving);
        if (!growthForm.updateDate || !Number.isInteger(surviving) || surviving < 0) {
            notify("Enter a valid growth check date and surviving plant count.");
            return;
        }
        if (crop.registration_kind === "legacy" && crop.quantityPlanted != null && surviving > Number(crop.quantityPlanted)) {
            notify("Current surviving plants cannot exceed quantity planted.");
            return;
        }
        if (growthForm.updateDate < crop.plantingDate || growthForm.updateDate > getTodayDateKey()) {
            notify("Growth check date must be between the planting date and today.");
            return;
        }
        const combinedNotes = [
            growthForm.observation.trim() ? `Observation: ${growthForm.observation.trim()}` : "",
            growthForm.notes.trim() ? `Notes: ${growthForm.notes.trim()}` : "",
        ].filter(Boolean).join("\n");

        onSaveGrowthCheck?.(crop.id, {
            updateDate: growthForm.updateDate,
            currentSurviving: surviving,
            observedStage: growthForm.observedStage || null,
            notes: combinedNotes || "Routine crop growth check.",
        });
        setShowGrowthForm(false);
    };

    const handlePestChange = (event) => {
        const { name, value } =
            event.target;

        setPestForm((currentForm) => ({
            ...currentForm,
            [name]: value,
        }));
    };

    const handlePestSubmit = (event) => {
        event.preventDefault();

        if (
            !pestForm.dateDetected ||
            !pestForm.type.trim() ||
            !pestForm.affectedArea.trim()
        ) {
            notify(
                "Please complete the required pest or disease fields."
            );
            return;
        }

        const payload = {
            dateDetected: pestForm.dateDetected,
            type: pestForm.type.trim(),
            severity: pestForm.severity,
            affectedArea: pestForm.affectedArea.trim(),
            notes: pestForm.notes.trim() || "No additional notes.",
            status: pestForm.status || "Active",
        };

        if (pestForm.id) {
            onUpdatePestDisease?.(crop.id, pestForm.id, payload);
        } else {
            onSavePestDisease(crop.id, payload);
        }
        setShowPestForm(false);
    };

    return (
        <div
            className="crop-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="crop-details-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="crop-details-header">
                    <div className="crop-details-title">
                        <span className="crop-details-main-icon">
                            <span className="material-symbols-outlined">
                                eco
                            </span>
                        </span>

                        <div>
                            <h2>
                                {crop.name}
                            </h2>

                            <p>
                                {crop.variety} •{" "}
                                {crop.field}
                            </p>
                        </div>
                    </div>

                    <div className="crop-details-header-actions">
                        <span
                           className={`crop-table-status ${getStatusClass(
    crop.status
)}`}
                        >
                            {crop.status}
                        </span>

                        <button
                            type="button"
                            onClick={onClose}
                            aria-label="Close crop details"
                        >
                            <span className="material-symbols-outlined">
                                close
                            </span>
                        </button>
                    </div>
                </header>

                <div className="crop-details-body">
                    <section className="crop-overview-grid">
                        <div className="crop-overview-card">
                            <span className="material-symbols-outlined">
                                landscape
                            </span>

                            <div>
                                <small>
                                    Area
                                </small>

                                <strong>
                                    {crop.area} ha
                                </strong>
                            </div>
                        </div>

                        <div className="crop-overview-card">
                            <span className="material-symbols-outlined">
                                location_on
                            </span>

                            <div>
                                <small>
                                    Field
                                </small>

                                <strong>
                                    {crop.field}
                                </strong>
                            </div>
                        </div>

                        <div className="crop-overview-card">
                            <span className="material-symbols-outlined">
                                calendar_today
                            </span>

                            <div>
                                <small>
                                    Planted
                                </small>

                                <strong>
                                    {formatDate(
                                        crop.plantingDate
                                    )}
                                </strong>
                            </div>
                        </div>

                        <div className="crop-overview-card">
                            <span className="material-symbols-outlined">
                                event_available
                            </span>

                            <div>
                                <small>
                                    Expected First Harvest
                                </small>

                                <strong>
                                    {formatDate(
                                        crop.estimatedHarvest
                                    )}
                                </strong>
                            </div>
                        </div>
                    </section>


                    <section className="crop-details-section crop-yield-cycle-section">
                        <div className="crop-details-section-heading">
                            <div>
                                <h3>Yield Cycle Summary</h3>
                                <p>Combined partial and final harvest records for this planting cycle.</p>
                            </div>
                        </div>

                        <div className="crop-care-grid crop-yield-summary-grid">
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">scale</span>
                                <div>
                                    <small>Total Yield</small>
                                    <strong>{yieldCycle.totalKg} kg</strong>
                                </div>
                            </div>
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">agriculture</span>
                                <div>
                                    <small>Harvest Records</small>
                                    <strong>{yieldCycle.count}</strong>
                                </div>
                            </div>
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">monitoring</span>
                                <div>
                                    <small>Yield per Hectare</small>
                                    <strong>
                                        {yieldCycle.yieldPerHectare === null
                                            ? "—"
                                            : `${yieldCycle.yieldPerHectare} kg/ha`}
                                    </strong>
                                </div>
                            </div>
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">event_available</span>
                                <div>
                                    <small>Latest Harvest</small>
                                    <strong>
                                        {yieldCycle.latest
                                            ? formatDate(yieldCycle.latest.harvestDate)
                                            : "No harvest yet"}
                                    </strong>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section className="crop-details-section">
                        <div className="crop-details-section-heading">
                            <div>
                                <h3>
                                    Field Growth Overview
                                </h3>

                                <p>
                                    Automatically calculated from planting to the expected first harvest date.
                                </p>
                            </div>

                            <strong className="crop-growth-number">
                                {crop.estimatedProgress == null ? "Not estimated" : `${crop.estimatedProgress}%`}
                            </strong>
                        </div>

                        <div className="crop-care-grid">
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">eco</span>
                                <div>
                                    <small>Growth Stage</small>
                                    <strong>{crop.growthStage || "Seeded"}</strong>
                                </div>
                            </div>
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">grass</span>
                                <div>
                                    <small>Plant Survival</small>
                                    <strong>
                                        {crop.currentSurviving ?? "Unknown"} / {crop.quantityPlanted ?? "Unknown"}
                                    </strong>
                                    <p>
                                        {crop.survivalRate === null || crop.survivalRate === undefined
                                            ? "No planted quantity recorded"
                                            : `${crop.survivalRate}% survival rate`}
                                    </p>
                                </div>
                            </div>
                        </div>

                        <div className="crop-details-progress">
                            <span
                                style={{
                                    width: `${crop.estimatedProgress == null ? "Not estimated" : `${crop.estimatedProgress}%`}`,
                                }}
                            />
                        </div>

                        <div className="crop-growth-labels">
                            <span>
                                Planted
                            </span>

                            <span>
                                Growing
                            </span>

                            <span>
                                Harvest
                            </span>
                        </div>
                    </section>

                    <div className="monitoring-summary"><div><dt>Estimated schedule progress</dt><dd>{crop.estimatedProgress == null ? "Not estimated" : `${crop.estimatedProgress}%`}</dd></div><div><dt>Latest approved observed stage</dt><dd>{crop.observedGrowthStage || (crop.readinessStatus === "Confirmed Ready" ? "Harvest Ready (confirmed)" : "Not recorded")}</dd></div><div><dt>Last inspection</dt><dd>{crop.monitoringSummary?.last_date || crop.lastObservationDate || "Not recorded"}</dd></div></div>
                    <section className="crop-details-section crop-growth-check-section">
                        <div className="crop-details-section-heading">
                            <div>
                                <h3>Growth Check</h3>
                                <p>Review dated inspections and approved monitoring. Historical entries preserve newer current counts.</p>
                            </div>
                            {canEditResources && !["Harvested", "Failed"].includes(crop.status) && (
                                <button
                                    type="button"
                                    className="pest-edit-button"
                                    onClick={() => setShowGrowthForm((value) => !value)}
                                >
                                    <span className="material-symbols-outlined">fact_check</span>
                                    Record Growth Check
                                </button>
                            )}
                        </div>

                        <HistoryDateRange range={growthHistory.range} onChange={growthHistory.setRange} count={growthHistory.filtered.length} />
                        {crop.growthRecords?.length > 0 && (
                            <div className="crop-growth-history-list">
                                {[...growthHistory.filtered]
                                    .sort((a, b) => String(b.updateDate || "").localeCompare(String(a.updateDate || "")))
                                    .map((record) => (
                                        <div key={record.id} className="crop-growth-history-item">
                                            <div>
                                                <strong>{formatDate(record.updateDate)}</strong>
                                                <small>{record.currentSurviving ?? crop.currentSurviving} surviving • {record.observedStage ? `Approved stage: ${record.observedStage}` : `Estimated stage: ${record.growthStage}`}</small>
                                            </div>
                                            <span>{record.growth == null ? "Not estimated" : `${record.growth}% estimated`}{record.relatedTaskId && <a href={`/task-management?taskId=${record.relatedTaskId}&tab=tasks`}> View approved work</a>}</span>
                                        </div>
                                    ))}
                            </div>
                        )}

                        {showGrowthForm && (
                            <form className="pest-record-form" onSubmit={handleGrowthSubmit}>
                                <div className="pest-form-grid">
                                    <div className="crop-form-group">
                                        <label htmlFor="growthCheckDate">Check Date <span>*</span></label>
                                        <input
                                            id="growthCheckDate"
                                            name="updateDate"
                                            type="date"
                                            min={crop.plantingDate}
                                            max={getTodayDateKey()}
                                            value={growthForm.updateDate}
                                            onChange={handleGrowthChange}
                                            required
                                        />
                                    </div>
                                    <div className="crop-form-group"><label htmlFor="direct-observed-stage">Observed stage (optional)</label><select id="direct-observed-stage" name="observedStage" value={growthForm.observedStage || ""} onChange={handleGrowthChange}><option value="">Record counts only</option>{["Seeded", "Germination", "Seedling", "Vegetative", "Flowering", "Fruiting", "Maturity"].map((stage) => <option key={stage}>{stage}</option>)}</select></div>
                                    <div className="crop-form-group">
                                        <label htmlFor="growthSurviving">Current Surviving <span>*</span></label>
                                        <input
                                            id="growthSurviving"
                                            name="currentSurviving"
                                            type="number"
                                            min="0"
                                            max={undefined}
                                            step="1"
                                            value={growthForm.currentSurviving}
                                            onChange={handleGrowthChange}
                                            required
                                        />
                                    </div>
                                </div>
                                <div className="crop-form-group">
                                    <label htmlFor="growthObservation">Observation</label>
                                    <input
                                        id="growthObservation"
                                        name="observation"
                                        type="text"
                                        placeholder="Example: Healthy vegetative growth"
                                        value={growthForm.observation}
                                        onChange={handleGrowthChange}
                                    />
                                </div>
                                <div className="crop-form-group">
                                    <label htmlFor="growthNotes">Notes</label>
                                    <textarea
                                        id="growthNotes"
                                        name="notes"
                                        rows="3"
                                        placeholder="Optional field notes..."
                                        value={growthForm.notes}
                                        onChange={handleGrowthChange}
                                    />
                                </div>
                                <div className="pest-form-buttons">
                                    <button type="button" onClick={() => setShowGrowthForm(false)}>Cancel</button>
                                    <button type="submit">Save Growth Check</button>
                                </div>
                            </form>
                        )}
                    </section>

                    <section className="crop-details-section">
                        <div className="crop-details-section-heading">
                            <div>
                                <h3>
                                    Crop Care Details
                                </h3>
                                <p>
                                    Watering schedule and general crop notes. Consumable inputs are tracked against Inventory below.
                                </p>
                            </div>
                        </div>

                        <div className="crop-care-grid">
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">water_drop</span>
                                <div>
                                    <small>Watering Schedule</small>
                                    <strong>{crop.wateringSchedule}</strong>
                                </div>
                            </div>
                            <div className="crop-care-item">
                                <span className="material-symbols-outlined">update</span>
                                <div>
                                    <small>Last Update</small>
                                    <strong>{formatDate(crop.lastUpdate)}</strong>
                                </div>
                            </div>
                        </div>

                        <div className="crop-notes-box">
                            <strong>Notes</strong>
                            <p>{crop.notes}</p>
                        </div>
                    </section>

                    <PlantingPositions crop={crop} onChanged={onPlantingChanged} />
                    <ResourceUsagePanel
                        module="Crop"
                        target={crop}
                        canEdit={canEditResources}
                    />

                    <section className="crop-details-section pest-disease-section">
                        <div className="crop-details-section-heading">
                            <div>
                                <h3>
                                    Pest / Disease
                                </h3>

                                <p>
                                    Record any pest or
                                    disease detected for
                                    this crop.
                                </p>
                            </div>

                            <button
                                type="button"
                                className="pest-edit-button"
                                onClick={() => {
                                    const nextOpen = !showPestForm;
                                    if (nextOpen) {
                                        setPestForm(crop.activePestDisease || { ...initialPestForm, dateDetected: getTodayDateKey() });
                                    }
                                    setShowPestForm(nextOpen);
                                }}
                            >
                                <span className="material-symbols-outlined">
                                    edit
                                </span>

                                {crop.activePestDisease
                                    ? "Update Record"
                                    : "Add Record"}
                            </button>
                        </div>

                        {crop.pestDisease ? (
                            <div className="pest-record-card">
                                <div className="pest-record-top">
                                    <div className="pest-record-title">
                                        <span className="material-symbols-outlined">
                                            pest_control
                                        </span>

                                        <div>
                                            <strong>
                                                {
                                                    crop
                                                        .pestDisease
                                                        .type
                                                }
                                            </strong>

                                            <small>
                                                Detected on{" "}
                                                {formatDate(
                                                    crop
                                                        .pestDisease
                                                        .dateDetected
                                                )}
                                            </small>
                                        </div>
                                    </div>

                                    <span
                                        className={`pest-severity ${crop.pestDisease.severity.toLowerCase()}`}
                                    >
                                        {
                                            crop
                                                .pestDisease
                                                .severity
                                        }{" "}
                                        Severity
                                    </span>

                                    <span className={`pest-record-status ${String(crop.pestDisease.status || "Active").toLowerCase().replaceAll(" ", "-")}`}>
                                        {crop.pestDisease.status || "Active"}
                                    </span>
                                </div>

                                <div className="pest-record-details">
                                    <div>
                                        <small>
                                            Affected Area
                                        </small>

                                        <strong>
                                            {
                                                crop
                                                    .pestDisease
                                                    .affectedArea
                                            }
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Notes
                                        </small>

                                        <strong>
                                            {
                                                crop
                                                    .pestDisease
                                                    .notes
                                            }
                                        </strong>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="no-pest-record">
                                <span className="material-symbols-outlined">
                                    verified
                                </span>

                                <div>
                                    <strong>
                                        No pest or disease
                                        recorded
                                    </strong>

                                    <p>
                                        This crop currently
                                        has no detected pest
                                        or disease.
                                    </p>
                                </div>
                            </div>
                        )}

                        {showPestForm && (
                            <form
                                className="pest-record-form"
                                onSubmit={
                                    handlePestSubmit
                                }
                            >
                                <div className="pest-form-grid">
                                    <div className="crop-form-group">
                                        <label htmlFor="dateDetected">
                                            Date Detected
                                            <span>*</span>
                                        </label>

                                        <input
                                            id="dateDetected"
                                            name="dateDetected"
                                            type="date"
                                            value={
                                                pestForm.dateDetected
                                            }
                                            onChange={
                                                handlePestChange
                                            }
                                            required
                                            disabled={Boolean(pestForm.id)}
                                        />
                                    </div>

                                    <div className="crop-form-group">
                                        <label htmlFor="pestType">
                                            Pest / Disease
                                            Type
                                            <span>*</span>
                                        </label>

                                        <input
                                            id="pestType"
                                            name="type"
                                            type="text"
                                            placeholder="Example: Corn earworm"
                                            value={
                                                pestForm.type
                                            }
                                            onChange={
                                                handlePestChange
                                            }
                                            required
                                            disabled={Boolean(pestForm.id)}
                                        />
                                    </div>

                                    <div className="crop-form-group">
                                        <label htmlFor="pestSeverity">
                                            Severity
                                        </label>

                                        <select
                                            id="pestSeverity"
                                            name="severity"
                                            value={
                                                pestForm.severity
                                            }
                                            onChange={
                                                handlePestChange
                                            }
                                        >
                                            <option>
                                                Low
                                            </option>

                                            <option>
                                                Medium
                                            </option>

                                            <option>
                                                High
                                            </option>

                                            <option>
                                                Critical
                                            </option>
                                        </select>
                                    </div>

                                    <div className="crop-form-group">
                                        <label htmlFor="affectedArea">
                                            Affected Area
                                            <span>*</span>
                                        </label>

                                        <input
                                            id="affectedArea"
                                            name="affectedArea"
                                            type="text"
                                            placeholder="Example: 0.3 hectares"
                                            value={
                                                pestForm.affectedArea
                                            }
                                            onChange={
                                                handlePestChange
                                            }
                                            required
                                        />
                                    </div>
                                </div>

                                {pestForm.id && (
                                    <div className="crop-form-group">
                                        <label htmlFor="pestStatus">Case Status</label>
                                        <select
                                            id="pestStatus"
                                            name="status"
                                            value={pestForm.status || "Active"}
                                            onChange={handlePestChange}
                                        >
                                            <option>Active</option>
                                            <option>Under Treatment</option>
                                            <option>Resolved</option>
                                        </select>
                                        <small>Resolving the case automatically completes its Dashboard follow-up task.</small>
                                    </div>
                                )}

                                <div className="crop-form-group">
                                    <label htmlFor="pestNotes">
                                        Treatment / Notes
                                    </label>

                                    <textarea
                                        id="pestNotes"
                                        name="notes"
                                        rows="4"
                                        placeholder="Enter treatment or observation details..."
                                        value={
                                            pestForm.notes
                                        }
                                        onChange={
                                            handlePestChange
                                        }
                                    />
                                </div>

                                <div className="pest-form-buttons">
                                    <button
                                        type="button"
                                        onClick={() =>
                                            setShowPestForm(
                                                false
                                            )
                                        }
                                    >
                                        Cancel
                                    </button>

                                    <button type="submit">
                                        {pestForm.id ? "Update Pest / Disease" : "Save Pest / Disease Record"}
                                    </button>
                                </div>
                            </form>
                        )}
                    </section>
                </div>

                <footer className="crop-details-footer">
                    <button
                        type="button"
                        onClick={onClose}
                    >
                        Close
                    </button>
                </footer>
            </div>
        </div>
    );
}
