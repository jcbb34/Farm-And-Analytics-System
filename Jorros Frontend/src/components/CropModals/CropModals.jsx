"use client";

import { MonitoringScheduleFields, scheduleForm, HistoryDateRange, useHistoryRange } from "../Monitoring/Monitoring.jsx";

import FarmLocationInput from "../FarmLocationInput/FarmLocationInput.jsx";
import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useRef,
    useState,
} from "react";

import {
    calculateAutomaticCropProgress,
    getAutomaticGrowthStage,
    parseWateringSchedule,
    serializeWateringSchedule,
    WATERING_FREQUENCIES,
    WATERING_PERIODS,
    WATERING_WEEKDAYS,
} from "../../services/cropService.js";
import ResourceUsagePanel from "../ResourceUsagePanel/ResourceUsagePanel.jsx";
import { workforceService } from "../../services/workforceService.js";

import "./CropModals.css";

const emptyCropForm = {
    ...scheduleForm({}, true),
    name: "",
    variety: "",
    field: "",
    area: "",
    plantingDate: "",
    estimatedHarvest: "",
    quantityPlanted: "",
    currentSurviving: "",
    wateringFrequency: "Daily",
    wateringDays: [],
    wateringPeriods: ["Morning"],
    wateringLegacy: "",
    notes: "",
    assignedEmployeeId: "",
    careTemplateId: "",
    futureCareTaskAction: "",
    statusMode: "Automatic",
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

    const watering = parseWateringSchedule(crop.wateringSchedule);

    return {
        ...scheduleForm(crop, true),
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
        wateringFrequency: watering.frequency,
        wateringDays: watering.days,
        wateringPeriods: watering.periods,
        wateringLegacy: watering.legacy,
        notes:
            crop.notes ===
            "No additional notes."
                ? ""
                : crop.notes ?? "",
        assignedEmployeeId: crop.assignedEmployeeId == null ? "" : String(crop.assignedEmployeeId),
        careTemplateId: crop.careTemplateId == null ? "" : String(crop.careTemplateId),
        futureCareTaskAction: "",
        statusMode:
            crop.status === "Failed"
                ? "Failed"
                : crop.status === "Harvested"
                  ? "Harvested"
                  : "Automatic",
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
    const [careTemplates, setCareTemplates] = useState([]);

    useEffect(() => {
        if (open) {
            submittingRef.current = false;
            setSaving(false);
            setForm(
                editing
                    ? cropToForm(crop)
                    : emptyCropForm
            );
            Promise.all([
                workforceService.getEmployees(),
                workforceService.getCareTemplates("Crop", false),
            ]).then(([employeeRows, templateRows]) => {
                setEmployees(employeeRows || []);
                setCareTemplates(templateRows || []);
            }).catch((error) => {
                console.warn("Unable to load crop workforce choices:", error);
                setEmployees([]);
                setCareTemplates([]);
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

    const handleChange = (event) => {
        const { name, value } =
            event.target;

        setForm((currentForm) => ({
            ...currentForm,
            [name]: value,
        }));
    };

    const handleWateringFrequencyChange = (event) => {
        const frequency = event.target.value;
        setForm((currentForm) => ({
            ...currentForm,
            wateringFrequency: frequency,
            wateringDays: [],
            wateringPeriods:
                frequency === "Twice Daily"
                    ? ["Morning", "Afternoon"]
                    : ["As Needed", "Rain-Fed", "Automated/Continuous"].includes(frequency)
                      ? []
                      : ["Morning"],
            wateringLegacy: "",
        }));
    };

    const toggleWateringValue = (field, value, maximum = null) => {
        setForm((currentForm) => {
            const values = Array.isArray(currentForm[field]) ? currentForm[field] : [];
            const exists = values.includes(value);
            let next = exists ? values.filter((item) => item !== value) : [...values, value];
            if (maximum && next.length > maximum) {
                next = next.slice(next.length - maximum);
            }
            return { ...currentForm, [field]: next, wateringLegacy: "" };
        });
    };

    const visualProgress =
        editing && form.statusMode === "Harvested"
            ? 100
            : calculateAutomaticCropProgress(
                  form.plantingDate,
                  form.estimatedHarvest
              );

    const automaticGrowthStage =
        editing && form.statusMode === "Harvested"
            ? "Harvested"
            : getAutomaticGrowthStage(
                  visualProgress
              );

    const survivalRate =
        Number(form.quantityPlanted) > 0 &&
        form.currentSurviving !== ""
            ? Math.round(
                  (Number(form.currentSurviving) /
                      Number(form.quantityPlanted)) *
                      1000
              ) / 10
            : null;


    const closeForm = () => { if (!submittingRef.current) onClose(); };

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (submittingRef.current) return;

        if (
            !form.name.trim() ||
            !form.variety.trim() ||
            !form.field.trim() ||
            !form.area ||
            !form.plantingDate ||
            !form.estimatedHarvest
        ) {
            notify(
                "Please complete all required crop fields."
            );
            return;
        }

        const area = Number(form.area);
        const quantityPlanted =
            form.quantityPlanted === ""
                ? 0
                : Number(form.quantityPlanted);

        const currentSurviving =
            form.currentSurviving === ""
                ? quantityPlanted
                : Number(form.currentSurviving);

        if (area <= 0) {
            notify(
                "Crop area must be greater than zero."
            );
            return;
        }

        if (
            !Number.isInteger(quantityPlanted) ||
            quantityPlanted < 0 ||
            !Number.isInteger(currentSurviving) ||
            currentSurviving < 0 ||
            currentSurviving > quantityPlanted
        ) {
            notify(
                "Quantity planted and current surviving must be whole numbers, and surviving plants cannot exceed the quantity planted."
            );
            return;
        }

        if (
            form.estimatedHarvest <
            form.plantingDate
        ) {
            notify(
                "Estimated harvest date must be later than or equal to the planting date."
            );
            return;
        }

        let wateringSchedule = form.wateringLegacy;
        if (form.wateringFrequency) {
            const frequency = form.wateringFrequency;
            const days = form.wateringDays || [];
            const periods = form.wateringPeriods || [];

            if (frequency === "3 Times per Week" && days.length !== 3) {
                notify("Please select exactly 3 watering days.");
                return;
            }
            if (frequency === "Weekly" && days.length !== 1) {
                notify("Please select exactly 1 watering day.");
                return;
            }
            if (frequency === "Twice Daily" && periods.length !== 2) {
                notify("Please select exactly 2 watering periods for Twice Daily.");
                return;
            }
            if (["Daily", "Every 2 Days", "3 Times per Week", "Weekly"].includes(frequency) && periods.length !== 1) {
                notify("Please select exactly 1 watering period for this schedule.");
                return;
            }

            wateringSchedule = serializeWateringSchedule({ frequency, days, periods });
        }

        if (
            editing
            && crop?.careTemplateId
            && !form.careTemplateId
            && !form.futureCareTaskAction
        ) {
            notify("Choose what should happen to future Pending care tasks before removing this care template.");
            return;
        }

        const payload = {
            name: form.name.trim(),
            variety:
                form.variety.trim(),
            field: form.field.trim(),
            area,
            plantingDate:
                form.plantingDate,
            estimatedHarvest:
                form.estimatedHarvest,
            quantityPlanted,
            currentSurviving,
            wateringSchedule: wateringSchedule || "Not specified",
            notes:
                form.notes.trim() ||
                "No additional notes.",
            ...scheduleForm(form, true),
            assignedEmployeeId: form.assignedEmployeeId ? Number(form.assignedEmployeeId) : null,
            careTemplateId: form.careTemplateId ? Number(form.careTemplateId) : null,
            futureCareTaskAction: form.futureCareTaskAction || undefined,
        };

        if (editing) {
            payload.statusMode = form.statusMode;
        }

        submittingRef.current = true;
        setSaving(true);
        try {
            await onSave(payload);
        } catch (error) {
            notify(error?.message || "Unable to save crop. Your entries are kept for retry.");
        } finally {
            submittingRef.current = false;
            setSaving(false);
        }
    };

    const idPrefix = editing
        ? "edit-crop"
        : "add-crop";

    return (
        <div
            className="crop-modal-overlay"
            onMouseDown={closeForm}
        >
            <div
                className="add-crop-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="crop-modal-header">
                    <div>
                        <h2>
                            {editing
                                ? "Edit Crop"
                                : "Add Crop"}
                        </h2>

                        <p>
                            {editing
                                ? "Update crop information and surviving plants. Schedule estimates remain separate from approved observations."
                                : "Add a crop record with its planting schedule and planted quantity. Growth tracking starts automatically."}
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
                    <fieldset className="crop-form-fields" disabled={saving}>
                    <section className="crop-form-section">
                        <div className="crop-form-section-title">
                            <span className="material-symbols-outlined">
                                eco
                            </span>

                            <div>
                                <h3>
                                    Crop Information
                                </h3>

                                <p>
                                    Enter the basic crop
                                    and field details.
                                </p>
                            </div>
                        </div>

                        <div className="crop-form-grid">
                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-name`}>
                                    Crop Name
                                    <span>*</span>
                                </label>

                                <input
                                    id={`${idPrefix}-name`}
                                    name="name"
                                    type="text"
                                    placeholder="Example: Yellow Corn"
                                    value={form.name}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-variety`}>
                                    Variety
                                    <span>*</span>
                                </label>

                                <input
                                    id={`${idPrefix}-variety`}
                                    name="variety"
                                    type="text"
                                    placeholder="Example: Hybrid Corn"
                                    value={form.variety}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-field`}>
                                    Field / Location
                                    <span>*</span>
                                </label>

                                <FarmLocationInput id={`${idPrefix}-field`} name="field" label="Field / Location" knownOptions={fieldOptions} context="crops" active={open} value={form.field} onValueChange={(field) => setForm((old) => ({ ...old, field }))} required maxLength={100} />
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-area`}>
                                    Area in Hectares
                                    <span>*</span>
                                </label>

                                <input
                                    id={`${idPrefix}-area`}
                                    name="area"
                                    type="number"
                                    min="0.01"
                                    step="0.01"
                                    placeholder="0.00"
                                    value={form.area}
                                    onChange={handleChange}
                                    required
                                />
                            </div>
                        </div>
                    </section>

                    <section className="crop-form-section">
                        <div className="crop-form-section-title">
                            <span className="material-symbols-outlined">
                                calendar_month
                            </span>

                            <div>
                                <h3>Planting & Growth</h3>
                                <p>
                                    Estimated progress follows the planting schedule. Approved observations record the actual stage; harvest readiness requires confirmation.
                                </p>
                            </div>
                        </div>

                        <div className="crop-form-grid">
                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-planting-date`}>
                                    Planting Date <span>*</span>
                                </label>
                                <input
                                    id={`${idPrefix}-planting-date`}
                                    name="plantingDate"
                                    type="date"
                                    value={form.plantingDate}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-estimated-harvest`}>
                                    Expected First Harvest <span>*</span>
                                </label>
                                <input
                                    id={`${idPrefix}-estimated-harvest`}
                                    name="estimatedHarvest"
                                    type="date"
                                    value={form.estimatedHarvest}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="crop-form-group">
                                <label>Automatic Growth Stage</label>
                                <input
                                    type="text"
                                    value={automaticGrowthStage}
                                    readOnly
                                    disabled
                                />
                            </div>

                            <div className="crop-form-group">
                                <label>Automatic Growth Progress</label>
                                <div className="growth-input-wrapper">
                                    <input
                                        type="text"
                                        value={`${visualProgress}%`}
                                        readOnly
                                        disabled
                                    />
                                    <span>%</span>
                                </div>
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-quantity-planted`}>
                                    Quantity Planted
                                </label>
                                <input
                                    id={`${idPrefix}-quantity-planted`}
                                    name="quantityPlanted"
                                    type="number"
                                    min="0"
                                    step="1"
                                    placeholder="Example: 500"
                                    value={form.quantityPlanted}
                                    onChange={handleChange}
                                />
                            </div>

                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-current-surviving`}>
                                    Current Surviving Plants
                                </label>
                                <input
                                    id={`${idPrefix}-current-surviving`}
                                    name="currentSurviving"
                                    type="number"
                                    min="0"
                                    step="1"
                                    max={form.quantityPlanted || undefined}
                                    placeholder="Example: 462"
                                    value={form.currentSurviving}
                                    onChange={handleChange}
                                />
                                {survivalRate !== null && (
                                    <small>
                                        Automatic survival rate: {survivalRate}%
                                    </small>
                                )}
                            </div>

                            {editing && (
                                <div className="crop-form-group">
                                    <label htmlFor={`${idPrefix}-record-status`}>
                                        Record Status
                                    </label>
                                    <select
                                        id={`${idPrefix}-record-status`}
                                        name="statusMode"
                                        value={form.statusMode}
                                        onChange={handleChange}
                                    >
                                        <option value="Automatic">Automatic / Active</option>
                                        <option value="Harvested">Harvested</option>
                                        <option value="Failed">Failed</option>
                                    </select>
                                </div>
                            )}
                        </div>

                        <p className="crop-form-info-note">
                            <span className="material-symbols-outlined">info</span>
                            <span>
                                Growth percentage and growth stage are system-controlled from the planting schedule. Only planted quantity and current surviving plants are edited manually; survival rate is calculated automatically.
                            </span>
                        </p>
                    </section>

                    <section className="crop-form-section">
                        <div className="crop-form-section-title">
                            <span className="material-symbols-outlined">
                                compost
                            </span>

                            <div>
                                <h3>
                                    Crop Maintenance
                                </h3>

                                <p>
                                    Use a standardized watering schedule so automatic tasks are consistent. Fertilizer, pesticide, herbicide, and other consumables are recorded through Inventory Resource Usage and deduct stock immediately.
                                </p>
                            </div>
                        </div>

                        <div className="crop-form-grid watering-schedule-grid">
                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-watering-frequency`}>
                                    Watering Frequency
                                </label>
                                <select
                                    id={`${idPrefix}-watering-frequency`}
                                    value={form.wateringFrequency}
                                    onChange={handleWateringFrequencyChange}
                                >
                                    {form.wateringLegacy && !form.wateringFrequency && (
                                        <option value="">Existing / Legacy Schedule</option>
                                    )}
                                    {WATERING_FREQUENCIES.map((frequency) => (
                                        <option key={frequency} value={frequency}>
                                            {frequency}
                                        </option>
                                    ))}
                                </select>
                                {form.wateringLegacy && !form.wateringFrequency && (
                                    <small>
                                        Existing value: {form.wateringLegacy}. Select a standardized schedule to enable reliable automatic watering tasks.
                                    </small>
                                )}
                            </div>

                            {["3 Times per Week", "Weekly"].includes(form.wateringFrequency) && (
                                <div className="crop-form-group full-width watering-option-group">
                                    <label>Watering Days</label>
                                    <div className="watering-chip-group" role="group" aria-label="Watering days">
                                        {WATERING_WEEKDAYS.map((day) => {
                                            const active = form.wateringDays.includes(day);
                                            return (
                                                <button
                                                    key={day}
                                                    type="button"
                                                    className={active ? "watering-chip active" : "watering-chip"}
                                                    onClick={() =>
                                                        toggleWateringValue(
                                                            "wateringDays",
                                                            day,
                                                            form.wateringFrequency === "Weekly" ? 1 : 3
                                                        )
                                                    }
                                                >
                                                    {day.slice(0, 3)}{active ? " ✓" : ""}
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <small>
                                        {form.wateringFrequency === "Weekly"
                                            ? "Select exactly 1 day."
                                            : "Select exactly 3 days, for example Monday, Wednesday, and Friday."}
                                    </small>
                                </div>
                            )}

                            {!["As Needed", "Rain-Fed", "Automated/Continuous"].includes(form.wateringFrequency) && (
                                <div className="crop-form-group full-width watering-option-group">
                                    <label>Watering Period</label>
                                    <div className="watering-chip-group" role="group" aria-label="Watering periods">
                                        {WATERING_PERIODS.map((period) => {
                                            const active = form.wateringPeriods.includes(period);
                                            const maximum = form.wateringFrequency === "Twice Daily" ? 2 : 1;
                                            return (
                                                <button
                                                    key={period}
                                                    type="button"
                                                    className={active ? "watering-chip active" : "watering-chip"}
                                                    onClick={() => toggleWateringValue("wateringPeriods", period, maximum)}
                                                >
                                                    {period}{active ? " ✓" : ""}
                                                </button>
                                            );
                                        })}
                                    </div>
                                    <small>
                                        {form.wateringFrequency === "Twice Daily"
                                            ? "Select exactly 2 periods."
                                            : "Select exactly 1 period."}
                                    </small>
                                </div>
                            )}
                        </div>

                        <div className="crop-form-group">
                            <label htmlFor={`${idPrefix}-notes`}>
                                Notes
                            </label>

                            <textarea
                                id={`${idPrefix}-notes`}
                                name="notes"
                                rows="4"
                                placeholder="Enter crop observations or instructions..."
                                value={form.notes}
                                onChange={handleChange}
                            />
                        </div>
                    </section>


                    <section className="crop-form-section">
                        <div className="crop-form-section-title">
                            <span className="material-symbols-outlined">assignment_ind</span>
                            <div><h3>Employee & Care Plan</h3><p>Assign responsibility and optionally generate scheduled work from an approved care template.</p></div>
                        </div>
                        <div className="crop-form-grid">
                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-employee`}>Assigned Employee</label>
                                <select id={`${idPrefix}-employee`} name="assignedEmployeeId" value={form.assignedEmployeeId} onChange={handleChange}>
                                    <option value="">Unassigned</option>
                                    {employees.filter((employee) => employee.employment_status === "Active").map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name} — {employee.positions?.length ? `${employee.positions.find((p)=>p.is_primary)?.name || employee.positions[0].name}${employee.positions.length > 1 ? ` +${employee.positions.length - 1} more` : ""}` : employee.position || "Employee"}</option>)}
                                </select>
                            </div>
                            <div className="crop-form-group">
                                <label htmlFor={`${idPrefix}-care-template`}>Crop Care Template</label>
                                <select id={`${idPrefix}-care-template`} name="careTemplateId" value={form.careTemplateId} onChange={handleChange}>
                                    <option value="">No template</option>
                                    {careTemplates.map((template) => <option key={template.id} value={template.id}>{template.name} ({template.steps?.length || 0} steps)</option>)}
                                </select>
                            </div>
                            {editing && crop?.careTemplateId && !form.careTemplateId && (
                                <div className="crop-form-group">
                                    <label htmlFor={`${idPrefix}-future-care-action`}>Future Pending Care Tasks</label>
                                    <select id={`${idPrefix}-future-care-action`} name="futureCareTaskAction" value={form.futureCareTaskAction} onChange={handleChange} required>
                                        <option value="">Choose an action</option>
                                        <option value="keep">Keep existing future tasks</option>
                                        <option value="resolve">Resolve future tasks</option>
                                    </select>
                                </div>
                            )}
                        </div>
                    </section>
                    <MonitoringScheduleFields value={form} onChange={setForm} module="Crop" earliestDate={form.plantingDate} />
                    </fieldset>
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
        if (surviving > Number(crop.quantityPlanted || 0)) {
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

                    {crop.careTemplateId && (
                        <section className="crop-details-section">
                            <div className="crop-details-section-heading">
                                <div>
                                    <h3>Assigned Care Protocol</h3>
                                    <p>Care guidance linked to this planting cycle. Built-in watering and harvest schedules remain the source of those tasks.</p>
                                </div>
                            </div>
                            <div className="crop-care-grid">
                                <div className="crop-care-item">
                                    <span className="material-symbols-outlined" aria-hidden="true">assignment</span>
                                    <div><small>Protocol</small><strong>{crop.careProtocolName || `Protocol #${crop.careTemplateId}`}{crop.careProtocolVersion ? ` · v${crop.careProtocolVersion}` : ""}</strong></div>
                                </div>
                                <div className="crop-care-item">
                                    <span className="material-symbols-outlined" aria-hidden="true">verified</span>
                                    <div><small>Status</small><strong>{crop.careProtocolStatus || "Assigned"}</strong></div>
                                </div>
                            </div>
                        </section>
                    )}

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
                                {(crop.estimatedProgress ?? crop.growth)}%
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
                                        {crop.currentSurviving ?? 0} / {crop.quantityPlanted ?? 0}
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
                                    width: `${(crop.estimatedProgress ?? crop.growth)}%`,
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

                    <div className="monitoring-summary"><div><dt>Estimated schedule progress</dt><dd>{crop.estimatedProgress ?? crop.growth}%</dd></div><div><dt>Latest approved observed stage</dt><dd>{crop.observedGrowthStage || (crop.readinessStatus === "Confirmed Ready" ? "Harvest Ready (confirmed)" : "Not recorded")}</dd></div><div><dt>Last inspection</dt><dd>{crop.monitoringSummary?.last_date || crop.lastObservationDate || "Not recorded"}</dd></div></div>
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
                                            <span>{record.growth}% estimated{record.relatedTaskId && <a href={`/task-management?taskId=${record.relatedTaskId}&tab=tasks`}> View approved work</a>}</span>
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
                                            max={crop.quantityPlanted}
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
