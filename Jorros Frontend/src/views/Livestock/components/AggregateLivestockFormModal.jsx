"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { farmDateKey } from "../../../utils/farmCalendar.js";
import { useEffect, useMemo, useState } from "react";
import { livestockService } from "../../../services/livestockService.js";
import "../../../components/LivestockModals/LivestockModals.css";
import "./AggregateLivestockFormModal.css";

const ANIMAL_TYPES = ["Pig", "Goat", "Chicken", "Duck", "Cattle", "Other"];
const GROWTH_STATUSES = ["Newborn", "Growing", "Mature", "Breeding", "Production"];
const VACCINATION_STATUSES = ["Not Vaccinated", "Scheduled", "Due", "Due Soon", "Up to Date"];
const PRODUCTION_PURPOSES = [
    "General",
    "Growing",
    "Breeding",
    "Pregnancy / Maternity",
    "Laying / Egg Production",
    "Meat Production",
    "Dual Purpose",
    "Lactating",
    "Market Ready",
];

function todayValue() {
    return farmDateKey();
}

function initialForm(animal) {
    const quantity = Number(animal?.quantity ?? 1);
    const health = animal?.healthStatus || "Healthy";
    const sex = animal?.sex || "Mixed";

    return {
        recordName: animal?.recordName || "",
        type: animal?.type || "Pig",
        breed: animal?.breed || "",
        quantity: String(quantity),
        maleQuantity: String(animal?.maleQuantity ?? (sex === "Male" ? quantity : 0)),
        femaleQuantity: String(animal?.femaleQuantity ?? (sex === "Female" ? quantity : 0)),
        unknownSexQuantity: String(
            animal?.unknownSexQuantity ?? (!["Male", "Female"].includes(sex) ? quantity : 0)
        ),
        dateOfBirth: animal?.dateOfBirth || "",
        weight: String(animal?.weight ?? ""),
        minWeight: String(animal?.minWeight ?? animal?.weight ?? ""),
        maxWeight: String(animal?.maxWeight ?? animal?.weight ?? ""),
        penId: animal?.penId ? String(animal.penId) : "",
        penLocation: animal?.penLocation || "",
        healthyQuantity: String(animal?.healthyQuantity ?? (health === "Healthy" ? quantity : 0)),
        atRiskQuantity: String(animal?.atRiskQuantity ?? (health === "At Risk" ? quantity : 0)),
        sickQuantity: String(animal?.sickQuantity ?? (health === "Sick" ? quantity : 0)),
        underTreatmentQuantity: String(
            animal?.underTreatmentQuantity ?? (health === "Under Treatment" ? quantity : 0)
        ),
        growthStatus: animal?.growthStatus || "Growing",
        productionPurpose: animal?.productionPurpose || "General",
        lastCheckup: animal?.lastCheckup || "",
        vaccinationStatus: animal?.vaccinationStatus || "Not Vaccinated",
        nextVaccination: animal?.nextVaccination || "",
        healthNotes: animal?.healthNotes || "",
        feedTimes: animal?.feedingSchedule?.times || "",
        feedType: animal?.feedingSchedule?.feedType || "",
        dailyFeedKg: String(animal?.feedingSchedule?.dailyAmountKg ?? ""),
        feedingNotes: animal?.feedingSchedule?.notes || "",
        dateAcquired: animal?.dateAcquired || todayValue(),
        acquiredFrom: animal?.acquiredFrom || "",
        lifecycleStatus: animal?.lifecycleStatus || "Active",
    };
}

function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function healthLabel(form, quantity) {
    const values = [
        ["Healthy", number(form.healthyQuantity)],
        ["At Risk", number(form.atRiskQuantity)],
        ["Sick", number(form.sickQuantity)],
        ["Under Treatment", number(form.underTreatmentQuantity)],
    ];
    const active = values.filter(([, count]) => count > 0);
    if (active.length > 1) return "Mixed";
    if (active.length === 1 && active[0][1] === quantity) return active[0][0];
    return "Healthy";
}

function sexLabel(form, quantity) {
    if (number(form.maleQuantity) === quantity) return "Male";
    if (number(form.femaleQuantity) === quantity) return "Female";
    return "Mixed";
}

export default function AggregateLivestockFormModal({ open, animal, onClose, onSave }) {
    const [form, setForm] = useState(() => initialForm(animal));
    const [pens, setPens] = useState([]);
    const [busy, setBusy] = useState(false);
    const [loadError, setLoadError] = useState("");

    useEffect(() => {
        if (!open) return;
        setForm(initialForm(animal));
        setLoadError("");
        livestockService
            .getPens()
            .then(setPens)
            .catch((error) => {
                console.error("Failed to load pens:", error);
                setPens([]);
                setLoadError("Unable to load pens. Open Manage Pens and try again.");
            });
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = "";
        };
    }, [open, animal]);

    const selectedPen = useMemo(
        () => pens.find((pen) => String(pen.id) === String(form.penId)),
        [pens, form.penId]
    );

    const selectablePens = useMemo(
        () =>
            pens.filter((pen) => {
                const isCurrentPen = String(pen.id) === String(form.penId);
                const canReceive = pen.status === "Active";
                const allowedSpecies = String(pen.animalType || "").trim().toLowerCase();
                const speciesMatches =
                    !allowedSpecies ||
                    ["all", "all livestock", "any"].includes(allowedSpecies) ||
                    allowedSpecies === String(form.type || "").trim().toLowerCase();
                return (canReceive || isCurrentPen) && speciesMatches;
            }),
        [pens, form.penId, form.type]
    );

    if (!open) return null;

    const updateField = (event) => {
        const { name, value } = event.target;
        setForm((current) => {
            const next = { ...current, [name]: value };
            if (name === "penId") {
                const pen = pens.find((item) => String(item.id) === String(value));
                next.penLocation = pen?.name || "";
            }
            return next;
        });
    };

    const submit = async (event) => {
        event.preventDefault();
        const quantity = number(form.quantity);
        const male = number(form.maleQuantity);
        const female = number(form.femaleQuantity);
        const unknown = number(form.unknownSexQuantity);
        const healthy = number(form.healthyQuantity);
        const atRisk = number(form.atRiskQuantity);
        const sick = number(form.sickQuantity);
        const treatment = number(form.underTreatmentQuantity);
        const avgWeight = number(form.weight);
        const minWeight = number(form.minWeight);
        const maxWeight = number(form.maxWeight);

        if (!form.recordName.trim() || !form.breed.trim() || !form.dateOfBirth || !form.dateAcquired) {
            notify("Complete all required livestock fields.");
            return;
        }
        if (!Number.isInteger(quantity) || quantity < 1) {
            notify("Total quantity must be at least 1.");
            return;
        }
        if (male + female + unknown !== quantity) {
            notify("Male + Female + Unknown quantities must equal the total quantity.");
            return;
        }
        if (healthy + atRisk + sick + treatment !== quantity) {
            notify("Healthy + At Risk + Sick + Under Treatment must equal the total quantity.");
            return;
        }
        if (avgWeight <= 0 || minWeight <= 0 || maxWeight <= 0) {
            notify("Enter valid minimum, average, and maximum weights.");
            return;
        }
        if (minWeight > maxWeight || avgWeight < minWeight || avgWeight > maxWeight) {
            notify("Average weight must be inside the minimum and maximum weight range.");
            return;
        }
        if (!form.penId || !selectedPen) {
            notify("Select a pen. Use Manage Pens first if the pen is not listed.");
            return;
        }
        if (form.dateAcquired < form.dateOfBirth) {
            notify("Date acquired cannot be earlier than the birth/hatch date.");
            return;
        }

        setBusy(true);
        try {
            await onSave({
                recordType: "Batch",
                lifecycleStatus: form.lifecycleStatus,
                recordName: form.recordName.trim(),
                type: form.type,
                breed: form.breed.trim(),
                quantity,
                maleQuantity: male,
                femaleQuantity: female,
                unknownSexQuantity: unknown,
                sex: sexLabel(form, quantity),
                dateOfBirth: form.dateOfBirth,
                weight: avgWeight,
                minWeight,
                maxWeight,
                penId: Number(form.penId),
                penLocation: selectedPen.name,
                healthStatus: healthLabel(form, quantity),
                healthyQuantity: healthy,
                atRiskQuantity: atRisk,
                sickQuantity: sick,
                underTreatmentQuantity: treatment,
                growthStatus: form.growthStatus,
                productionPurpose: form.productionPurpose,
                lastCheckup: form.lastCheckup,
                healthNotes: form.healthNotes.trim(),
                vaccinationStatus: form.vaccinationStatus,
                nextVaccination: form.nextVaccination,
                feedingSchedule: {
                    times: form.feedTimes.trim(),
                    feedType: form.feedType.trim(),
                    dailyAmountKg: number(form.dailyFeedKg),
                    notes: form.feedingNotes.trim(),
                },
                dateAcquired: form.dateAcquired,
                acquiredFrom: form.acquiredFrom.trim(),
            });
        } finally {
            setBusy(false);
        }
    };

    const penPurposeHint = selectedPen
        ? `${selectedPen.purpose} • ${selectedPen.animalType || "All livestock"} • ${
              selectedPen.capacity
                  ? `${selectedPen.currentOccupancy}/${selectedPen.capacity} occupied`
                  : `${selectedPen.currentOccupancy} occupied`
          }`
        : "Choose a pen created in Pen Management.";

    const allHealthAffected =
        number(form.healthyQuantity) === 0 &&
        number(form.atRiskQuantity) + number(form.sickQuantity) + number(form.underTreatmentQuantity) === number(form.quantity);

    const preferredPurposes = (() => {
        if (number(form.sickQuantity) + number(form.underTreatmentQuantity) === number(form.quantity) && number(form.quantity) > 0) {
            return ["Isolation / Sick", "Recovery"];
        }
        if (allHealthAffected && number(form.atRiskQuantity) > 0) return ["Observation", "Isolation / Sick"];
        if (form.productionPurpose === "Laying / Egg Production") return ["Egg Production", "General"];
        if (form.productionPurpose === "Meat Production") return ["Meat Production / Finisher", "Growing", "General"];
        if (form.productionPurpose === "Breeding") return ["Breeding", "General"];
        if (form.productionPurpose === "Pregnancy / Maternity") return ["Pregnancy / Maternity", "Breeding", "General"];
        if (form.productionPurpose === "Market Ready") return ["Market Ready", "Meat Production / Finisher", "General"];
        if (form.growthStatus === "Newborn") return ["Brooding / Nursery", "General"];
        if (form.growthStatus === "Growing") return ["Growing", "General"];
        return ["General", form.productionPurpose];
    })();

    const penCompatibilityWarning =
        selectedPen && !preferredPurposes.includes(selectedPen.purpose)
            ? `This batch is usually better suited to: ${preferredPurposes.join(" or ")}.`
            : "";

    return (
        <div className="livestock-modal-overlay" onMouseDown={onClose}>
            <section className="add-livestock-modal aggregate-livestock-modal" onMouseDown={(e) => e.stopPropagation()}>
                <header className="livestock-modal-header">
                    <div>
                        <h2>{animal ? "Edit Livestock Batch" : "Add Livestock Batch"}</h2>
                        <p>
                            One batch represents one breed and one management group. Quantity may be 1 or more.
                        </p>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close">
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </header>

                <form className="add-livestock-form" onSubmit={submit}>
                    {!animal && (
                        <div className="aggregate-population-notice">
                            <span className="material-symbols-outlined">info</span>
                            <div>
                                <strong>Add Livestock increases the farm population.</strong>
                                <p>To reorganize animals already recorded in the system, use Transfer Pen or Split / Move Animals instead of adding another batch.</p>
                            </div>
                        </div>
                    )}
                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">pets</span>
                            <div>
                                <h3>Batch Information</h3>
                                <p>Keep different breeds in separate batches even when they share the same pen.</p>
                            </div>
                        </div>
                        <div className="livestock-form-grid">
                            <div className="livestock-form-group">
                                <label>Record Name <span>*</span></label>
                                <input name="recordName" value={form.recordName} onChange={updateField} placeholder="Example: Native Pig Growers" required />
                            </div>
                            <div className="livestock-form-group">
                                <label>Animal Type <span>*</span></label>
                                <select name="type" value={form.type} onChange={updateField}>
                                    {ANIMAL_TYPES.map((item) => <option key={item}>{item}</option>)}
                                </select>
                            </div>
                            <div className="livestock-form-group">
                                <label>Breed <span>*</span></label>
                                <input name="breed" value={form.breed} onChange={updateField} placeholder="Example: Philippine Native Pig" required />
                            </div>
                            <div className="livestock-form-group">
                                <label>Total Quantity <span>*</span></label>
                                <input name="quantity" type="number" min="1" step="1" value={form.quantity} onChange={updateField} required />
                            </div>
                            <div className="livestock-form-group">
                                <label>Birth / Hatch Date <span>*</span></label>
                                <input name="dateOfBirth" type="date" value={form.dateOfBirth} onChange={updateField} required />
                            </div>
                            <div className="livestock-form-group">
                                <label>Production Purpose</label>
                                <select name="productionPurpose" value={form.productionPurpose} onChange={updateField}>
                                    {!PRODUCTION_PURPOSES.includes(form.productionPurpose) && form.productionPurpose && (
                                        <option value={form.productionPurpose}>{form.productionPurpose}</option>
                                    )}
                                    {PRODUCTION_PURPOSES.map((item) => <option key={item}>{item}</option>)}
                                </select>
                            </div>
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">wc</span>
                            <div>
                                <h3>Sex Breakdown</h3>
                                <p>The three quantities must equal the batch total.</p>
                            </div>
                        </div>
                        <div className="aggregate-three-grid">
                            <div className="livestock-form-group"><label>Male</label><input name="maleQuantity" type="number" min="0" step="1" value={form.maleQuantity} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Female</label><input name="femaleQuantity" type="number" min="0" step="1" value={form.femaleQuantity} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Unknown / Unsexed</label><input name="unknownSexQuantity" type="number" min="0" step="1" value={form.unknownSexQuantity} onChange={updateField} /></div>
                        </div>
                        <div className={`aggregate-total-check ${number(form.maleQuantity) + number(form.femaleQuantity) + number(form.unknownSexQuantity) === number(form.quantity) ? "valid" : "invalid"}`}>
                            Sex total: {number(form.maleQuantity) + number(form.femaleQuantity) + number(form.unknownSexQuantity)} / {number(form.quantity)}
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">monitor_weight</span>
                            <div>
                                <h3>Weight and Growth</h3>
                                <p>Use the batch weight range and average weight per animal.</p>
                            </div>
                        </div>
                        <div className="aggregate-three-grid">
                            <div className="livestock-form-group"><label>Minimum Weight (kg) <span>*</span></label><input name="minWeight" type="number" min="0.01" step="0.01" value={form.minWeight} onChange={updateField} required /></div>
                            <div className="livestock-form-group"><label>Average Weight (kg) <span>*</span></label><input name="weight" type="number" min="0.01" step="0.01" value={form.weight} onChange={updateField} required /></div>
                            <div className="livestock-form-group"><label>Maximum Weight (kg) <span>*</span></label><input name="maxWeight" type="number" min="0.01" step="0.01" value={form.maxWeight} onChange={updateField} required /></div>
                        </div>
                        <div className="livestock-form-grid">
                            <div className="livestock-form-group">
                                <label>Growth Status</label>
                                <select name="growthStatus" value={form.growthStatus} onChange={updateField}>{GROWTH_STATUSES.map((item) => <option key={item}>{item}</option>)}</select>
                            </div>
                            <div className="livestock-form-group">
                                <label>Current Pen <span>*</span></label>
                                <select name="penId" value={form.penId} onChange={updateField} required>
                                    <option value="">Select a pen</option>
                                    {selectablePens.map((pen) => (
                                        <option key={pen.id} value={pen.id}>
                                            {pen.name} — {pen.purpose}{pen.status === "Full" ? " (Full - current pen)" : ""}
                                        </option>
                                    ))}
                                </select>
                                <small className="livestock-field-help">{loadError || penPurposeHint}</small>
                                {penCompatibilityWarning && (
                                    <small className="aggregate-pen-warning">{penCompatibilityWarning}</small>
                                )}
                            </div>
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">health_and_safety</span>
                            <div>
                                <h3>Health Breakdown</h3>
                                <p>Keep a few sick birds in the same batch by recording the count. Split them only when physically isolated.</p>
                            </div>
                        </div>
                        <div className="aggregate-four-grid">
                            <div className="livestock-form-group"><label>Healthy</label><input name="healthyQuantity" type="number" min="0" step="1" value={form.healthyQuantity} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>At Risk</label><input name="atRiskQuantity" type="number" min="0" step="1" value={form.atRiskQuantity} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Sick</label><input name="sickQuantity" type="number" min="0" step="1" value={form.sickQuantity} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Under Treatment</label><input name="underTreatmentQuantity" type="number" min="0" step="1" value={form.underTreatmentQuantity} onChange={updateField} /></div>
                        </div>
                        <div className={`aggregate-total-check ${number(form.healthyQuantity) + number(form.atRiskQuantity) + number(form.sickQuantity) + number(form.underTreatmentQuantity) === number(form.quantity) ? "valid" : "invalid"}`}>
                            Health total: {number(form.healthyQuantity) + number(form.atRiskQuantity) + number(form.sickQuantity) + number(form.underTreatmentQuantity)} / {number(form.quantity)}
                        </div>
                        <div className="livestock-form-grid aggregate-top-gap">
                            <div className="livestock-form-group"><label>Last Checkup</label><input name="lastCheckup" type="date" value={form.lastCheckup} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Vaccination Status</label><select name="vaccinationStatus" value={form.vaccinationStatus} onChange={updateField}>{VACCINATION_STATUSES.map((item) => <option key={item}>{item}</option>)}</select></div>
                            <div className="livestock-form-group"><label>Next Vaccination</label><input name="nextVaccination" type="date" value={form.nextVaccination} onChange={updateField} /></div>
                            <div className="livestock-form-group full-width"><label>Health Notes</label><textarea name="healthNotes" rows="3" value={form.healthNotes} onChange={updateField} placeholder="Batch health observations and treatment notes" /></div>
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">restaurant</span>
                            <div><h3>Feeding and Acquisition</h3><p>Daily feed is recorded per animal so total batch consumption can be calculated.</p></div>
                        </div>
                        <div className="livestock-form-grid">
                            <div className="livestock-form-group"><label>Feeding Times</label><input name="feedTimes" value={form.feedTimes} onChange={updateField} placeholder="Example: 2× daily" /></div>
                            <div className="livestock-form-group"><label>Feed Type</label><input name="feedType" value={form.feedType} onChange={updateField} placeholder="Example: Hog Grower Feed" /></div>
                            <div className="livestock-form-group"><label>Feed per Animal / Day (kg)</label><input name="dailyFeedKg" type="number" min="0" step="0.01" value={form.dailyFeedKg} onChange={updateField} /></div>
                            <div className="livestock-form-group"><label>Calculated Batch Feed</label><input value={`${(number(form.dailyFeedKg) * number(form.quantity)).toFixed(2)} kg/day`} readOnly /></div>
                            <div className="livestock-form-group"><label>Date Acquired <span>*</span></label><input name="dateAcquired" type="date" value={form.dateAcquired} onChange={updateField} required /></div>
                            <div className="livestock-form-group"><label>Acquired From</label><input name="acquiredFrom" value={form.acquiredFrom} onChange={updateField} /></div>
                            <div className="livestock-form-group full-width"><label>Feeding Notes</label><textarea name="feedingNotes" rows="3" value={form.feedingNotes} onChange={updateField} /></div>
                        </div>
                    </section>

                    <footer className="aggregate-form-footer">
                        <button type="button" className="aggregate-secondary-button" onClick={onClose}>Cancel</button>
                        <button type="submit" className="aggregate-primary-button" disabled={busy}>{busy ? "Saving..." : animal ? "Save Changes" : "Add Livestock"}</button>
                    </footer>
                </form>
            </section>
        </div>
    );
}
