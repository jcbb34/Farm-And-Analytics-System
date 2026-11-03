"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useMemo,
    useState,
} from "react";

import { workforceService } from "../../services/workforceService.js";

import "./CropActionModals.css";

const qualityOptions = [
    "Grade A",
    "Grade B",
    "Grade C",
    "For Processing",
    "Rejected",
];

function getTodayDateKey() {
    const today = new Date();

    const year = today.getFullYear();
    const month = String(
        today.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        today.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

export function AddYieldModal({
    open,
    crops,
    employees = [],
    initialCropId = null,
    onClose,
    onSave,
}) {
    const [submitting, setSubmitting] = useState(false);
    const [finalHarvestBlockers, setFinalHarvestBlockers] = useState([]);
    const [finalHarvestCheckLoading, setFinalHarvestCheckLoading] = useState(false);
    const [finalHarvestCheckError, setFinalHarvestCheckError] = useState("");
    const [finalHarvestCheckVersion, setFinalHarvestCheckVersion] = useState(0);
    const [form, setForm] = useState({
        cropId: "",
        harvestDate: getTodayDateKey(),
        quantityKg: "",
        farmUseQuantityKg: "0",
        damagedQuantityKg: "0",
        reservedQuantityKg: "0",
        quality: "Grade A",
        harvestType: "Partial Harvest",
        performedByEmployeeId: "",
        manualReason: "",
        evidenceUrl: "",
        finalHarvestConfirmed: false,
        notes: "",
    });

    const selectedCrop = useMemo(() => {
        return crops.find(
            (crop) =>
                String(crop.id) ===
                String(form.cropId)
        );
    }, [crops, form.cropId]);

    const yieldPerHectare = useMemo(() => {
        if (
            !selectedCrop ||
            !form.quantityKg
        ) {
            return 0;
        }

        const quantity = Number(
            form.quantityKg
        );

        if (
            Number.isNaN(quantity) ||
            selectedCrop.area <= 0
        ) {
            return 0;
        }

        return (
            quantity / selectedCrop.area
        );
    }, [
        selectedCrop,
        form.quantityKg,
    ]);

    useEffect(() => {
        if (!open) {
            return;
        }

        const initialCrop = crops.find((crop) => String(crop.id) === String(initialCropId)) || crops[0] || null;

        setForm({
            cropId: initialCrop
                ? String(initialCrop.id)
                : "",
            harvestDate:
                getTodayDateKey(),
            quantityKg: "",
            farmUseQuantityKg: "0",
            damagedQuantityKg: "0",
            reservedQuantityKg: "0",
            quality: "Grade A",
            harvestType:
                "Partial Harvest",
            performedByEmployeeId: "",
            manualReason: "",
            evidenceUrl: "",
            finalHarvestConfirmed: false,
            notes: "",
        });
        setFinalHarvestBlockers([]);
        setFinalHarvestCheckLoading(false);
        setFinalHarvestCheckError("");
        setFinalHarvestCheckVersion(0);

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, crops, initialCropId]);

    useEffect(() => {
        if (
            !open
            || form.harvestType !== "Final Harvest"
            || !form.finalHarvestConfirmed
            || !form.cropId
            || !form.harvestDate
        ) {
            setFinalHarvestBlockers([]);
            setFinalHarvestCheckLoading(false);
            setFinalHarvestCheckError("");
            return;
        }

        let active = true;
        setFinalHarvestCheckLoading(true);
        setFinalHarvestCheckError("");

        workforceService
            .getTasks({
                source_module: "Crop",
                source_record_id: Number(form.cropId),
            })
            .then((rows) => {
                if (!active) return;
                const blockers = (Array.isArray(rows) ? rows : []).filter((task) =>
                    task.activity_date === form.harvestDate
                    && ["Pending", "In Progress", "Submitted for Review", "Returned"].includes(task.status)
                );
                setFinalHarvestBlockers(blockers);
            })
            .catch((error) => {
                if (!active) return;
                setFinalHarvestBlockers([]);
                setFinalHarvestCheckError(
                    error?.message || "Unable to verify same-day crop tasks before Final Harvest."
                );
            })
            .finally(() => {
                if (active) setFinalHarvestCheckLoading(false);
            });

        return () => {
            active = false;
        };
    }, [
        open,
        form.harvestType,
        form.finalHarvestConfirmed,
        form.cropId,
        form.harvestDate,
        finalHarvestCheckVersion,
    ]);

    if (!open) {
        return null;
    }

    const handleChange = (event) => {
        const { name, value, type, checked } = event.target;

        setForm((currentForm) => {
            const nextForm = {
                ...currentForm,
                [name]: type === "checkbox" ? checked : value,
            };

            // Final Harvest confirmation is intentionally one-time for the
            // currently selected crop/date/type. Changing that context makes
            // the manager confirm the closing consequence again.
            if (name === "harvestType" || name === "cropId" || name === "harvestDate") {
                nextForm.finalHarvestConfirmed = false;
            }

            return nextForm;
        });
    };

    const finalHarvestRequiresConfirmation = form.harvestType === "Final Harvest";
    const finalHarvestPrecheckBlocked = finalHarvestRequiresConfirmation && (
        !form.finalHarvestConfirmed
        || finalHarvestCheckLoading
        || Boolean(finalHarvestCheckError)
        || finalHarvestBlockers.length > 0
    );

    const openBlockingTask = (task) => {
        const returnTo = `/crops?cropId=${encodeURIComponent(form.cropId)}&addYield=1`;
        const query = new URLSearchParams({
            tab: "tasks",
            taskId: String(task.id),
            from: "crops",
            returnTo,
        });
        window.location.assign(`/task-management?${query.toString()}`);
    };

    const handleSubmit = async (event) => {
        event.preventDefault();

        if (submitting) {
            return;
        }

        if (
            !form.cropId ||
            !form.harvestDate ||
            !form.quantityKg
        ) {
            notify(
                "Please complete the required yield fields."
            );

            return;
        }

        if (!selectedCrop) {
            notify("No crop is currently eligible for harvest.");
            return;
        }

        if (form.harvestDate < selectedCrop.plantingDate) {
            notify("Harvest date cannot be earlier than the planting date.");
            return;
        }

        if (form.harvestDate > getTodayDateKey()) {
            notify("Harvest date cannot be in the future.");
            return;
        }

        const quantityKg = Number(
            form.quantityKg
        );

        if (
            Number.isNaN(quantityKg) ||
            quantityKg <= 0
        ) {
            notify(
                "Yield quantity must be greater than zero."
            );

            return;
        }

        const farmUseQuantityKg = Number(form.farmUseQuantityKg || 0);
        const damagedQuantityKg = Number(form.damagedQuantityKg || 0);
        const reservedQuantityKg = Number(form.reservedQuantityKg || 0);
        if ([farmUseQuantityKg, damagedQuantityKg, reservedQuantityKg].some((value) => Number.isNaN(value) || value < 0)) {
            notify("Harvest allocation quantities cannot be negative.");
            return;
        }
        if (farmUseQuantityKg + damagedQuantityKg + reservedQuantityKg > quantityKg) {
            notify("Farm use, damaged/spoiled, and reserved quantities cannot exceed the harvested quantity.");
            return;
        }
        if (!form.performedByEmployeeId) {
            notify("Select the employee who performed the harvest.");
            return;
        }
        if (!form.manualReason.trim()) {
            notify("Enter the required reason for recording this harvest manually.");
            return;
        }
        if (form.harvestType === "Final Harvest" && !form.finalHarvestConfirmed) {
            notify("Confirm that Final Harvest will close this crop cycle and stop future care tasks.");
            return;
        }
        if (form.harvestType === "Final Harvest" && finalHarvestCheckLoading) {
            notify("Please wait while same-day crop tasks are checked.");
            return;
        }
        if (form.harvestType === "Final Harvest" && finalHarvestCheckError) {
            notify("Final Harvest cannot continue until the same-day task check succeeds.");
            return;
        }
        if (form.harvestType === "Final Harvest" && finalHarvestBlockers.length > 0) {
            notify("Resolve the listed same-day crop task(s) before Final Harvest.");
            return;
        }

        setSubmitting(true);
        try {
            await onSave({
                cropId: Number(
                    form.cropId
                ),
                harvestDate:
                    form.harvestDate,
                quantityKg,
                farmUseQuantityKg,
                damagedQuantityKg,
                reservedQuantityKg,
                quality: form.quality,
                harvestType:
                    form.harvestType,
                performedByEmployeeId: Number(form.performedByEmployeeId),
                manualReason: form.manualReason.trim(),
                evidenceUrl: form.evidenceUrl.trim(),
                finalHarvestConfirmed: Boolean(form.finalHarvestConfirmed),
                notes: form.notes.trim(),
            });
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="crop-action-overlay"
            onMouseDown={onClose}
        >
            <div
                className="crop-action-modal yield-record-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="crop-action-header">
                    <div>
                        <h2>
                            Add Yield Record
                        </h2>

                        <p>
                            Only crops that are Ready for Harvest or already Harvesting are shown here.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close yield form"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="crop-action-form"
                    onSubmit={handleSubmit}
                >
                    <section className="crop-action-section">
                        <div className="crop-action-section-title">
                            <span className="material-symbols-outlined">
                                agriculture
                            </span>

                            <div>
                                <h3>
                                    Harvest Information
                                </h3>

                                <p>
                                    Enter the crop and
                                    harvested production.
                                </p>
                            </div>
                        </div>

                        {crops.length === 0 && (
                            <div className="final-harvest-notice crop-no-harvest-ready">
                                <span className="material-symbols-outlined">info</span>
                                <p>No crop is currently ready for harvest. Crops will appear here when their status becomes Ready for Harvest or Harvesting.</p>
                            </div>
                        )}

                        {selectedCrop && (
                            <div className="yield-calculation-grid" aria-label="Crop cycle context">
                                <div><small>Crop / Variety</small><strong>{selectedCrop.name} — {selectedCrop.variety || "Not Recorded"}</strong></div>
                                <div><small>Field</small><strong>{selectedCrop.field}</strong></div>
                                <div><small>Planting Date</small><strong>{selectedCrop.plantingDate || "Not Recorded"}</strong></div>
                                <div><small>Previous Partial Harvests</small><strong>{Number(selectedCrop.previousPartialHarvestTotalKg || 0).toLocaleString("en-US", { maximumFractionDigits: 2 })} kg</strong></div>
                                <div><small>Existing Harvest Count</small><strong>{selectedCrop.harvestCount || 0}</strong></div>
                                <div><small>Readiness</small><strong>{selectedCrop.readinessStatus || "Estimated Ready"}</strong></div>
                            </div>
                        )}

                        <div className="crop-action-form-grid">
                            <div className="crop-action-form-group full-width">
                                <label htmlFor="yieldCrop">
                                    Crop Record
                                    <span>*</span>
                                </label>

                                <select
                                    id="yieldCrop"
                                    name="cropId"
                                    value={
                                        form.cropId
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                >
                                    <option value="">
                                        Select Crop
                                    </option>

                                    {crops.map((crop) => (
                                        <option
                                            key={crop.id}
                                            value={crop.id}
                                        >
                                            {crop.name} —{" "}
                                            {crop.field}
                                        </option>
                                    ))}
                                </select>
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="harvestDate">
                                    Harvest Date
                                    <span>*</span>
                                </label>

                                <input
                                    id="harvestDate"
                                    name="harvestDate"
                                    type="date"
                                    min={selectedCrop?.plantingDate || undefined}
                                    max={getTodayDateKey()}
                                    value={
                                        form.harvestDate
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="quantityKg">
                                    Harvested Quantity
                                    <span>*</span>
                                </label>

                                <div className="crop-action-unit-input">
                                    <input
                                        id="quantityKg"
                                        name="quantityKg"
                                        type="number"
                                        min="0.01"
                                        step="0.01"
                                        placeholder="0"
                                        value={
                                            form.quantityKg
                                        }
                                        onChange={
                                            handleChange
                                        }
                                        required
                                    />

                                    <span>kg</span>
                                </div>
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="yieldQuality">
                                    Product Quality
                                </label>

                                <select
                                    id="yieldQuality"
                                    name="quality"
                                    value={
                                        form.quality
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {qualityOptions.map(
                                        (quality) => (
                                            <option
                                                key={
                                                    quality
                                                }
                                                value={
                                                    quality
                                                }
                                            >
                                                {
                                                    quality
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="harvestType">
                                    Harvest Type
                                </label>

                                <select
                                    id="harvestType"
                                    name="harvestType"
                                    value={
                                        form.harvestType
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option>
                                        Partial Harvest
                                    </option>

                                    <option>
                                        Final Harvest
                                    </option>
                                </select>
                            </div>


                            <div className="crop-action-form-group">
                                <label htmlFor="performedByEmployeeId">Performed By <span>*</span></label>
                                <select id="performedByEmployeeId" name="performedByEmployeeId" value={form.performedByEmployeeId} onChange={handleChange} required>
                                    <option value="">Select employee</option>
                                    {employees.map((employee) => (
                                        <option key={employee.id} value={employee.id}>{employee.full_name || employee.fullName || employee.employee_code || `Employee #${employee.id}`}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="crop-action-form-group full-width">
                                <label htmlFor="manualReason">Reason for Manual / Assisted Recording <span>*</span></label>
                                <input id="manualReason" name="manualReason" value={form.manualReason} onChange={handleChange} placeholder="Example: Harvest recorded by manager after field collection" required />
                            </div>

                            <div className="crop-action-form-group full-width">
                                <label htmlFor="evidenceUrl">Evidence Reference (optional)</label>
                                <input id="evidenceUrl" name="evidenceUrl" value={form.evidenceUrl} onChange={handleChange} placeholder="Existing evidence URL or reference" />
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="farmUseQuantityKg">Farm Use (kg)</label>
                                <input id="farmUseQuantityKg" name="farmUseQuantityKg" type="number" min="0" step="0.01" value={form.farmUseQuantityKg} onChange={handleChange} />
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="damagedQuantityKg">Damaged / Spoiled (kg)</label>
                                <input id="damagedQuantityKg" name="damagedQuantityKg" type="number" min="0" step="0.01" value={form.damagedQuantityKg} onChange={handleChange} />
                            </div>

                            <div className="crop-action-form-group">
                                <label htmlFor="reservedQuantityKg">Reserved / Seed (kg)</label>
                                <input id="reservedQuantityKg" name="reservedQuantityKg" type="number" min="0" step="0.01" value={form.reservedQuantityKg} onChange={handleChange} />
                            </div>
                        </div>

                        <div className="yield-calculation-grid">
                            <div>
                                <small>
                                    Field Area
                                </small>

                                <strong>
                                    {selectedCrop
                                        ? `${selectedCrop.area} ha`
                                        : "—"}
                                </strong>
                            </div>

                            <div>
                                <small>
                                    Yield per Hectare
                                </small>

                                <strong>
                                    {yieldPerHectare.toLocaleString(
                                        "en-US",
                                        {
                                            maximumFractionDigits:
                                                2,
                                        }
                                    )}{" "}
                                    kg/ha
                                </strong>
                            </div>

                            <div>
                                <small>
                                    Current Crop Status
                                </small>

                                <strong>
                                    {selectedCrop
                                        ? selectedCrop.status
                                        : "—"}
                                </strong>
                            </div>
                            <div>
                                <small>Available for Sale</small>
                                <strong>
                                    {Math.max(0, Number(form.quantityKg || 0) - Number(form.farmUseQuantityKg || 0) - Number(form.damagedQuantityKg || 0) - Number(form.reservedQuantityKg || 0)).toLocaleString("en-US", { maximumFractionDigits: 2 })} kg
                                </strong>
                            </div>
                            <div>
                                <small>Resulting Seasonal Yield</small>
                                <strong>{(Number(selectedCrop?.totalHarvestQuantityKg || 0) + Number(form.quantityKg || 0)).toLocaleString("en-US", { maximumFractionDigits: 2 })} kg</strong>
                            </div>
                            <div>
                                <small>Resulting Crop Status</small>
                                <strong>{form.harvestType === "Final Harvest" ? "Fully Harvested/Completed" : "Harvesting"}</strong>
                            </div>
                        </div>

                        {form.harvestType === "Partial Harvest" && (
                            <div className="final-harvest-notice">
                                <span className="material-symbols-outlined">
                                    info
                                </span>

                                <p>
                                    A partial harvest keeps the crop active and
                                    changes its stage to Harvesting / Production.
                                    More yield records can still be added later.
                                </p>
                            </div>
                        )}

                        {form.harvestType === "Final Harvest" && (
                            <div className="final-harvest-notice">
                                <span className="material-symbols-outlined">warning</span>
                                <div>
                                    <p><strong>Final Harvest will close this crop cycle and stop future care tasks.</strong> You will not be able to record another harvest unless an authorized manager reopens the cycle.</p>
                                    <label className="crop-final-confirm">
                                        <input
                                            type="checkbox"
                                            name="finalHarvestConfirmed"
                                            checked={form.finalHarvestConfirmed}
                                            onChange={handleChange}
                                            required
                                            aria-required="true"
                                        />
                                        <span>
                                            I confirm this is the final harvest for this crop cycle.
                                            <strong className="crop-required-indicator"> Required</strong>
                                        </span>
                                    </label>
                                    {!form.finalHarvestConfirmed && (
                                        <p className="crop-final-confirm-help">
                                            The manager must check this confirmation before Final Harvest can be saved.
                                        </p>
                                    )}
                                    {form.finalHarvestConfirmed && finalHarvestCheckLoading && (
                                        <p className="crop-final-task-check" role="status">
                                            Checking unresolved same-day crop tasks...
                                        </p>
                                    )}
                                    {form.finalHarvestConfirmed && finalHarvestCheckError && (
                                        <div className="crop-final-task-blockers" role="alert">
                                            <strong>Same-day task check failed.</strong>
                                            <p>{finalHarvestCheckError}</p>
                                            <button
                                                type="button"
                                                className="crop-final-task-action"
                                                onClick={() => setFinalHarvestCheckVersion((value) => value + 1)}
                                            >
                                                Check Again
                                            </button>
                                        </div>
                                    )}
                                    {form.finalHarvestConfirmed && !finalHarvestCheckLoading && !finalHarvestCheckError && finalHarvestBlockers.length > 0 && (
                                        <div className="crop-final-task-blockers" role="alert">
                                            <strong>Resolve same-day crop tasks before closing this crop cycle.</strong>
                                            <p>Final Harvest remains disabled until these tasks are resolved.</p>
                                            <ul>
                                                {finalHarvestBlockers.map((task) => (
                                                    <li key={task.id}>
                                                        <span>{task.activity_code || `Task ${task.id}`} — {task.status}</span>
                                                        <button
                                                            type="button"
                                                            className="crop-final-task-action"
                                                            onClick={() => openBlockingTask(task)}
                                                        >
                                                            Open Task
                                                        </button>
                                                    </li>
                                                ))}
                                            </ul>
                                        </div>
                                    )}
                                    {form.finalHarvestConfirmed && !finalHarvestCheckLoading && !finalHarvestCheckError && finalHarvestBlockers.length === 0 && (
                                        <p className="crop-final-task-clear" role="status">
                                            No unresolved same-day crop tasks. Final Harvest can proceed.
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}

                        <div className="crop-action-form-group">
                            <label htmlFor="yieldNotes">
                                Harvest Notes
                            </label>

                            <textarea
                                id="yieldNotes"
                                name="notes"
                                rows="4"
                                placeholder="Enter harvest observations, storage instructions, or quality notes..."
                                value={
                                    form.notes
                                }
                                onChange={
                                    handleChange
                                }
                            />
                        </div>
                    </section>

                    <footer className="crop-action-footer">
                        <button
                            type="button"
                            className="crop-action-cancel"
                            onClick={onClose}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="crop-action-save"
                            disabled={crops.length === 0 || submitting || finalHarvestPrecheckBlocked}
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            {submitting ? "Saving Harvest..." : "Save Yield Record"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}
