"use client";

import { notify } from "../../context/NotificationContext.jsx";

import { farmDateKey } from "../../utils/farmCalendar.js";
import { useEffect, useMemo, useRef, useState } from "react";
import { productionSalesService } from "../../services/productionSalesService.js";
import { livestockService } from "../../services/livestockService.js";
import { clearStableIdempotencyKey, stableIdempotencyKey } from "../../services/idempotencyKey.js";
import "./LivestockReproductionProduction.css";

function todayValue() {
    return farmDateKey();
}

function n(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
}

function formatDate(value) {
    if (!value) return "—";
    const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
    return new Date(year, month - 1, day).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
    });
}

function speciesGroup(type = "") {
    const value = String(type).toLowerCase();
    if (["chicken", "duck", "bird", "poultry"].some((term) => value.includes(term))) return "bird";
    if (value.includes("pig") || value.includes("swine")) return "pig";
    if (value.includes("goat") || value.includes("cattle") || value.includes("cow")) return "ruminant";
    return "other";
}

function isBreedingPen(animal, pens) {
    const pen = pens.find((row) => Number(row.id) === Number(animal?.penId));
    return String(pen?.purpose || "").toLowerCase().includes("breeding");
}

function normalizeReproduction(row = {}) {
    return {
        id: row.id,
        recordType: row.recordType ?? row.record_type ?? "",
        eventDate: row.eventDate ?? row.event_date ?? "",
        breederMaleQuantity: n(row.breederMaleQuantity ?? row.breeder_male_quantity),
        breederFemaleQuantity: n(row.breederFemaleQuantity ?? row.breeder_female_quantity),
        confirmedPregnantQuantity: n(row.confirmedPregnantQuantity ?? row.confirmed_pregnant_quantity),
        eggsSet: n(row.eggsSet ?? row.eggs_set),
        fertileEggs: n(row.fertileEggs ?? row.fertile_eggs),
        incubationMethod: row.incubationMethod ?? row.incubation_method ?? "",
        reproductiveStatus: row.reproductiveStatus ?? row.reproductive_status ?? "",
        expectedDate: row.expectedDate ?? row.expected_date ?? "",
        actualDate: row.actualDate ?? row.actual_date ?? "",
        offspringCount: n(row.offspringCount ?? row.offspring_count),
        aliveOffspring: n(row.aliveOffspring ?? row.alive_offspring),
        lossCount: n(row.lossCount ?? row.loss_count),
        offspringRecordName: row.offspringRecordName ?? row.offspring_record_name ?? "",
        notes: row.notes ?? "",
    };
}

function normalizeProduction(row = {}) {
    return {
        id: row.id,
        outputType: row.outputType ?? row.output_type ?? "",
        recordDate: row.recordDate ?? row.record_date ?? "",
        sourceActiveQuantity: row.sourceActiveQuantity ?? row.source_active_quantity ?? null,
        grossQuantity: n(row.grossQuantity ?? row.gross_quantity ?? row.quantity),
        lossQuantity: n(row.lossQuantity ?? row.loss_quantity),
        quantity: n(row.quantity),
        availableQuantity: n(row.availableQuantity ?? row.available_quantity),
        soldQuantity: n(row.soldQuantity ?? row.sold_quantity),
        unit: row.unit ?? "",
        layingRatePercent: row.layingRatePercent ?? row.laying_rate_percent ?? null,
        qualityGrade: row.qualityGrade ?? row.quality_grade ?? "",
        destination: row.destination ?? "",
        notes: row.notes ?? "",
    };
}

function emptyReproduction(animal) {
    const group = speciesGroup(animal?.type);
    return {
        recordType: "Breeding",
        eventDate: todayValue(),
        breederMaleQuantity: "1",
        breederFemaleQuantity: group === "bird" ? String(Math.max(1, n(animal?.femaleQuantity))) : "1",
        confirmedPregnantQuantity: "0",
        eggsSet: "0",
        fertileEggs: "0",
        incubationMethod: "Incubator",
        reproductiveStatus: "Recorded",
        partnerReference: "",
        breedingMethod: "Natural",
        expectedDate: "",
        actualDate: "",
        offspringCount: "0",
        aliveOffspring: "0",
        maleOffspring: "0",
        femaleOffspring: "0",
        lossCount: "0",
        createOffspringRecord: false,
        offspringRecordName: "",
        offspringAverageWeightKg: "",
        offspringPenId: "",
        notes: "",
    };
}

function eligibleOffspringPens(pens, animal, count) {
    const group = speciesGroup(animal?.type);
    return pens.filter((pen) => {
        const species = String(pen.animalType || "").toLowerCase();
        const compatible = !species || species === "all livestock" || species === String(animal?.type || "").toLowerCase();
        const available = pen.capacity == null || n(pen.currentOccupancy) + Math.max(1, n(count)) <= n(pen.capacity);
        const active = !["Inactive", "Closed", "Maintenance", "Full"].includes(pen.status);
        const purpose = String(pen.purpose || "").toLowerCase();
        const purposeMatches = group === "bird"
            ? ["brooder", "nursery"].some((token) => purpose.includes(token))
            : group === "pig"
                ? ["nursing", "farrowing", "nursery"].some((token) => purpose.includes(token))
                : group === "ruminant"
                    ? ["nursing", "nursery", "maternity"].some((token) => purpose.includes(token))
                    : true;
        return compatible && available && active && purposeMatches;
    });
}

export function LivestockReproductionPanel({ animal, onSave }) {
    const requestRef = useRef(null);
    const inFlightRef = useRef(false);
    const [records, setRecords] = useState([]);
    const [pens, setPens] = useState([]);
    const [showForm, setShowForm] = useState(false);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState(() => emptyReproduction(animal));

    const group = speciesGroup(animal?.type);
    const isBird = group === "bird";
    const breedingEligible = isBreedingPen(animal, pens) && n(animal?.maleQuantity) > 0 && n(animal?.femaleQuantity) > 0;
    const recordTypes = isBird ? ["Breeding", "Egg Setting", "Hatch"] : ["Breeding", "Pregnancy Check", "Birth"];
    const birthOrHatch = ["Birth", "Hatch"].includes(form.recordType);

    const load = async () => {
        if (!animal?.id) return;
        try {
            const [rows, penRows] = await Promise.all([
                productionSalesService.getReproduction({ livestock_id: animal.id }),
                livestockService.getPens(),
            ]);
            setRecords((Array.isArray(rows) ? rows : rows?.data || []).map(normalizeReproduction));
            setPens(penRows);
        } catch (error) {
            console.error("Failed to load reproduction records:", error);
        }
    };

    useEffect(() => {
        setForm(emptyReproduction(animal));
        setShowForm(false);
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [animal?.id]);

    const destinationPens = useMemo(
        () => eligibleOffspringPens(pens, animal, form.aliveOffspring),
        [pens, animal, form.aliveOffspring]
    );

    const change = (event) => {
        const { name, value, type, checked } = event.target;
        setForm((current) => ({ ...current, [name]: type === "checkbox" ? checked : value }));
    };

    const submit = async (event) => {
        event.preventDefault();
        if (inFlightRef.current) return;
        if (["Breeding", "Egg Setting"].includes(form.recordType) && !breedingEligible) {
            notify("Breeding and hatching-egg setting require an eligible male/female batch inside a Breeding pen.");
            return;
        }
        if (n(form.breederMaleQuantity) > n(animal.maleQuantity) || n(form.breederFemaleQuantity) > n(animal.femaleQuantity)) {
            notify("Breeder male/female counts cannot exceed the available batch counts.");
            return;
        }
        if (birthOrHatch && form.createOffspringRecord && !form.offspringPenId) {
            notify("Choose the offspring destination pen.");
            return;
        }
        inFlightRef.current = true;
        setSaving(true);
        try {
            const payload = {
                livestock_id: animal.id,
                record_type: form.recordType,
                event_date: form.eventDate,
                partner_reference: form.partnerReference.trim() || null,
                breeding_method: form.breedingMethod || null,
                breeder_male_quantity: n(form.breederMaleQuantity),
                breeder_female_quantity: n(form.breederFemaleQuantity),
                confirmed_pregnant_quantity: n(form.confirmedPregnantQuantity),
                eggs_set: n(form.eggsSet),
                fertile_eggs: n(form.fertileEggs),
                incubation_method: isBird ? form.incubationMethod : null,
                reproductive_status: form.reproductiveStatus || "Recorded",
                expected_date: form.expectedDate || null,
                actual_date: form.actualDate || null,
                offspring_count: n(form.offspringCount),
                alive_offspring: n(form.aliveOffspring),
                male_offspring: form.maleOffspring === "" ? null : n(form.maleOffspring),
                female_offspring: form.femaleOffspring === "" ? null : n(form.femaleOffspring),
                loss_count: n(form.lossCount),
                notes: form.notes.trim() || null,
                create_offspring_record: birthOrHatch && Boolean(form.createOffspringRecord),
                offspring_record_name: form.offspringRecordName.trim() || null,
                offspring_average_weight_kg: form.offspringAverageWeightKg ? n(form.offspringAverageWeightKg) : null,
                offspring_pen_id: form.offspringPenId ? n(form.offspringPenId) : null,
            };
            const idempotencyKey = stableIdempotencyKey(requestRef, payload, "livestock-reproduction");
            const saved = await productionSalesService.createReproduction(payload, { idempotencyKey });
            await onSave?.(saved);
            await load();
            clearStableIdempotencyKey(requestRef);
            setForm(emptyReproduction(animal));
            setShowForm(false);
            window.dispatchEvent(new CustomEvent("joross:livestock-updated"));
            notify(birthOrHatch && payload.create_offspring_record ? "Reproduction saved and offspring batch created." : "Reproduction record saved.");
        } catch (error) {
            console.error("Failed to save reproduction:", error);
            notify(error?.message || "Unable to save reproduction record.");
        } finally {
            inFlightRef.current = false;
            setSaving(false);
        }
    };

    return (
        <section className="livestock-rp-section">
            <div className="livestock-rp-heading">
                <div><h3>Reproduction</h3><p>{isBird ? "Breeder flock → hatching eggs → incubation → hatch → offspring batch." : "Breeding → pregnancy check → birth → separate offspring batch."}</p></div>
                <button type="button" onClick={() => setShowForm((value) => !value)}><span className="material-symbols-outlined">add</span>Record Reproduction</button>
            </div>

            <div className={`livestock-rp-eligibility ${breedingEligible ? "eligible" : "blocked"}`}>
                <span className="material-symbols-outlined">{breedingEligible ? "check_circle" : "info"}</span>
                <div><strong>{breedingEligible ? "Breeding eligible" : "Breeding currently blocked"}</strong><p>Current pen: {animal.penLocation} · Male {animal.maleQuantity} · Female {animal.femaleQuantity}. Breeding/Egg Setting requires a Breeding pen and both sexes.</p></div>
            </div>

            {showForm && (
                <form className="livestock-rp-form" onSubmit={submit}>
                    <div className="livestock-rp-grid">
                        <label>Event Type<select name="recordType" value={form.recordType} onChange={change}>{recordTypes.map((type) => <option key={type}>{type}</option>)}</select></label>
                        <label>Event Date<input name="eventDate" type="date" max={todayValue()} value={form.eventDate} onChange={change} required /></label>

                        {["Breeding", "Egg Setting"].includes(form.recordType) && <>
                            <label>Breeder Males<input name="breederMaleQuantity" type="number" min="1" max={animal.maleQuantity} value={form.breederMaleQuantity} onChange={change} required /></label>
                            <label>Breeder Females<input name="breederFemaleQuantity" type="number" min="1" max={animal.femaleQuantity} value={form.breederFemaleQuantity} onChange={change} required /></label>
                            <label>Breeding Method<select name="breedingMethod" value={form.breedingMethod} onChange={change}><option>Natural</option><option>Artificial Insemination</option></select></label>
                        </>}

                        {!isBird && form.recordType === "Pregnancy Check" && <>
                            <label>Females Checked / Bred<input name="breederFemaleQuantity" type="number" min="1" max={animal.femaleQuantity} value={form.breederFemaleQuantity} onChange={change} /></label>
                            <label>Confirmed Pregnant<input name="confirmedPregnantQuantity" type="number" min="0" max={form.breederFemaleQuantity || animal.femaleQuantity} value={form.confirmedPregnantQuantity} onChange={change} /></label>
                            <label>Expected Birth / Farrowing<input name="expectedDate" type="date" value={form.expectedDate} onChange={change} /></label>
                        </>}

                        {isBird && ["Egg Setting", "Hatch"].includes(form.recordType) && <>
                            <label>Eggs Set for Hatching<input name="eggsSet" type="number" min="1" value={form.eggsSet} onChange={change} required /></label>
                            <label>Fertile Eggs<input name="fertileEggs" type="number" min="0" max={form.eggsSet || undefined} value={form.fertileEggs} onChange={change} /></label>
                            <label>Incubation Method<select name="incubationMethod" value={form.incubationMethod} onChange={change}><option>Incubator</option><option>Natural</option></select></label>
                            <label>Expected Hatch Date<input name="expectedDate" type="date" value={form.expectedDate} onChange={change} /></label>
                        </>}

                        {birthOrHatch && <>
                            <label>{isBird ? "Total Hatched" : "Total Offspring Born"}<input name="offspringCount" type="number" min="0" value={form.offspringCount} onChange={change} required /></label>
                            <label>Alive Offspring<input name="aliveOffspring" type="number" min="0" max={form.offspringCount || undefined} value={form.aliveOffspring} onChange={change} required /></label>
                            <label>Male Offspring<input name="maleOffspring" type="number" min="0" value={form.maleOffspring} onChange={change} /></label>
                            <label>Female Offspring<input name="femaleOffspring" type="number" min="0" value={form.femaleOffspring} onChange={change} /></label>
                            <label>Loss / Stillborn / Unhatched<input name="lossCount" type="number" min="0" value={form.lossCount} onChange={change} /></label>
                            <label>Actual {isBird ? "Hatch" : "Birth"} Date<input name="actualDate" type="date" max={todayValue()} value={form.actualDate} onChange={change} /></label>
                        </>}
                    </div>

                    {birthOrHatch && <div className="livestock-rp-offspring-box">
                        <label className="livestock-rp-check"><input name="createOffspringRecord" type="checkbox" checked={form.createOffspringRecord} onChange={change} />Create a separate offspring batch after this {isBird ? "hatch" : "birth"}</label>
                        {form.createOffspringRecord && <div className="livestock-rp-grid">
                            <label>Offspring Batch Name<input name="offspringRecordName" value={form.offspringRecordName} onChange={change} placeholder={`${animal.recordName} Offspring`} /></label>
                            <label>Average Offspring Weight (kg)<input name="offspringAverageWeightKg" type="number" min="0.01" step="0.01" value={form.offspringAverageWeightKg} onChange={change} required /></label>
                            <label>Destination Pen<select name="offspringPenId" value={form.offspringPenId} onChange={change} required><option value="">Select offspring-appropriate pen</option>{destinationPens.map((pen) => <option key={pen.id} value={pen.id}>{pen.name} — {pen.purpose} — {pen.capacity ? `${pen.currentOccupancy}/${pen.capacity}` : `${pen.currentOccupancy} occupied`}</option>)}</select><small>{isBird ? "New chicks/ducklings must start in a Brooder/Nursery pen." : group === "pig" ? "New piglets must start in a Nursing/Farrowing/Nursery pen." : "New offspring must start in a Nursing/Nursery/Maternity pen."}</small></label>
                        </div>}
                    </div>}

                    <label className="livestock-rp-full">Notes<textarea name="notes" rows="3" value={form.notes} onChange={change} /></label>
                    <footer className="livestock-rp-actions"><button type="button" className="secondary" onClick={() => setShowForm(false)}>Cancel</button><button type="submit" disabled={saving}>{saving ? "Saving..." : "Save Reproduction"}</button></footer>
                </form>
            )}

            <div className="livestock-rp-records">
                {records.length ? records.map((record) => <article key={record.id}><div><strong>{record.recordType}</strong><small>{formatDate(record.eventDate)} · {record.reproductiveStatus || "Recorded"}</small></div><p>{record.recordType === "Egg Setting" ? `${record.eggsSet} eggs set · ${record.fertileEggs} fertile` : ["Birth", "Hatch"].includes(record.recordType) ? `${record.aliveOffspring}/${record.offspringCount} alive${record.offspringRecordName ? ` · New batch: ${record.offspringRecordName}` : ""}` : `${record.breederFemaleQuantity} female(s) · ${record.breederMaleQuantity} male(s)`}</p></article>) : <div className="livestock-rp-empty">No reproduction records yet.</div>}
            </div>
        </section>
    );
}

function productionOptions(animal) {
    const group = speciesGroup(animal?.type);
    const purpose = String(animal?.productionPurpose || "General").toLowerCase();
    const options = [];
    if (group === "bird") {
        if (purpose.includes("egg") || purpose.includes("laying")) options.push("Eggs");
    } else if (group === "ruminant") {
        if (purpose.includes("milk") || purpose.includes("dual")) options.push("Milk");
    }
    return options;
}

function emptyProduction(animal) {
    const options = productionOptions(animal);
    return {
        mode: options[0] || "",
        recordDate: todayValue(),
        sourceActiveQuantity: "",
        grossQuantity: "",
        lossQuantity: "0",
        qualityGrade: "",
        destination: "Available for sale",
        animalsProcessed: "",
        maleQuantity: "0",
        femaleQuantity: "0",
        unknownQuantity: "0",
        liveWeightKg: "",
        meatOutputKg: "",
        notes: "",
    };
}

export function LivestockProductionPanel({ animal, onSave }) {
    const requestRef = useRef(null);
    const inFlightRef = useRef(false);
    const [records, setRecords] = useState([]);
    const [showForm, setShowForm] = useState(false);
    const [saving, setSaving] = useState(false);
    const [form, setForm] = useState(() => emptyProduction(animal));
    const options = useMemo(() => productionOptions(animal), [animal]);

    const load = async () => {
        if (!animal?.id) return;
        try {
            const rows = await productionSalesService.getProduction({ livestock_id: animal.id });
            setRecords((Array.isArray(rows) ? rows : rows?.data || []).map(normalizeProduction));
        } catch (error) {
            console.error("Failed to load production records:", error);
        }
    };

    useEffect(() => {
        setForm(emptyProduction(animal));
        setShowForm(false);
        load();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [animal?.id]);

    const change = (event) => {
        const { name, value } = event.target;
        setForm((current) => ({ ...current, [name]: value }));
    };

    const submit = async (event) => {
        event.preventDefault();
        if (inFlightRef.current) return;
        inFlightRef.current = true;
        setSaving(true);
        try {
            let saved;
            if (form.mode === "Meat Processing") {
                const processed = n(form.animalsProcessed);
                if (processed < 1 || processed > n(animal.quantity)) {
                    notify(`Animals processed must be between 1 and ${animal.quantity}.`);
                    return;
                }
                const sexTotal = n(form.maleQuantity) + n(form.femaleQuantity) + n(form.unknownQuantity);
                if (sexTotal !== 0 && sexTotal !== processed) {
                    notify("Male + Female + Unknown must equal Animals Processed.");
                    return;
                }
                const payload = {
                    livestock_id: animal.id,
                    processing_date: form.recordDate,
                    animals_processed: processed,
                    male_quantity: n(form.maleQuantity),
                    female_quantity: n(form.femaleQuantity),
                    unknown_quantity: n(form.unknownQuantity),
                    live_weight_kg: form.liveWeightKg ? n(form.liveWeightKg) : null,
                    meat_output_kg: n(form.meatOutputKg),
                    quality_grade: form.qualityGrade.trim() || null,
                    destination: form.destination.trim() || "Available for sale",
                    notes: form.notes.trim() || null,
                };
                const idempotencyKey = stableIdempotencyKey(requestRef, payload, "livestock-processing");
                saved = await productionSalesService.createProcessing(payload, { idempotencyKey });
            } else {
                const gross = n(form.grossQuantity);
                const loss = n(form.lossQuantity);
                const usable = gross - loss;
                if (gross <= 0 || usable <= 0 || loss > gross) {
                    notify("Gross output must be greater than losses/rejected output.");
                    return;
                }
                const active = n(form.sourceActiveQuantity);
                if (active < 1 || active > n(animal.femaleQuantity || animal.quantity)) {
                    notify(`Active producing animals must be between 1 and ${animal.femaleQuantity || animal.quantity}.`);
                    return;
                }
                const payload = {
                    livestock_id: animal.id,
                    output_type: form.mode,
                    record_date: form.recordDate,
                    source_active_quantity: active,
                    gross_quantity: gross,
                    loss_quantity: loss,
                    quantity: usable,
                    unit: form.mode === "Eggs" ? "pcs" : "L",
                    quality_grade: form.qualityGrade.trim() || null,
                    destination: form.destination.trim() || "Available for sale",
                    track_sale_inventory: true,
                    notes: form.notes.trim() || null,
                };
                const idempotencyKey = stableIdempotencyKey(requestRef, payload, "production-output");
                saved = await productionSalesService.createProduction(payload, { idempotencyKey });
            }
            await onSave?.(saved);
            await load();
            clearStableIdempotencyKey(requestRef);
            setForm(emptyProduction(animal));
            setShowForm(false);
            window.dispatchEvent(new CustomEvent("joross:production-sales-updated"));
            window.dispatchEvent(new CustomEvent("joross:livestock-updated"));
            notify("Production saved. It is now available in Production & Sales.");
        } catch (error) {
            console.error("Failed to save production:", error);
            notify(error?.message || "Unable to save production record.");
        } finally {
            inFlightRef.current = false;
            setSaving(false);
        }
    };

    const usable = Math.max(0, n(form.grossQuantity) - n(form.lossQuantity));

    return (
        <section className="livestock-rp-section">
            <div className="livestock-rp-heading">
                <div><h3>Production</h3><p>Egg and milk outputs use the shared stock ledger. Meat is created only from the Processing tab in Production &amp; Sales so live head count and meat stock change together.</p></div>
                {options.length ? <button type="button" onClick={() => setShowForm((value) => !value)}><span className="material-symbols-outlined">add_chart</span>Record Production</button> : String(animal?.productionPurpose || "").toLowerCase().includes("meat") ? <button type="button" onClick={() => { window.location.href = "/production-sales"; }}><span className="material-symbols-outlined">manufacturing</span>Open Processing</button> : null}
            </div>

            {showForm && <form className="livestock-rp-form" onSubmit={submit}>
                <div className="livestock-rp-grid">
                    <label>Production Type<select name="mode" value={form.mode} onChange={change}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>
                    <label>Date<input name="recordDate" type="date" max={todayValue()} value={form.recordDate} onChange={change} required /></label>
                    {form.mode !== "Meat Processing" ? <>
                        <label>{form.mode === "Eggs" ? "Active Laying Females" : "Animals Milked"}<input name="sourceActiveQuantity" type="number" min="1" max={animal.femaleQuantity || animal.quantity} value={form.sourceActiveQuantity} onChange={change} required /></label>
                        <label>{form.mode === "Eggs" ? "Eggs Collected" : "Gross Milk Produced"}<input name="grossQuantity" type="number" min="0.01" step={form.mode === "Eggs" ? "1" : "0.01"} value={form.grossQuantity} onChange={change} required /></label>
                        <label>{form.mode === "Eggs" ? "Damaged / Rejected Eggs" : "Rejected / Spoiled Milk"}<input name="lossQuantity" type="number" min="0" step={form.mode === "Eggs" ? "1" : "0.01"} value={form.lossQuantity} onChange={change} /></label>
                        <label>Usable / Saleable Output<input value={`${usable} ${form.mode === "Eggs" ? "pcs" : "L"}`} readOnly /></label>
                    </> : <>
                        <label>Animals Processed<input name="animalsProcessed" type="number" min="1" max={animal.quantity} value={form.animalsProcessed} onChange={change} required /></label>
                        <label>Male Processed<input name="maleQuantity" type="number" min="0" max={animal.maleQuantity} value={form.maleQuantity} onChange={change} /></label>
                        <label>Female Processed<input name="femaleQuantity" type="number" min="0" max={animal.femaleQuantity} value={form.femaleQuantity} onChange={change} /></label>
                        <label>Unknown Sex<input name="unknownQuantity" type="number" min="0" max={animal.unknownSexQuantity} value={form.unknownQuantity} onChange={change} /></label>
                        <label>Total Live Weight (kg)<input name="liveWeightKg" type="number" min="0.01" step="0.01" value={form.liveWeightKg} onChange={change} /></label>
                        <label>Meat Output (kg)<input name="meatOutputKg" type="number" min="0.01" step="0.01" value={form.meatOutputKg} onChange={change} required /></label>
                    </>}
                    <label>Quality / Grade<input name="qualityGrade" value={form.qualityGrade} onChange={change} /></label>
                    <label>Destination<select name="destination" value={form.destination} onChange={change}><option>Available for sale</option><option>Farm Use</option><option>Reserved</option></select></label>
                </div>
                <label className="livestock-rp-full">Notes<textarea name="notes" rows="3" value={form.notes} onChange={change} /></label>
                <footer className="livestock-rp-actions"><button type="button" className="secondary" onClick={() => setShowForm(false)}>Cancel</button><button type="submit" disabled={saving}>{saving ? "Saving..." : "Save Production"}</button></footer>
            </form>}

            <div className="livestock-rp-records">
                {records.length ? records.map((record) => <article key={record.id}><div><strong>{record.outputType}</strong><small>{formatDate(record.recordDate)} · {record.quantity} {record.unit} usable</small></div><p>{record.grossQuantity !== record.quantity ? `${record.grossQuantity} gross · ${record.lossQuantity} rejected · ` : ""}{record.availableQuantity} {record.unit} available{record.layingRatePercent != null ? ` · ${Number(record.layingRatePercent).toFixed(1)}% laying rate` : ""}</p></article>) : <div className="livestock-rp-empty">No production records yet.</div>}
            </div>
        </section>
    );
}
