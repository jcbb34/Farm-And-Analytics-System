"use client";

import { HistoryDateRange, useHistoryRange, MonitoringScheduleFields, scheduleForm } from "../Monitoring/Monitoring.jsx";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useCallback,
    useEffect,
    useState,
} from "react";

import {
    LivestockProductionPanel,
    LivestockReproductionPanel,
} from "../LivestockReproductionProduction/LivestockReproductionProduction.jsx";
import ResourceUsagePanel from "../ResourceUsagePanel/ResourceUsagePanel.jsx";
import { inventoryService } from "../../services/inventoryService.js";
import { livestockService } from "../../services/livestockService.js";
import { workforceService } from "../../services/workforceService.js";

import "./LivestockModals.css";

const animalTypes = [
    "Pig",
    "Cattle",
    "Goat",
    "Chicken",
    "Duck",
];

const healthStatuses = [
    "Healthy",
    "Mixed",
    "Under Treatment",
    "At Risk",
    "Sick",
];

const growthStatuses = [
    "Newborn",
    "Brooding",
    "Weaned",
    "Growing",
    "Finisher",
    "Pre-Laying",
    "Laying",
    "Ready for Market",
    "Mature",
    "Breeding",
    "Production",
];

const vaccinationStatuses = [
    "Not Vaccinated",
    "Scheduled",
    "Due",
    "Due Soon",
    "Up to Date",
];

const feedingFrequencies = [
    { value: "Once Daily", count: 1 },
    { value: "Twice Daily", count: 2 },
    { value: "Three Times Daily", count: 3 },
];

const feedingPeriods = ["Morning", "Afternoon", "Evening"];

const productionPurposes = {
    Pig: ["Breeding", "Meat", "Growing", "General"],
    Cattle: ["Breeding", "Milk", "Meat", "Dual Purpose", "General"],
    Goat: ["Breeding", "Milk", "Meat", "Dual Purpose", "General"],
    Chicken: ["Breeding", "Egg Production", "Meat", "Dual Purpose", "General"],
    Duck: ["Breeding", "Egg Production", "Meat", "Dual Purpose", "General"],
};

function feedingCount(frequency) {
    return feedingFrequencies.find((item) => item.value === frequency)?.count || 1;
}

function parseFeedingSchedule(value = "") {
    const text = String(value || "");
    const lower = text.toLowerCase();
    const periods = feedingPeriods.filter((period) => lower.includes(period.toLowerCase()));
    let frequency = "Once Daily";
    if (lower.includes("twice") || periods.length === 2) frequency = "Twice Daily";
    if (lower.includes("three") || periods.length >= 3) frequency = "Three Times Daily";
    return { frequency, periods: periods.length ? periods : ["Morning"] };
}

function serializeFeedingSchedule(frequency, periods) {
    return `${frequency} | ${(periods || []).join(", ")}`;
}

function isFeedItem(item) {
    const category = String(item?.category || "").trim().toLowerCase();
    const name = String(item?.name || "").trim().toLowerCase();
    const unit = String(item?.unit || "").trim().toLowerCase();
    const today = getTodayDate();
    return !item?.isArchived && Number(item?.quantity || 0) > 0 &&
        (category.includes("feed") || name.includes("feed")) &&
        ["kg", "kilogram", "kilograms"].includes(unit) &&
        (!item?.expirationDate || item.expirationDate >= today);
}

function isVaccineItem(item) {
    const category = String(item?.category || "").trim().toLowerCase();
    return !item?.isArchived && Number(item?.quantity || 0) > 0 &&
        ["vaccine", "vaccines", "vaccination"].includes(category) &&
        (!item?.expirationDate || item.expirationDate >= getTodayDate());
}

function getTodayDate() {
    const date = new Date();

    const year = date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        date.getDate()
    ).padStart(2, "0");

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

function getClassName(value = "") {
    return value
        .toLowerCase()
        .replaceAll(" ", "-");
}

function createEmptyLivestockForm() {
    return {
        ...scheduleForm(),
        recordType: "Batch",
        lifecycleStatus: "Active",
        recordName: "",
        type: "Pig",
        breed: "",
        quantity: "1",
        sex: "Mixed",
        maleQuantity: "0",
        femaleQuantity: "0",
        unknownSexQuantity: "1",
        productionPurpose: "General",

        dateOfBirth: "",
        ageIsEstimated: false,
        estimatedAgeDays: "",
        estimatedAgeAsOfDate: "",
        estimatedAgeConfidence: "",
        estimatedAgeSource: "",
        acquisitionStage: "Growing",
        acquisitionVaccinationHistory: "",
        acquisitionTreatmentHistory: "",
        feedingPlanName: "",
        assignedEmployeeId: "",
        careTemplateId: "",
        futureCareTaskAction: "",
        weight: "",
        minWeight: "",
        maxWeight: "",
        penId: "",
        penLocation: "",

        healthStatus: "Healthy",
        healthyQuantity: "1",
        atRiskQuantity: "0",
        sickQuantity: "0",
        underTreatmentQuantity: "0",
        growthStatus: "Growing",
        lastCheckup: getTodayDate(),
        healthNotes: "",

        vaccinationStatus:
            "Not Vaccinated",

        nextVaccination: "",

        feedInventoryItemId: "",
        feedingFrequency: "Once Daily",
        feedingPeriods: ["Morning"],
        feedTimes: "",
        feedType: "",
        dailyFeedKg: "",
        feedingNotes: "",

        dateAcquired: getTodayDate(),
        acquiredFrom: "",
    };
}

function createLivestockFormFromAnimal(
    animal
) {
    if (!animal) {
        return createEmptyLivestockForm();
    }

    return {
        ...scheduleForm(animal),
        recordType:
            animal.recordType || "Batch",

        lifecycleStatus:
            animal.lifecycleStatus || "Active",

        recordName:
            animal.recordName || "",

        type:
            animal.type || "Pig",

        breed:
            animal.breed || "",

        quantity: String(
            animal.quantity ?? 1
        ),

        sex:
            animal.sex || "Mixed",
        maleQuantity: String(animal.maleQuantity ?? 0),
        femaleQuantity: String(animal.femaleQuantity ?? 0),
        unknownSexQuantity: String(animal.unknownSexQuantity ?? 0),
        productionPurpose: animal.productionPurpose || "General",

        dateOfBirth:
            animal.dateOfBirth || "",
        ageIsEstimated: Boolean(animal.ageIsEstimated),
        estimatedAgeDays: animal.estimatedAgeDays == null ? "" : String(animal.estimatedAgeDays),
        estimatedAgeAsOfDate: animal.estimatedAgeAsOfDate || "",
        estimatedAgeConfidence: animal.estimatedAgeConfidence || "",
        estimatedAgeSource: animal.estimatedAgeSource || "",
        acquisitionStage: animal.acquisitionStage || animal.growthStatus || "Growing",
        acquisitionVaccinationHistory: animal.acquisitionVaccinationHistory || "",
        acquisitionTreatmentHistory: animal.acquisitionTreatmentHistory || "",
        feedingPlanName: animal.feedingPlanName || "",
        assignedEmployeeId: animal.assignedEmployeeId == null ? "" : String(animal.assignedEmployeeId),
        careTemplateId: animal.careTemplateId == null ? "" : String(animal.careTemplateId),
        futureCareTaskAction: "",

        weight: String(
            animal.weight ?? ""
        ),
        minWeight: animal.minWeight == null ? "" : String(animal.minWeight),
        maxWeight: animal.maxWeight == null ? "" : String(animal.maxWeight),
        penId: animal.penId == null ? "" : String(animal.penId),

        penLocation:
            animal.penLocation || "",

        healthStatus:
            animal.healthStatus ||
            "Healthy",
        healthyQuantity: String(animal.healthyQuantity ?? (animal.healthStatus === "Healthy" ? animal.quantity : 0)),
        atRiskQuantity: String(animal.atRiskQuantity ?? (animal.healthStatus === "At Risk" ? animal.quantity : 0)),
        sickQuantity: String(animal.sickQuantity ?? (animal.healthStatus === "Sick" ? animal.quantity : 0)),
        underTreatmentQuantity: String(animal.underTreatmentQuantity ?? (animal.healthStatus === "Under Treatment" ? animal.quantity : 0)),

        growthStatus:
            animal.growthStatus ||
            "Growing",

        lastCheckup:
            animal.lastCheckup ||
            getTodayDate(),

        healthNotes:
            animal.healthNotes || "",

        vaccinationStatus:
            animal.vaccinationStatus ||
            "Not Vaccinated",

        nextVaccination:
            animal.nextVaccination ||
            "",

        feedInventoryItemId: animal.feedInventoryItemId == null ? "" : String(animal.feedInventoryItemId),
        feedingFrequency: parseFeedingSchedule(animal.feedingSchedule?.times).frequency,
        feedingPeriods: parseFeedingSchedule(animal.feedingSchedule?.times).periods,
        feedTimes:
            animal.feedingSchedule
                ?.times || "",

        feedType:
            animal.feedingSchedule
                ?.feedType || "",

        dailyFeedKg: String(
            animal.feedingSchedule
                ?.dailyAmountKg ?? ""
        ),

        feedingNotes:
            animal.feedingSchedule
                ?.notes || "",

        dateAcquired:
            animal.dateAcquired ||
            getTodayDate(),

        acquiredFrom:
            animal.acquiredFrom || "",
    };
}

function createEmptyVaccinationForm() {
    return {
        vaccine: "",
        dateAdministered:
            getTodayDate(),
        nextDue: "",
        status: "Up to Date",
        administeredBy: "",
        inventoryItemId: "",
        inventoryQuantity: "",
        notes: "",
    };
}

/* =========================================================
   ADD AND EDIT LIVESTOCK FORM
========================================================= */

export function LivestockFormModal({
    open,
    animal,
    onClose,
    onSave,
    saving = false,
}) {
    const [form, setForm] =
        useState(
            createEmptyLivestockForm
        );
    const [pens, setPens] = useState([]);
    const [feedInventory, setFeedInventory] = useState([]);
    const [employees, setEmployees] = useState([]);
    const [careTemplates, setCareTemplates] = useState([]);
    const [growthAssessment, setGrowthAssessment] = useState(null);

    const isEditing =
        Boolean(animal);

    useEffect(() => {
        if (!open) {
            return;
        }

        setForm(
            createLivestockFormFromAnimal(
                animal
            )
        );

        livestockService
            .getPens()
            .then(setPens)
            .catch((error) => {
                console.error("Failed to load livestock pens:", error);
                setPens([]);
            });

        inventoryService.getInventory(false)
            .then((items) => setFeedInventory(items.filter(isFeedItem)))
            .catch((error) => {
                console.error("Failed to load feed Inventory:", error);
                setFeedInventory([]);
            });

        Promise.all([
            workforceService.getEmployees(),
            workforceService.getCareTemplates("Livestock", false),
        ]).then(([employeeRows, templateRows]) => {
            setEmployees(employeeRows || []);
            setCareTemplates(templateRows || []);
        }).catch((error) => {
            console.warn("Unable to load livestock workforce choices:", error);
            setEmployees([]);
            setCareTemplates([]);
        });

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, animal]);

    useEffect(() => {
        if (!open) return undefined;
        const hasAge = Boolean(form.dateOfBirth) || (String(form.estimatedAgeDays || "").trim() && form.estimatedAgeAsOfDate);
        if (!hasAge || !form.type) {
            setGrowthAssessment(null);
            return undefined;
        }
        const timer = window.setTimeout(() => {
            livestockService.previewGrowthAssessment(form)
                .then(setGrowthAssessment)
                .catch((error) => {
                    console.warn("Unable to preview backend growth assessment:", error);
                    setGrowthAssessment(null);
                });
        }, 250);
        return () => window.clearTimeout(timer);
    }, [
        open, form.type, form.breed, form.productionPurpose, form.sex, form.dateOfBirth,
        form.estimatedAgeDays, form.estimatedAgeAsOfDate, form.weight,
    ]);

    if (!open) {
        return null;
    }

    const handleChange = (event) => {
        const { name, value } = event.target;

        setForm((currentForm) => {
            const nextForm = {
                ...currentForm,
                [name]: value,
            };

            if (name === "recordType" && value === "Individual") {
                nextForm.quantity = "1";
                nextForm.maleQuantity = value === "Male" ? "1" : "0";
                nextForm.femaleQuantity = value === "Female" ? "1" : "0";
                nextForm.unknownSexQuantity = "0";
            }
            if (name === "quantity" && currentForm.recordType !== "Individual") {
                const currentKnown = Number(currentForm.maleQuantity || 0) + Number(currentForm.femaleQuantity || 0);
                nextForm.unknownSexQuantity = String(Math.max(0, Number(value || 0) - currentKnown));
            }
            if (name === "sex" && currentForm.recordType === "Individual") {
                nextForm.maleQuantity = value === "Male" ? "1" : "0";
                nextForm.femaleQuantity = value === "Female" ? "1" : "0";
                nextForm.unknownSexQuantity = "0";
            }
            if (name === "type") {
                nextForm.productionPurpose = productionPurposes[value]?.[0] || "General";
                nextForm.penId = "";
                nextForm.penLocation = "";
            }
            if (name === "feedInventoryItemId") {
                const item = feedInventory.find((row) => String(row.id) === String(value));
                nextForm.feedType = item?.name || "";
            }

            return nextForm;
        });
    };

    const toggleFeedingPeriod = (period) => {
        setForm((current) => {
            const required = feedingCount(current.feedingFrequency);
            const selected = current.feedingPeriods || [];
            const exists = selected.includes(period);
            let next = exists ? selected.filter((item) => item !== period) : [...selected, period];
            if (!exists && next.length > required) next = next.slice(next.length - required);
            return { ...current, feedingPeriods: next };
        });
    };

    const handleSubmit = (event) => {
        event.preventDefault();
        if (saving) return;

        const requiredFields = [
            "recordName",
            "type",
            "breed",
            "quantity",
            "weight",
            "penId",
            "dateAcquired",
        ];

        const missingRequiredField =
            requiredFields.some(
                (fieldName) =>
                    !String(
                        form[fieldName]
                    ).trim()
            );

        if (missingRequiredField) {
            notify(
                "Please complete all required livestock fields."
            );

            return;
        }

        if (!form.dateOfBirth && !String(form.estimatedAgeDays || "").trim()) {
            notify("Provide the date of birth/hatch or an estimated biological age in days.");
            return;
        }
        if (!form.dateOfBirth && (!form.estimatedAgeAsOfDate || !form.estimatedAgeConfidence || !form.estimatedAgeSource.trim())) {
            notify("Unknown birth/hatch date requires the age estimation date, confidence, and source/basis.");
            return;
        }

        const quantity = Number(
            form.quantity
        );

        const weight = Number(
            form.weight
        );

        const dailyFeedKg =
            form.dailyFeedKg
                ? Number(
                      form.dailyFeedKg
                  )
                : 0;

        if (
            Number.isNaN(quantity) ||
            quantity < 1
        ) {
            notify(
                "Animal count must be at least one."
            );

            return;
        }

        if (form.recordType === "Individual" && quantity !== 1) {
            notify(
                "Individual livestock records must have an animal count of 1."
            );
            return;
        }

        if (form.recordType === "Individual" && form.sex === "Mixed") {
            notify(
                "Choose Male or Female for an individual animal."
            );
            return;
        }

        let maleQuantity = Number(form.maleQuantity || 0);
        let femaleQuantity = Number(form.femaleQuantity || 0);
        let unknownSexQuantity = Number(form.unknownSexQuantity || 0);
        if (form.recordType === "Individual") {
            maleQuantity = form.sex === "Male" ? 1 : 0;
            femaleQuantity = form.sex === "Female" ? 1 : 0;
            unknownSexQuantity = 0;
        }
        if (maleQuantity + femaleQuantity + unknownSexQuantity !== quantity) {
            notify("Male + Female + Unknown quantities must equal the livestock count.");
            return;
        }

        if (form.healthStatus === "Mixed") {
            const healthTotal = Number(form.healthyQuantity || 0) + Number(form.atRiskQuantity || 0) + Number(form.sickQuantity || 0) + Number(form.underTreatmentQuantity || 0);
            if (healthTotal !== quantity) {
                notify("This batch has a Mixed health status. Update its head-count breakdown from the Health Notes tab before changing the batch quantity.");
                return;
            }
        }

        if (form.feedInventoryItemId) {
            const requiredPeriods = feedingCount(form.feedingFrequency);
            if ((form.feedingPeriods || []).length !== requiredPeriods) {
                notify(`Select exactly ${requiredPeriods} feeding period${requiredPeriods > 1 ? "s" : ""}.`);
                return;
            }
            if (dailyFeedKg <= 0) {
                notify("Enter the daily feed amount per animal for the linked feed item.");
                return;
            }
        }

        if (
            Number.isNaN(weight) ||
            weight <= 0
        ) {
            notify(
                "Weight must be greater than zero."
            );

            return;
        }

        if (
            form.dateOfBirth &&
            form.lastCheckup &&
            form.lastCheckup <
                form.dateOfBirth
        ) {
            notify(
                "The last checkup cannot be earlier than the date of birth."
            );

            return;
        }

        if (
            form.dateOfBirth &&
            form.nextVaccination &&
            form.nextVaccination <
                form.dateOfBirth
        ) {
            notify(
                "The vaccination date cannot be earlier than the date of birth."
            );

            return;
        }

        if (
            form.dateOfBirth &&
            form.dateAcquired &&
            form.dateAcquired <
                form.dateOfBirth
        ) {
            notify(
                "The date acquired cannot be earlier than the date of birth."
            );

            return;
        }

        if (
            isEditing
            && animal?.careTemplateId
            && !form.careTemplateId
            && !form.futureCareTaskAction
        ) {
            notify("Choose what should happen to future Pending care tasks before removing this care template.");
            return;
        }

        onSave({
            ...scheduleForm(form),
            recordType: form.recordType,
            lifecycleStatus: form.lifecycleStatus,

            recordName:
                form.recordName.trim(),

            type: form.type,

            breed:
                form.breed.trim(),

            quantity,

            sex: form.recordType === "Individual"
                ? form.sex
                : (maleQuantity === quantity ? "Male" : femaleQuantity === quantity ? "Female" : "Mixed"),
            maleQuantity,
            femaleQuantity,
            unknownSexQuantity,
            productionPurpose: form.productionPurpose,

            dateOfBirth:
                form.dateOfBirth || null,
            ageIsEstimated: Boolean(!form.dateOfBirth),
            estimatedAgeDays: form.estimatedAgeDays === "" ? null : Number(form.estimatedAgeDays),
            estimatedAgeAsOfDate: form.dateOfBirth ? null : (form.estimatedAgeAsOfDate || null),
            estimatedAgeConfidence: form.dateOfBirth ? null : (form.estimatedAgeConfidence || null),
            estimatedAgeSource: form.dateOfBirth ? null : (form.estimatedAgeSource.trim() || null),
            acquisitionStage: form.acquisitionStage || form.growthStatus,
            acquisitionVaccinationHistory: form.acquisitionVaccinationHistory.trim() || null,
            acquisitionTreatmentHistory: form.acquisitionTreatmentHistory.trim() || null,
            feedingPlanName: form.feedingPlanName.trim() || null,
            assignedEmployeeId: form.assignedEmployeeId ? Number(form.assignedEmployeeId) : null,
            careTemplateId: form.careTemplateId ? Number(form.careTemplateId) : null,
            futureCareTaskAction: form.futureCareTaskAction || undefined,

            weight,
            minWeight: form.minWeight ? Number(form.minWeight) : null,
            maxWeight: form.maxWeight ? Number(form.maxWeight) : null,
            penId: Number(form.penId),

            penLocation:
                form.penLocation.trim(),

            healthStatus:
                form.healthStatus,
            healthyQuantity: form.healthStatus === "Mixed" ? Number(form.healthyQuantity || 0) : (form.healthStatus === "Healthy" ? quantity : 0),
            atRiskQuantity: form.healthStatus === "Mixed" ? Number(form.atRiskQuantity || 0) : (form.healthStatus === "At Risk" ? quantity : 0),
            sickQuantity: form.healthStatus === "Mixed" ? Number(form.sickQuantity || 0) : (form.healthStatus === "Sick" ? quantity : 0),
            underTreatmentQuantity: form.healthStatus === "Mixed" ? Number(form.underTreatmentQuantity || 0) : (form.healthStatus === "Under Treatment" ? quantity : 0),

            growthStatus:
                form.growthStatus,

            lastCheckup:
                form.lastCheckup,

            healthNotes:
                form.healthNotes.trim() ||
                "No health issues observed.",

            vaccinationStatus:
                form.vaccinationStatus,

            nextVaccination:
                form.nextVaccination,

            feedInventoryItemId: form.feedInventoryItemId ? Number(form.feedInventoryItemId) : null,
            feedingSchedule: {
                times: form.feedInventoryItemId
                    ? serializeFeedingSchedule(form.feedingFrequency, form.feedingPeriods)
                    : "",

                feedType: form.feedInventoryItemId ? form.feedType.trim() : "",

                dailyAmountKg:
                    dailyFeedKg,

                notes:
                    form.feedingNotes.trim() ||
                    "No feeding notes.",
            },

            dateAcquired:
                form.dateAcquired,

            acquiredFrom:
                form.acquiredFrom.trim() ||
                "Not specified",
        });
    };

    return (
        <div
            className="livestock-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="add-livestock-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="livestock-modal-header">
                    <div>
                        <h2>
                            {isEditing
                                ? "Edit Livestock"
                                : "Add Livestock"}
                        </h2>

                        <p>
                            {isEditing
                                ? `Update ${animal.recordName} (${animal.animalId}) and save the changes.`
                                : "Create an individual animal or livestock batch with pen, health, feeding, vaccination, and acquisition information."}
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close livestock form"
                        disabled={saving}
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="add-livestock-form"
                    aria-busy={saving}
                    onSubmit={handleSubmit}
                >
                    <fieldset className="livestock-form-fields" disabled={saving}>
                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">
                                pets
                            </span>

                            <div>
                                <h3>
                                    Livestock Information
                                </h3>

                                <p>
                                    Choose individual or batch tracking, then enter the livestock information.
                                </p>
                            </div>
                        </div>

                        <div className="livestock-form-grid">
                            <div className="livestock-form-group livestock-record-type-group">
                                <label htmlFor="livestockRecordType">
                                    Record Type
                                    <span>*</span>
                                </label>

                                <select
                                    id="livestockRecordType"
                                    name="recordType"
                                    value={form.recordType}
                                    onChange={handleChange}
                                    required
                                >
                                    <option value="Batch">Batch / Group</option>
                                    <option value="Individual">Individual Animal</option>
                                </select>

                                <small className="livestock-field-help">
                                    {form.recordType === "Individual"
                                        ? "Tracks one animal separately for health, breeding, and movement history."
                                        : "Tracks animals managed together in the same pen and stage."}
                                </small>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockRecordName">
                                    Record Name
                                    <span>*</span>
                                </label>

                                <input
                                    id="livestockRecordName"
                                    name="recordName"
                                    type="text"
                                    placeholder="Example: Pig Batch 06"
                                    value={
                                        form.recordName
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockType">
                                    Animal Type
                                    <span>*</span>
                                </label>

                                <select
                                    id="livestockType"
                                    name="type"
                                    value={form.type}
                                    onChange={
                                        handleChange
                                    }
                                    required
                                >
                                    {(animalTypes.includes(form.type)
                                        ? animalTypes
                                        : [form.type, ...animalTypes]
                                    ).map(
                                        (type) => (
                                            <option
                                                key={
                                                    type
                                                }
                                                value={
                                                    type
                                                }
                                            >
                                                {
                                                    type
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockBreed">
                                    Breed
                                    <span>*</span>
                                </label>

                                <input
                                    id="livestockBreed"
                                    name="breed"
                                    type="text"
                                    placeholder="Example: Native"
                                    value={
                                        form.breed
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockQuantity">
                                    {form.recordType === "Individual"
                                        ? "Animal Count"
                                        : "Batch Count"}
                                    <span>*</span>
                                </label>

                                <input
                                    id="livestockQuantity"
                                    name="quantity"
                                    type="number"
                                    min="1"
                                    disabled={form.recordType === "Individual"}
                                    value={
                                        form.quantity
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockSex">
                                    Sex
                                </label>

                                <select
                                    id="livestockSex"
                                    name="sex"
                                    value={form.sex}
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="Mixed">
                                        Mixed
                                    </option>

                                    <option value="Male">
                                        Male
                                    </option>

                                    <option value="Female">
                                        Female
                                    </option>
                                </select>
                            </div>

                            {form.recordType === "Batch" && (
                                <>
                                    <div className="livestock-form-group">
                                        <label>Male Count</label>
                                        <input name="maleQuantity" type="number" min="0" value={form.maleQuantity} onChange={handleChange} />
                                    </div>
                                    <div className="livestock-form-group">
                                        <label>Female Count</label>
                                        <input name="femaleQuantity" type="number" min="0" value={form.femaleQuantity} onChange={handleChange} />
                                    </div>
                                    <div className="livestock-form-group">
                                        <label>Unknown Sex Count</label>
                                        <input name="unknownSexQuantity" type="number" min="0" value={form.unknownSexQuantity} onChange={handleChange} />
                                    </div>
                                </>
                            )}

                            <div className="livestock-form-group">
                                <label htmlFor="livestockProductionPurpose">Production Purpose</label>
                                <select id="livestockProductionPurpose" name="productionPurpose" value={form.productionPurpose} onChange={handleChange}>
                                    {(productionPurposes[form.type] || ["General"]).map((purpose) => (
                                        <option key={purpose} value={purpose}>{purpose}</option>
                                    ))}
                                </select>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockBirthDate">
                                    Date of Birth
                                    <span>*</span>
                                </label>

                                <input
                                    id="livestockBirthDate"
                                    name="dateOfBirth"
                                    type="date"
                                    value={form.dateOfBirth}
                                    onChange={handleChange}
                                    required={!form.estimatedAgeDays}
                                />
                                <small className="livestock-field-help">If the exact birth date is unknown, enter an estimated age below.</small>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockEstimatedAgeDays">Estimated Biological Age (days)</label>
                                <input id="livestockEstimatedAgeDays" name="estimatedAgeDays" type="number" min="0" value={form.estimatedAgeDays} onChange={(event) => setForm((current) => ({ ...current, estimatedAgeDays: event.target.value, ageIsEstimated: Boolean(event.target.value) }))} />
                                <small className="livestock-field-help">Use only when the exact birth/hatch date is unknown.</small>
                            </div>

                            {!form.dateOfBirth && String(form.estimatedAgeDays || "").trim() && (
                                <>
                                    <div className="livestock-form-group">
                                        <label htmlFor="livestockEstimatedAgeAsOf">Age Estimation Date <span>*</span></label>
                                        <input id="livestockEstimatedAgeAsOf" name="estimatedAgeAsOfDate" type="date" value={form.estimatedAgeAsOfDate} onChange={handleChange} required />
                                    </div>
                                    <div className="livestock-form-group">
                                        <label htmlFor="livestockEstimatedAgeConfidence">Estimation Confidence <span>*</span></label>
                                        <select id="livestockEstimatedAgeConfidence" name="estimatedAgeConfidence" value={form.estimatedAgeConfidence} onChange={handleChange} required>
                                            <option value="">Select confidence</option>
                                            <option value="Low">Low</option>
                                            <option value="Medium">Medium</option>
                                            <option value="High">High</option>
                                        </select>
                                    </div>
                                    <div className="livestock-form-group full-width">
                                        <label htmlFor="livestockEstimatedAgeSource">Age Estimate Source / Basis <span>*</span></label>
                                        <input id="livestockEstimatedAgeSource" name="estimatedAgeSource" type="text" maxLength="255" placeholder="Seller record, transfer document, veterinarian estimate, dentition, etc." value={form.estimatedAgeSource} onChange={handleChange} required />
                                    </div>
                                </>
                            )}

                            <div className="livestock-form-group">
                                <label htmlFor="livestockWeight">
                                    {form.recordType === "Individual"
                                        ? "Weight"
                                        : "Average Weight per Animal"}
                                    <span>*</span>
                                </label>

                                <div className="livestock-unit-input">
                                    <input
                                        id="livestockWeight"
                                        name="weight"
                                        type="number"
                                        min="0.01"
                                        step="0.01"
                                        placeholder="0"
                                        value={
                                            form.weight
                                        }
                                        onChange={
                                            handleChange
                                        }
                                        required
                                    />

                                    <span>kg</span>
                                </div>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockPen">
                                    Pen Location <span>*</span>
                                </label>
                                <select
                                    id="livestockPen"
                                    name="penId"
                                    value={form.penId}
                                    onChange={(event) => {
                                        const pen = pens.find((row) => String(row.id) === String(event.target.value));
                                        setForm((current) => ({
                                            ...current,
                                            penId: event.target.value,
                                            penLocation: pen?.name || "",
                                        }));
                                    }}
                                    required
                                >
                                    <option value="">Select an available pen</option>
                                    {pens
                                        .filter((pen) => {
                                            const species = String(pen.animalType || "").toLowerCase();
                                            const compatible = !species || species === "all livestock" || species === String(form.type).toLowerCase();
                                            const available = pen.capacity == null || Number(pen.currentOccupancy || 0) + Number(form.quantity || 0) <= Number(pen.capacity);
                                            const current = String(pen.id) === String(form.penId);
                                            return compatible && (available || current) && !["Inactive", "Closed", "Maintenance"].includes(pen.status);
                                        })
                                        .map((pen) => (
                                            <option key={pen.id} value={pen.id}>
                                                {pen.name} — {pen.purpose || "General"} — {pen.capacity ? `${pen.currentOccupancy}/${pen.capacity} occupied` : `${pen.currentOccupancy} occupied`}
                                            </option>
                                        ))}
                                </select>
                                <small className="livestock-field-help">
                                    Only compatible pens with enough available capacity are shown. Use Manage Pens on the Livestock page to create or update pens.
                                </small>
                            </div>
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">
                                health_and_safety
                            </span>

                            <div>
                                <h3>
                                    Health and Growth
                                </h3>

                                <p>
                                    Record the current
                                    health condition and
                                    growth status.
                                </p>
                            </div>
                        </div>

                        <div className="livestock-form-grid">
                            <div className="livestock-form-group">
                                <label htmlFor="livestockHealthStatus">
                                    Health Status
                                </label>

                                <select
                                    id="livestockHealthStatus"
                                    name="healthStatus"
                                    value={
                                        form.healthStatus
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {healthStatuses.map(
                                        (status) => (
                                            <option
                                                key={
                                                    status
                                                }
                                                value={
                                                    status
                                                }
                                            >
                                                {
                                                    status
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockGrowthStatus">
                                    Current Growth Stage
                                </label>

                                <select
                                    id="livestockGrowthStatus"
                                    name="growthStatus"
                                    value={form.growthStatus}
                                    onChange={handleChange}
                                    disabled={isEditing}
                                >
                                    {growthStatuses.map((status) => (
                                        <option key={status} value={status}>{status}</option>
                                    ))}
                                </select>
                                {isEditing && (
                                    <small className="livestock-field-help">Existing stages can only be changed through the manager stage-override action so the reason is audited.</small>
                                )}
                                {growthAssessment?.suggestedStage && (
                                    <div className={`livestock-growth-suggestion${growthAssessment.profileStatus === "Draft" ? " is-draft" : ""}`} role="note">
                                        <div className="livestock-growth-suggestion-heading">
                                            <span className="material-symbols-outlined" aria-hidden="true">
                                                {growthAssessment.profileStatus === "Draft" ? "warning_amber" : "info"}
                                            </span>
                                            <div>
                                                <small>Suggested growth stage</small>
                                                <strong>{growthAssessment.suggestedStage}</strong>
                                            </div>
                                        </div>
                                        <p>{growthAssessment.suggestionReason}</p>
                                        {growthAssessment.profileStatus === "Draft" && (
                                            <p className="livestock-growth-suggestion-caution"><strong>Draft profile:</strong> not yet expert-approved. {isEditing ? "This suggestion does not change the recorded stage; a manager must review any override." : "Confirm the suggested stage before using it."}</p>
                                        )}
                                        {!isEditing && growthAssessment.suggestedStage !== form.growthStatus && (
                                            <button type="button" className="livestock-inline-action" onClick={() => setForm((current) => ({ ...current, growthStatus: growthAssessment.suggestedStage, acquisitionStage: growthAssessment.suggestedStage }))}>Use backend suggestion</button>
                                        )}
                                    </div>
                                )}
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockLastCheckup">
                                    Last Checkup
                                </label>

                                <input
                                    id="livestockLastCheckup"
                                    name="lastCheckup"
                                    type="date"
                                    value={
                                        form.lastCheckup
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockVaccinationStatus">
                                    Vaccination Status
                                </label>

                                <select
                                    id="livestockVaccinationStatus"
                                    name="vaccinationStatus"
                                    value={
                                        form.vaccinationStatus
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {vaccinationStatuses.map(
                                        (status) => (
                                            <option
                                                key={
                                                    status
                                                }
                                                value={
                                                    status
                                                }
                                            >
                                                {
                                                    status
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockNextVaccination">
                                    Next Vaccination
                                </label>

                                <input
                                    id="livestockNextVaccination"
                                    name="nextVaccination"
                                    type="date"
                                    value={
                                        form.nextVaccination
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                        </div>

                        <div className="livestock-form-group">
                            <label htmlFor="livestockHealthNotes">
                                Health Notes
                            </label>

                            <textarea
                                id="livestockHealthNotes"
                                name="healthNotes"
                                rows="4"
                                placeholder="Enter health observations, symptoms, or treatment details..."
                                value={
                                    form.healthNotes
                                }
                                onChange={
                                    handleChange
                                }
                            />
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">nutrition</span>
                            <div>
                                <h3>Feeding Information</h3>
                                <p>Link the exact Feed item from Inventory and choose a standardized daily schedule.</p>
                            </div>
                        </div>

                        <div className="livestock-form-grid">
                            <div className="livestock-form-group">
                                <label htmlFor="livestockFeedInventory">Feed Item</label>
                                <select id="livestockFeedInventory" name="feedInventoryItemId" value={form.feedInventoryItemId} onChange={handleChange}>
                                    <option value="">No feeding schedule yet</option>
                                    {feedInventory.map((item) => (
                                        <option key={item.id} value={item.id}>
                                            {item.name} — {item.quantity} {item.unit} available
                                        </option>
                                    ))}
                                </select>
                                <small className="livestock-field-help">Only active, unexpired Feed Inventory items with available stock are shown.</small>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockFeedFrequency">Feedings Per Day</label>
                                <select
                                    id="livestockFeedFrequency"
                                    name="feedingFrequency"
                                    value={form.feedingFrequency}
                                    disabled={!form.feedInventoryItemId}
                                    onChange={(event) => {
                                        const value = event.target.value;
                                        const count = feedingCount(value);
                                        setForm((current) => ({ ...current, feedingFrequency: value, feedingPeriods: feedingPeriods.slice(0, count) }));
                                    }}
                                >
                                    {feedingFrequencies.map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}
                                </select>
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockFeedAmount">Daily Feed per Animal</label>
                                <div className="livestock-unit-input">
                                    <input id="livestockFeedAmount" name="dailyFeedKg" type="number" min="0" step="0.001" value={form.dailyFeedKg} onChange={handleChange} disabled={!form.feedInventoryItemId} />
                                    <span>kg</span>
                                </div>
                            </div>
                        </div>

                        {form.feedInventoryItemId && (
                            <div className="livestock-form-group">
                                <label>Feeding Period</label>
                                <div className="livestock-choice-chips">
                                    {feedingPeriods.map((period) => (
                                        <button key={period} type="button" className={(form.feedingPeriods || []).includes(period) ? "active" : ""} onClick={() => toggleFeedingPeriod(period)}>
                                            {period}{(form.feedingPeriods || []).includes(period) ? " ✓" : ""}
                                        </button>
                                    ))}
                                </div>
                                <small className="livestock-field-help">Select exactly {feedingCount(form.feedingFrequency)} period(s). Each completed occurrence deducts only that occurrence from the linked Feed Inventory item.</small>
                            </div>
                        )}

                        <div className="livestock-form-group">
                            <label htmlFor="livestockFeedingNotes">Feeding Notes</label>
                            <textarea id="livestockFeedingNotes" name="feedingNotes" rows="3" placeholder="Enter feeding instructions or observations..." value={form.feedingNotes} onChange={handleChange} />
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">assignment_ind</span>
                            <div><h3>Employee & Care Plan</h3><p>Assign a responsible employee and an approved growth/health care template.</p></div>
                        </div>
                        <div className="livestock-form-grid">
                            <div className="livestock-form-group"><label htmlFor="livestockAssignedEmployee">Assigned Employee</label><select id="livestockAssignedEmployee" name="assignedEmployeeId" value={form.assignedEmployeeId} onChange={handleChange}><option value="">Unassigned</option>{employees.filter((employee)=>employee.employment_status === "Active").map((employee)=><option key={employee.id} value={employee.id}>{employee.full_name} — {employee.positions?.length ? `${employee.positions.find((p)=>p.is_primary)?.name || employee.positions[0].name}${employee.positions.length > 1 ? ` +${employee.positions.length - 1} more` : ""}` : employee.position || "Employee"}</option>)}</select></div>
                            <div className="livestock-form-group"><label>Care Template</label><select name="careTemplateId" value={form.careTemplateId} onChange={handleChange}><option value="">No template</option>{careTemplates.map((template)=><option key={template.id} value={template.id}>{template.name} ({template.steps?.length || 0} steps)</option>)}</select></div>
                            {isEditing && animal?.careTemplateId && !form.careTemplateId && (
                                <div className="livestock-form-group"><label>Future Pending Care Tasks</label><select name="futureCareTaskAction" value={form.futureCareTaskAction} onChange={handleChange} required><option value="">Choose an action</option><option value="keep">Keep existing future tasks</option><option value="resolve">Resolve future tasks</option></select></div>
                            )}
                            <div className="livestock-form-group"><label>Feeding Plan Name</label><input name="feedingPlanName" type="text" placeholder="Example: Grower Feeding Plan" value={form.feedingPlanName} onChange={handleChange}/></div>
                        </div>
                    </section>

                    <section className="livestock-form-section">
                        <div className="livestock-section-title">
                            <span className="material-symbols-outlined">
                                inventory
                            </span>

                            <div>
                                <h3>
                                    Acquisition Information
                                </h3>

                                <p>
                                    Record when and where
                                    the livestock was
                                    acquired.
                                </p>
                            </div>
                        </div>

                        <div className="livestock-form-grid">
                            <div className="livestock-form-group full-width">
                                <label htmlFor="livestockAcquisitionVaccinationHistory">Known Vaccination History Before Acquisition / Transfer</label>
                                <textarea id="livestockAcquisitionVaccinationHistory" name="acquisitionVaccinationHistory" rows="3" placeholder="List known vaccines/dates, or leave blank if unknown so the record is flagged for review." value={form.acquisitionVaccinationHistory} onChange={handleChange} />
                            </div>

                            <div className="livestock-form-group full-width">
                                <label htmlFor="livestockAcquisitionTreatmentHistory">Known Treatment / Medicine History Before Acquisition / Transfer</label>
                                <textarea id="livestockAcquisitionTreatmentHistory" name="acquisitionTreatmentHistory" rows="3" placeholder="List known treatments/medicines and dates, or leave blank if unknown." value={form.acquisitionTreatmentHistory} onChange={handleChange} />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockDateAcquired">
                                    Date Acquired
                                    <span>*</span>
                                </label>

                                <input
                                    id="livestockDateAcquired"
                                    name="dateAcquired"
                                    type="date"
                                    value={
                                        form.dateAcquired
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="livestock-form-group">
                                <label htmlFor="livestockAcquiredFrom">
                                    Acquired From
                                </label>

                                <input
                                    id="livestockAcquiredFrom"
                                    name="acquiredFrom"
                                    type="text"
                                    placeholder="Example: Local Supplier"
                                    value={
                                        form.acquiredFrom
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                        </div>
                    </section>

                    <MonitoringScheduleFields value={form} onChange={setForm} module="Livestock" earliestDate={form.dateAcquired} disabled={saving} />
                    </fieldset>

                    <footer className="livestock-form-footer">
                        <button
                            type="button"
                            className="livestock-modal-cancel"
                            onClick={onClose}
                            disabled={saving}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="livestock-modal-save"
                            disabled={saving}
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            {saving ? "Saving…" : isEditing
                                ? "Save Changes"
                                : "Save Livestock"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}

/* =========================================================
   LIVESTOCK DETAILS MODAL
========================================================= */

export function LivestockDetailsModal({
    animal,
    onClose,
    onStageOverrideSaved,
    onSaveVaccination,
    savingVaccination = false,
    onSaveFeeding,
    onSaveGrowth,
    onSaveHealth,
    onSaveReproduction,
    onSaveProduction,
    canEditResources = true,
}) {
    const weightHistory = useHistoryRange(animal?.growthRecords, "measurementDate");
    const [
        activeTab,
        setActiveTab,
    ] = useState("overview");

    const [
        showVaccinationForm,
        setShowVaccinationForm,
    ] = useState(false);

    const [
        vaccinationForm,
        setVaccinationForm,
    ] = useState(
        createEmptyVaccinationForm
    );

    const [
        vaccineInventory,
        setVaccineInventory,
    ] = useState([]);
    const [feedInventory, setFeedInventory] = useState([]);
    const [vaccinationSchedule, setVaccinationSchedule] = useState([]);
    const [vaccinationScheduleLoading, setVaccinationScheduleLoading] = useState(false);
    const [vaccinationScheduleError, setVaccinationScheduleError] = useState("");

    const [
        feedingForm,
        setFeedingForm,
    ] = useState({
        inventoryItemId: "",
        frequency: "Once Daily",
        periods: ["Morning"],
        times: "",
        feedType: "",
        dailyAmountKg: "",
        notes: "",
    });

    const [
        healthForm,
        setHealthForm,
    ] = useState({
        healthStatus: "Healthy",
        healthyQuantity: "0",
        atRiskQuantity: "0",
        sickQuantity: "0",
        underTreatmentQuantity: "0",
        lastCheckup: "",
        healthNotes: "",
    });

    const [
        growthForm,
        setGrowthForm,
    ] = useState({
        measurementDate: getTodayDate(),
        animalsMeasured: "1",
        measurementBasis: "Average",
        weightKg: "",
        totalMeasuredWeightKg: "",
        minWeightKg: "",
        maxWeightKg: "",
        notes: "",
    });

    const [growthAssessment, setGrowthAssessment] = useState(null);
    const [growthAssessmentLoading, setGrowthAssessmentLoading] = useState(false);
    const [growthAssessmentError, setGrowthAssessmentError] = useState("");
    const [stageOverride, setStageOverride] = useState({ stage: "", reason: "" });
    const [stageOverrideSaving, setStageOverrideSaving] = useState(false);

    useEffect(() => {
        if (!animal) {
            return;
        }

        setActiveTab("overview");
        setVaccinationSchedule([]);
        setVaccinationScheduleError("");
        setGrowthAssessment(null);
        setGrowthAssessmentError("");
        setStageOverride({ stage: animal.growthStatus || "", reason: "" });

        setShowVaccinationForm(
            false
        );

        setVaccinationForm(
            createEmptyVaccinationForm()
        );

        const parsedFeeding = parseFeedingSchedule(animal.feedingSchedule?.times);
        setFeedingForm({
            inventoryItemId: animal.feedInventoryItemId == null ? "" : String(animal.feedInventoryItemId),
            frequency: parsedFeeding.frequency,
            periods: parsedFeeding.periods,
            times: animal.feedingSchedule?.times || "",
            feedType: animal.feedingSchedule?.feedType || "",
            dailyAmountKg: animal.feedingSchedule?.dailyAmountKg ?? "",
            notes: animal.feedingSchedule?.notes || "",
        });

        setHealthForm({
            healthStatus: animal.healthStatus || "Healthy",
            healthyQuantity: String(animal.healthyQuantity ?? (animal.healthStatus === "Healthy" ? animal.quantity : 0)),
            atRiskQuantity: String(animal.atRiskQuantity ?? (animal.healthStatus === "At Risk" ? animal.quantity : 0)),
            sickQuantity: String(animal.sickQuantity ?? (animal.healthStatus === "Sick" ? animal.quantity : 0)),
            underTreatmentQuantity: String(animal.underTreatmentQuantity ?? (animal.healthStatus === "Under Treatment" ? animal.quantity : 0)),
            lastCheckup: animal.lastCheckup || "",
            healthNotes: animal.healthNotes || "",
        });

        setGrowthForm({
            measurementDate: getTodayDate(),
            animalsMeasured: String(animal.recordType === "Individual" ? 1 : Math.min(Number(animal.quantity || 1), 10)),
            measurementBasis: "Average",
            weightKg: String(animal.weight ?? ""),
            totalMeasuredWeightKg: "",
            minWeightKg: animal.minWeight == null ? "" : String(animal.minWeight),
            maxWeightKg: animal.maxWeight == null ? "" : String(animal.maxWeight),
            notes: "",
        });

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [animal?.id]);

    useEffect(() => {
        if (!animal) {
            setVaccineInventory([]);
            setFeedInventory([]);
            return;
        }

        let cancelled = false;
        inventoryService.getInventory(false)
            .then((items) => {
                if (cancelled) return;
                setVaccineInventory(items.filter(isVaccineItem));
                setFeedInventory(items.filter(isFeedItem));
            })
            .catch((error) => {
                console.error("Unable to load vaccine inventory:", error);
                if (!cancelled) {
                    setVaccineInventory([]);
                    setFeedInventory([]);
                }
            });

        return () => { cancelled = true; };
    }, [animal]);

    const loadVaccinationSchedule = useCallback(async () => {
        if (!animal?.id) {
            setVaccinationSchedule([]);
            return;
        }
        setVaccinationScheduleLoading(true);
        setVaccinationScheduleError("");
        try {
            const rows = await livestockService.getVaccinationSchedule(animal.id);
            setVaccinationSchedule(rows || []);
        } catch (error) {
            console.error("Unable to load livestock vaccination schedule:", error);
            setVaccinationScheduleError(error?.message || "Unable to load vaccination schedule.");
        } finally {
            setVaccinationScheduleLoading(false);
        }
    }, [animal?.id]);

    useEffect(() => {
        if (!animal?.id || activeTab !== "vaccination") return;
        loadVaccinationSchedule();
    }, [animal?.id, activeTab, loadVaccinationSchedule]);

    const loadGrowthAssessment = useCallback(async () => {
        if (!animal?.id) {
            setGrowthAssessment(null);
            return;
        }
        setGrowthAssessmentLoading(true);
        setGrowthAssessmentError("");
        try {
            const assessment = await livestockService.getGrowthAssessment(animal.id);
            setGrowthAssessment(assessment);
            setStageOverride((current) => ({
                ...current,
                stage: current.stage || assessment.currentStage || animal.growthStatus || "",
            }));
        } catch (error) {
            console.error("Unable to load backend growth assessment:", error);
            setGrowthAssessmentError(error?.message || "Unable to load growth assessment.");
        } finally {
            setGrowthAssessmentLoading(false);
        }
    }, [animal?.id, animal?.growthStatus]);

    useEffect(() => {
        if (!animal?.id || activeTab !== "growth") return;
        loadGrowthAssessment();
    }, [animal?.id, activeTab, loadGrowthAssessment]);

    const handleStageOverride = async (event) => {
        event.preventDefault();
        if (!stageOverride.stage || stageOverride.reason.trim().length < 5) {
            notify("Select the stage and enter a reason of at least 5 characters.");
            return;
        }
        setStageOverrideSaving(true);
        try {
            const assessment = await livestockService.overrideGrowthStage(
                animal.id,
                stageOverride.stage,
                stageOverride.reason
            );
            setGrowthAssessment(assessment);
            setStageOverride({ stage: assessment.currentStage || stageOverride.stage, reason: "" });
            onStageOverrideSaved?.(animal.id, assessment.currentStage || stageOverride.stage);
            notify("Growth stage override saved with an audit entry.");
        } catch (error) {
            notify(error?.message || "Unable to override the growth stage.");
        } finally {
            setStageOverrideSaving(false);
        }
    };

    if (!animal) {
        return null;
    }

    const vaccinationRecords =
        animal.vaccinationRecords ||
        [];

    const growthRecords =
        animal.growthRecords ||
        [];

    const feedingSchedule =
        animal.feedingSchedule || {
            times: "Not specified",
            feedType: "Not specified",
            dailyAmountKg: 0,
            notes:
                "No feeding notes.",
        };

    const handleVaccinationChange = (
        event
    ) => {
        const { name, value } =
            event.target;

        setVaccinationForm((currentForm) => {
            const nextForm = {
                ...currentForm,
                [name]: value,
            };

            if (name === "inventoryItemId") {
                const selected = vaccineInventory.find(
                    (item) => String(item.id) === String(value)
                );
                nextForm.inventoryQuantity = "";
                nextForm.vaccine = selected?.name || "";
            }

            return nextForm;
        });
    };

    const handleVaccinationSubmit = async (
        event
    ) => {
        event.preventDefault();
        if (savingVaccination) return;

        if (
            !vaccinationForm.inventoryItemId ||
            !vaccinationForm.dateAdministered
        ) {
            notify(
                "Select an available Vaccine Inventory item and administration date."
            );

            return;
        }

        if (
            vaccinationForm.nextDue &&
            vaccinationForm.nextDue <
                vaccinationForm.dateAdministered
        ) {
            notify(
                "The next vaccination date cannot be earlier than the administration date."
            );

            return;
        }

        if (
            Number(vaccinationForm.inventoryQuantity || 0) <= 0
        ) {
            notify(
                "Enter the quantity of vaccine taken from inventory."
            );
            return;
        }

        if (vaccinationForm.inventoryItemId) {
            const selectedVaccineStock = vaccineInventory.find(
                (item) => String(item.id) === String(vaccinationForm.inventoryItemId)
            );
            if (
                selectedVaccineStock &&
                Number(vaccinationForm.inventoryQuantity || 0) >
                    Number(selectedVaccineStock.quantity || 0)
            ) {
                notify(
                    `Insufficient vaccine stock. Only ${selectedVaccineStock.quantity} ${selectedVaccineStock.unit} is available.`
                );
                return;
            }
        }

        const saved = await onSaveVaccination(
            animal.id,
            {
                id: Date.now(),

                vaccine: vaccineInventory.find((item) => String(item.id) === String(vaccinationForm.inventoryItemId))?.name || vaccinationForm.vaccine.trim(),

                dateAdministered:
                    vaccinationForm.dateAdministered,

                nextDue:
                    vaccinationForm.nextDue,

                status:
                    vaccinationForm.status,

                administeredBy:
                    vaccinationForm.administeredBy.trim() ||
                    "Not specified",

                inventoryItemId:
                    vaccinationForm.inventoryItemId || null,

                quantityUsed: Number(vaccinationForm.inventoryQuantity || 0),

                notes:
                    vaccinationForm.notes.trim() ||
                    "No vaccination notes.",
            }
        );

        if (saved === false) {
            return;
        }

        await loadVaccinationSchedule();

        setVaccinationForm(
            createEmptyVaccinationForm()
        );

        setShowVaccinationForm(
            false
        );
    };

    const handleFeedingChange = (
        event
    ) => {
        const { name, value } =
            event.target;

        setFeedingForm((currentForm) => {
            const next = { ...currentForm, [name]: value };
            if (name === "inventoryItemId") {
                const item = feedInventory.find((row) => String(row.id) === String(value));
                next.feedType = item?.name || "";
            }
            if (name === "frequency") {
                next.periods = feedingPeriods.slice(0, feedingCount(value));
            }
            return next;
        });
    };

    const toggleDetailFeedingPeriod = (period) => {
        setFeedingForm((current) => {
            const required = feedingCount(current.frequency);
            const selected = current.periods || [];
            const exists = selected.includes(period);
            let next = exists ? selected.filter((item) => item !== period) : [...selected, period];
            if (!exists && next.length > required) next = next.slice(next.length - required);
            return { ...current, periods: next };
        });
    };

    const handleFeedingSubmit = (
        event
    ) => {
        event.preventDefault();

        if (!feedingForm.inventoryItemId) {
            notify("Select an available Feed Inventory item.");
            return;
        }
        const required = feedingCount(feedingForm.frequency);
        if ((feedingForm.periods || []).length !== required) {
            notify(`Select exactly ${required} feeding period${required > 1 ? "s" : ""}.`);
            return;
        }
        if (Number(feedingForm.dailyAmountKg || 0) <= 0) {
            notify("Enter a daily feed amount greater than zero.");
            return;
        }
        onSaveFeeding(animal.id, {
            inventoryItemId: Number(feedingForm.inventoryItemId),
            times: serializeFeedingSchedule(feedingForm.frequency, feedingForm.periods),
            feedType: feedingForm.feedType,
            dailyAmountKg: Number(feedingForm.dailyAmountKg),
            notes: feedingForm.notes.trim() || "No feeding notes.",
        });
    };

    const handleHealthChange = (
        event
    ) => {
        const { name, value } =
            event.target;

        setHealthForm(
            (currentForm) => ({
                ...currentForm,
                [name]: value,
            })
        );
    };

    const handleHealthSubmit = (
        event
    ) => {
        event.preventDefault();

        const healthy = Number(healthForm.healthyQuantity || 0);
        const atRisk = Number(healthForm.atRiskQuantity || 0);
        const sick = Number(healthForm.sickQuantity || 0);
        const treatment = Number(healthForm.underTreatmentQuantity || 0);
        if (animal.recordType === "Batch" && healthy + atRisk + sick + treatment !== Number(animal.quantity || 0)) {
            notify(`Healthy + At Risk + Sick + Under Treatment must equal the batch quantity (${animal.quantity}).`);
            return;
        }
        onSaveHealth(animal.id, {
            healthStatus: healthForm.healthStatus,
            healthyQuantity: animal.recordType === "Batch" ? healthy : (healthForm.healthStatus === "Healthy" ? 1 : 0),
            atRiskQuantity: animal.recordType === "Batch" ? atRisk : (healthForm.healthStatus === "At Risk" ? 1 : 0),
            sickQuantity: animal.recordType === "Batch" ? sick : (healthForm.healthStatus === "Sick" ? 1 : 0),
            underTreatmentQuantity: animal.recordType === "Batch" ? treatment : (healthForm.healthStatus === "Under Treatment" ? 1 : 0),
            lastCheckup: healthForm.lastCheckup,
            healthNotes: healthForm.healthNotes.trim() || "No health issues observed.",
        });
    };

    const handleGrowthChange = (event) => {
        const { name, value } = event.target;
        setGrowthForm((currentForm) => ({
            ...currentForm,
            [name]: value,
        }));
    };

    const handleGrowthSubmit = async (event) => {
        event.preventDefault();

        const animalsMeasured = Number(growthForm.animalsMeasured || 0);
        let averageWeight = Number(growthForm.weightKg || 0);
        const totalWeight = Number(growthForm.totalMeasuredWeightKg || 0);
        if (growthForm.measurementBasis === "Total" && animalsMeasured > 0 && totalWeight > 0) {
            averageWeight = totalWeight / animalsMeasured;
        }
        if (!growthForm.measurementDate || animalsMeasured < 1 || animalsMeasured > Number(animal.quantity || 1) || averageWeight <= 0) {
            notify(`Enter a valid date, measurement, and Animals Measured between 1 and ${animal.quantity}.`);
            return;
        }
        const minWeight = growthForm.minWeightKg ? Number(growthForm.minWeightKg) : null;
        const maxWeight = growthForm.maxWeightKg ? Number(growthForm.maxWeightKg) : null;
        if (minWeight && minWeight > averageWeight || maxWeight && maxWeight < averageWeight || minWeight && maxWeight && minWeight > maxWeight) {
            notify("Check the minimum, average, and maximum weight values.");
            return;
        }

        const saved = await onSaveGrowth?.(animal.id, {
            measurementDate: growthForm.measurementDate,
            animalsMeasured,
            measurementBasis: growthForm.measurementBasis,
            weightKg: averageWeight,
            totalMeasuredWeightKg: totalWeight > 0 ? totalWeight : null,
            minWeightKg: minWeight,
            maxWeightKg: maxWeight,
            notes: growthForm.notes,
        });

        if (saved === false) {
            return;
        }

        setGrowthForm({
            measurementDate: getTodayDate(),
            animalsMeasured: String(animal.recordType === "Individual" ? 1 : Math.min(Number(animal.quantity || 1), 10)),
            measurementBasis: "Average",
            weightKg: String(saved?.weightKg ?? animal.weight ?? ""),
            totalMeasuredWeightKg: "",
            minWeightKg: saved?.minWeightKg == null ? "" : String(saved.minWeightKg),
            maxWeightKg: saved?.maxWeightKg == null ? "" : String(saved.maxWeightKg),
            notes: "",
        });
    };

    return (
        <div
            className="livestock-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="livestock-details-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="livestock-details-header">
                    <div className="livestock-details-title">
                        <span className="livestock-details-main-icon">
                            <span className="material-symbols-outlined">
                                pets
                            </span>
                        </span>

                        <div>
                            <div className="livestock-id-line">
                                <h2>
                                    {
                                        animal.recordName
                                    }
                                </h2>

                                <span>
                                    {
                                        animal.animalId
                                    }
                                </span>
                            </div>

                            <p>
                                {animal.type} •{" "}
                                {animal.breed} •{" "}
                                {animal.quantity}{" "}
                                {animal.quantity ===
                                1
                                    ? "animal"
                                    : "animals"}
                            </p>
                        </div>
                    </div>

                    <div className="livestock-details-header-actions">
                        <span
                            className={`livestock-details-health ${getClassName(
                                animal.healthStatus
                            )}`}
                        >
                            {
                                animal.healthStatus
                            }
                        </span>

                        <button
                            type="button"
                            onClick={onClose}
                            aria-label="Close livestock details"
                        >
                            <span className="material-symbols-outlined">
                                close
                            </span>
                        </button>
                    </div>
                </header>

                <nav className="livestock-detail-tabs">
                    {[
                        {
                            value: "overview",
                            label: "Overview",
                            icon: "dashboard",
                        },
                        {
                            value: "growth",
                            label: "Growth History",
                            icon: "monitor_weight",
                        },
                        {
                            value: "vaccination",
                            label: "Vaccination",
                            icon: "vaccines",
                        },
                        {
                            value: "feeding",
                            label: "Feeding",
                            icon: "nutrition",
                        },
                        {
                            value: "resources",
                            label: "Resource Usage",
                            icon: "inventory_2",
                        },
                        {
                            value: "reproduction",
                            label: "Reproduction",
                            icon: "family_history",
                        },
                        {
                            value: "production",
                            label: "Production",
                            icon: "monitoring",
                        },
                        {
                            value: "health",
                            label: "Health Notes",
                            icon:
                                "health_and_safety",
                        },
                    ].map((tab) => (
                        <button
                            type="button"
                            key={tab.value}
                            className={
                                activeTab ===
                                tab.value
                                    ? "active"
                                    : ""
                            }
                            onClick={() =>
                                setActiveTab(
                                    tab.value
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                {tab.icon}
                            </span>

                            {tab.label}
                        </button>
                    ))}
                </nav>

                <div className="livestock-details-body">
                    {activeTab ===
                        "overview" && (
                        <>
                            <section className="livestock-overview-grid">
                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        inventory_2
                                    </span>

                                    <div>
                                        <small>
                                            Record Type
                                        </small>

                                        <strong>
                                            {animal.recordType || "Batch"}
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        pets
                                    </span>

                                    <div>
                                        <small>
                                            Breed
                                        </small>

                                        <strong>
                                            {
                                                animal.breed
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        numbers
                                    </span>

                                    <div>
                                        <small>
                                            {animal.recordType === "Individual"
                                                ? "Animal Count"
                                                : "Batch Count"}
                                        </small>

                                        <strong>
                                            {
                                                animal.quantity
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        wc
                                    </span>

                                    <div>
                                        <small>
                                            Sex
                                        </small>

                                        <strong>
                                            {
                                                animal.sex
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        location_on
                                    </span>

                                    <div>
                                        <small>
                                            Pen Location
                                        </small>

                                        <strong>
                                            {
                                                animal.penLocation
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        cake
                                    </span>

                                    <div>
                                        <small>
                                            Age
                                        </small>

                                        <strong>
                                            {
                                                animal.age
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        scale
                                    </span>

                                    <div>
                                        <small>
                                            {animal.recordType === "Individual"
                                                ? "Weight"
                                                : "Average Weight per Animal"}
                                        </small>

                                        <strong>
                                            {
                                                animal.weight
                                            }{" "}
                                            kg
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        calendar_month
                                    </span>

                                    <div>
                                        <small>
                                            Date of Birth
                                        </small>

                                        <strong>
                                            {formatDate(
                                                animal.dateOfBirth
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        medical_services
                                    </span>

                                    <div>
                                        <small>
                                            Last Checkup
                                        </small>

                                        <strong>
                                            {formatDate(
                                                animal.lastCheckup
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        vaccines
                                    </span>

                                    <div>
                                        <small>
                                            Vaccination Status
                                        </small>

                                        <strong>
                                            {
                                                animal.vaccinationStatus
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        event_upcoming
                                    </span>

                                    <div>
                                        <small>
                                            Next Vaccination
                                        </small>

                                        <strong>
                                            {formatDate(
                                                animal.nextVaccination
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        monitoring
                                    </span>

                                    <div>
                                        <small>
                                            Growth Status
                                        </small>

                                        <strong>
                                            {
                                                animal.growthStatus
                                            }
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        inventory
                                    </span>

                                    <div>
                                        <small>
                                            Date Acquired
                                        </small>

                                        <strong>
                                            {formatDate(
                                                animal.dateAcquired
                                            )}
                                        </strong>
                                    </div>
                                </div>

                                <div className="livestock-overview-item">
                                    <span className="material-symbols-outlined">
                                        store
                                    </span>

                                    <div>
                                        <small>
                                            Acquired From
                                        </small>

                                        <strong>
                                            {
                                                animal.acquiredFrom
                                            }
                                        </strong>
                                    </div>
                                </div>
                            </section>

                            {animal.careTemplateId && (
                                <section className="livestock-detail-section">
                                    <div className="livestock-detail-section-heading">
                                        <div>
                                            <h3>Assigned Care Protocol</h3>
                                            <p>Care guidance linked to this record. Feeding and other built-in schedules are tracked once in My Tasks.</p>
                                        </div>
                                    </div>
                                    <div className="livestock-detail-info-grid">
                                        <div>
                                            <small>Protocol</small>
                                            <strong>{animal.careProtocolName || `Protocol #${animal.careTemplateId}`}{animal.careProtocolVersion ? ` · v${animal.careProtocolVersion}` : ""}</strong>
                                        </div>
                                        <div>
                                            <small>Status</small>
                                            <strong>{animal.careProtocolStatus || "Assigned"}</strong>
                                        </div>
                                    </div>
                                </section>
                            )}

                            <section className="livestock-detail-section">
                                <div className="livestock-detail-section-heading">
                                    <div>
                                        <h3>
                                            Feeding Summary
                                        </h3>

                                        <p>
                                            Current feeding
                                            schedule and daily
                                            consumption.
                                        </p>
                                    </div>
                                </div>

                                <div className="livestock-detail-info-grid">
                                    <div>
                                        <small>
                                            Schedule
                                        </small>

                                        <strong>
                                            {
                                                feedingSchedule.times
                                            }
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Feed Type
                                        </small>

                                        <strong>
                                            {
                                                feedingSchedule.feedType
                                            }
                                        </strong>
                                    </div>

                                    <div>
                                        <small>
                                            Daily Consumption
                                        </small>

                                        <strong>
                                            {
                                                feedingSchedule.dailyAmountKg
                                            }{" "}
                                            kg/day
                                        </strong>
                                    </div>

                                </div>
                            </section>

                            <section className="livestock-health-summary">
                                <span className="material-symbols-outlined">
                                    clinical_notes
                                </span>

                                <div>
                                    <strong>
                                        Health Notes
                                    </strong>

                                    <p>
                                        {
                                            animal.healthNotes
                                        }
                                    </p>
                                </div>
                            </section>
                        </>
                    )}

                    {activeTab === "growth" && (
                        <section className="livestock-detail-section">
                            <div className="livestock-detail-section-heading">
                                <div>
                                    <h3>Growth & Weight History</h3>
                                    <p>Record real measurements. For batches, enter how many animals were measured; the system uses the average weight for growth change and ADG.</p>
                                </div>
                            </div>

                            <div className="livestock-growth-kpis">
                                <div><small>Actual Average Weight</small><strong>{Number(animal.weight || 0).toFixed(2)} kg</strong></div>
                                <div><small>Biological Age</small><strong>{growthAssessment?.ageDays == null ? "—" : `${growthAssessment.ageDays} days`}</strong></div>
                                <div><small>Backend Suggested Stage</small><strong>{growthAssessment?.suggestedStage || "—"}</strong></div>
                                <div><small>Expected Weight</small><strong>{growthAssessment?.expectedMinWeightKg == null && growthAssessment?.expectedMaxWeightKg == null ? "—" : `${growthAssessment?.expectedMinWeightKg ?? "—"}–${growthAssessment?.expectedMaxWeightKg ?? "—"} kg`}</strong></div>
                            </div>

                            <div className="livestock-growth-assessment-card">
                                <div>
                                    <strong>Expected vs Actual Growth</strong>
                                    {growthAssessmentLoading ? (
                                        <p>Loading backend growth profile…</p>
                                    ) : growthAssessmentError ? (
                                        <p>{growthAssessmentError}</p>
                                    ) : growthAssessment ? (
                                        <>
                                            <p>{growthAssessment.suggestionReason || "The backend matched the biological age to the current growth profile."}</p>
                                            <p><b>Current recorded stage:</b> {growthAssessment.currentStage || animal.growthStatus || "—"} &nbsp; <b>Suggested:</b> {growthAssessment.suggestedStage || "—"}</p>
                                            <p><b>Profile:</b> {growthAssessment.profileName || "No matching profile"}{growthAssessment.profileVersion ? ` v${growthAssessment.profileVersion}` : ""}{growthAssessment.profileStatus ? ` · ${growthAssessment.profileStatus}` : ""}</p>
                                            <p><b>Age basis:</b> {growthAssessment.ageSource || "Unknown"}{animal.estimatedAgeConfidence ? ` · ${animal.estimatedAgeConfidence} confidence` : ""}{animal.estimatedAgeSource ? ` · ${animal.estimatedAgeSource}` : ""}</p>
                                            <p><b>Past medical history:</b> {animal.medicalHistoryStatus || "Unknown - Needs Review"}</p>
                                            {growthAssessment.deviationMessage && <p><b>Weight comparison:</b> {growthAssessment.deviationMessage}</p>}
                                            {growthAssessment.profileStatus === "Draft" && <p><b>Draft profile:</b> This expectation still requires expert review and is not a medical diagnosis.</p>}
                                        </>
                                    ) : <p>No matching backend growth profile is available.</p>}
                                </div>
                            </div>

                            <HistoryDateRange range={weightHistory.range} onChange={weightHistory.setRange} count={weightHistory.filtered.length} />
                            {canEditResources && (
                                <form className="livestock-edit-form livestock-stage-override-form" onSubmit={handleStageOverride}>
                                    <div className="livestock-detail-section-heading">
                                        <div>
                                            <h4>Manager Stage Override</h4>
                                            <p>Use only when the recorded stage should differ from the backend suggestion. A reason is required and the action is audited.</p>
                                        </div>
                                    </div>
                                    <div className="livestock-form-grid">
                                        <div className="livestock-form-group">
                                            <label>Override Stage</label>
                                            <select value={stageOverride.stage} onChange={(event) => setStageOverride((current) => ({ ...current, stage: event.target.value }))} required>
                                                <option value="">Select stage</option>
                                                {growthStatuses.map((status) => <option key={status} value={status}>{status}</option>)}
                                            </select>
                                        </div>
                                        <div className="livestock-form-group">
                                            <label>Reason</label>
                                            <input value={stageOverride.reason} onChange={(event) => setStageOverride((current) => ({ ...current, reason: event.target.value }))} placeholder="Observed maturity, transfer records, manager verification…" minLength={5} required />
                                        </div>
                                    </div>
                                    <div className="livestock-edit-footer"><button type="submit" disabled={stageOverrideSaving}>{stageOverrideSaving ? "Saving…" : "Save Audited Override"}</button></div>
                                </form>
                            )}

                            {canEditResources && (
                                <form className="livestock-edit-form livestock-growth-form" onSubmit={handleGrowthSubmit}>
                                    <div className="livestock-form-grid">
                                        <div className="livestock-form-group">
                                            <label>Measurement Date</label>
                                            <input name="measurementDate" type="date" min={animal.dateAcquired || animal.dateOfBirth || undefined} max={getTodayDate()} value={growthForm.measurementDate} onChange={handleGrowthChange} required />
                                        </div>
                                        <div className="livestock-form-group">
                                            <label>Animals Measured</label>
                                            <input name="animalsMeasured" type="number" min="1" max={animal.quantity} value={growthForm.animalsMeasured} onChange={handleGrowthChange} disabled={animal.recordType === "Individual"} required />
                                            <small className="livestock-field-help">{animal.recordType === "Batch" ? `Sample or full batch: ${growthForm.animalsMeasured || 0} of ${animal.quantity} animals.` : "Individual measurement."}</small>
                                        </div>
                                        <div className="livestock-form-group">
                                            <label>Entry Method</label>
                                            <select name="measurementBasis" value={growthForm.measurementBasis} onChange={handleGrowthChange}>
                                                <option value="Average">Average Weight</option>
                                                <option value="Total">Total Measured Weight</option>
                                            </select>
                                        </div>
                                        {growthForm.measurementBasis === "Average" ? (
                                            <div className="livestock-form-group">
                                                <label>Average Weight (kg)</label>
                                                <input name="weightKg" type="number" min="0.01" step="0.01" value={growthForm.weightKg} onChange={handleGrowthChange} required />
                                            </div>
                                        ) : (
                                            <div className="livestock-form-group">
                                                <label>Total Measured Weight (kg)</label>
                                                <input name="totalMeasuredWeightKg" type="number" min="0.01" step="0.01" value={growthForm.totalMeasuredWeightKg} onChange={handleGrowthChange} required />
                                                <small className="livestock-field-help">Average: {Number(growthForm.animalsMeasured || 0) > 0 && Number(growthForm.totalMeasuredWeightKg || 0) > 0 ? `${(Number(growthForm.totalMeasuredWeightKg) / Number(growthForm.animalsMeasured)).toFixed(2)} kg` : "—"}</small>
                                            </div>
                                        )}
                                        <div className="livestock-form-group">
                                            <label>Minimum Weight (kg)</label>
                                            <input name="minWeightKg" type="number" min="0.01" step="0.01" value={growthForm.minWeightKg} onChange={handleGrowthChange} />
                                        </div>
                                        <div className="livestock-form-group">
                                            <label>Maximum Weight (kg)</label>
                                            <input name="maxWeightKg" type="number" min="0.01" step="0.01" value={growthForm.maxWeightKg} onChange={handleGrowthChange} />
                                        </div>
                                    </div>
                                    <div className="livestock-form-group">
                                        <label>Measurement Notes</label>
                                        <textarea name="notes" rows="3" placeholder="Body condition, sample details, feeding change, recovery, or other observation..." value={growthForm.notes} onChange={handleGrowthChange} />
                                    </div>
                                    <div className="livestock-edit-footer"><button type="submit"><span className="material-symbols-outlined">add_chart</span>Save Measurement</button></div>
                                </form>
                            )}

                            <div className="livestock-growth-history-table-wrap">
                                <table className="livestock-growth-history-table">
                                    <thead><tr><th>Date</th><th>Actual Weight</th><th>Expected Stage</th><th>Expected Weight</th><th>Deviation</th><th>Measured</th><th>Change</th><th>ADG</th><th>Notes</th></tr></thead>
                                    <tbody>
                                        {weightHistory.filtered.length > 0 ? weightHistory.filtered.map((record) => (
                                            <tr key={record.id}>
                                                <td>{formatDate(record.measurementDate)}</td>
                                                <td>{Number(record.weightKg || 0).toFixed(2)} kg</td>
                                                <td>{record.expectedStage || "—"}</td>
                                                <td>{record.expectedMinWeightKg == null && record.expectedMaxWeightKg == null ? "—" : `${record.expectedMinWeightKg ?? "—"}–${record.expectedMaxWeightKg ?? "—"} kg`}</td>
                                                <td title={record.deviationMessage || ""}>{record.deviationStatus || "—"}</td>
                                                <td>{record.animalsMeasured || (animal.recordType === "Individual" ? 1 : "—")} / {animal.quantity}</td>
                                                <td>{record.weightChangeKg == null ? "Baseline" : `${Number(record.weightChangeKg).toFixed(2)} kg`}</td>
                                                <td>{record.averageDailyGainKg == null ? "—" : `${Number(record.averageDailyGainKg).toFixed(3)} kg/day`}</td>
                                                <td>{record.notes || "—"}{record.relatedTaskId && <a href={`/task-management?taskId=${record.relatedTaskId}&tab=tasks`}> View approved work</a>}</td>
                                            </tr>
                                        )) : <tr><td colSpan="9" className="livestock-growth-empty">No growth measurements recorded yet.</td></tr>}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )}

                    {activeTab ===
                        "vaccination" && (
                        <section className="livestock-detail-section">
                            <div className="livestock-detail-section-heading">
                                <div>
                                    <h3>
                                        Vaccination Records
                                    </h3>

                                    <p>
                                        Review vaccination
                                        history and upcoming
                                        schedules.
                                    </p>
                                </div>

                                <button
                                    type="button"
                                    className="livestock-record-add-button"
                                    onClick={() =>
                                        setShowVaccinationForm(
                                            (
                                                currentValue
                                            ) =>
                                                !currentValue
                                        )
                                    }
                                >
                                    <span className="material-symbols-outlined">
                                        add
                                    </span>

                                    Add Vaccination
                                </button>
                            </div>

                            <div className="livestock-vaccination-schedule">
                                <div className="livestock-vaccination-schedule-heading">
                                    <div>
                                        <h4>Vaccination Schedule</h4>
                                        <p>Workforce vaccination tasks assigned to this livestock record appear here and stay linked to employee completion.</p>
                                    </div>
                                    <button
                                        type="button"
                                        className="livestock-schedule-refresh"
                                        onClick={loadVaccinationSchedule}
                                        disabled={vaccinationScheduleLoading}
                                    >
                                        <span className="material-symbols-outlined">refresh</span>
                                        {vaccinationScheduleLoading ? "Loading..." : "Refresh"}
                                    </button>
                                </div>

                                {vaccinationScheduleError ? (
                                    <div className="livestock-schedule-message error">{vaccinationScheduleError}</div>
                                ) : vaccinationScheduleLoading && vaccinationSchedule.length === 0 ? (
                                    <div className="livestock-schedule-message">Loading vaccination schedule...</div>
                                ) : vaccinationSchedule.length > 0 ? (
                                    <div className="livestock-vaccination-schedule-list">
                                        {vaccinationSchedule.map((schedule, index) => (
                                            <article className="livestock-vaccination-schedule-item" key={schedule.taskId || `${schedule.scheduledDate}-${index}`}>
                                                <span className="vaccination-record-icon">
                                                    <span className="material-symbols-outlined">event_upcoming</span>
                                                </span>
                                                <div className="livestock-vaccination-schedule-content">
                                                    <div className="livestock-vaccination-schedule-title">
                                                        <strong>{schedule.title}</strong>
                                                        {schedule.activityCode && <small>{schedule.activityCode}</small>}
                                                    </div>
                                                    <p>Scheduled {formatDate(schedule.scheduledDate)}{schedule.assignedEmployeeName ? ` • Assigned to ${schedule.assignedEmployeeName}` : " • Unassigned"}</p>
                                                    {(schedule.inventoryItemName || schedule.plannedQuantity != null) && (
                                                        <small>
                                                            {schedule.inventoryItemName || "Vaccine resource"}
                                                            {schedule.plannedQuantity != null ? ` • Planned ${schedule.plannedQuantity} ${schedule.plannedUnit || ""}` : ""}
                                                        </small>
                                                    )}
                                                    {schedule.status === "Completed" && (
                                                        <small className="livestock-vaccination-completed-detail">
                                                            Completed{schedule.performedBy ? ` by ${schedule.performedBy}` : ""}
                                                            {schedule.actualQuantity != null ? ` • Actual ${schedule.actualQuantity} ${schedule.actualUnit || schedule.plannedUnit || ""}` : ""}
                                                        </small>
                                                    )}
                                                </div>
                                                <span className={`vaccination-status-label ${getClassName(schedule.status)}`}>{schedule.status}</span>
                                            </article>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="livestock-schedule-message">No vaccination schedule is currently assigned to this livestock record.</div>
                                )}
                            </div>

                            <div className="vaccination-record-list">
                                {vaccinationRecords.length >
                                0 ? (
                                    vaccinationRecords.map(
                                        (
                                            record
                                        ) => (
                                            <article
                                                className="vaccination-record-item"
                                                key={
                                                    record.id
                                                }
                                            >
                                                <span className="vaccination-record-icon">
                                                    <span className="material-symbols-outlined">
                                                        vaccines
                                                    </span>
                                                </span>

                                                <div className="vaccination-record-content">
                                                    <div>
                                                        <strong>
                                                            {
                                                                record.vaccine
                                                            }
                                                        </strong>

                                                        <small>
                                                            Administered{" "}
                                                            {formatDate(
                                                                record.dateAdministered
                                                            )}
                                                        </small>
                                                    </div>

                                                    <p>
                                                        {
                                                            record.notes
                                                        }
                                                    </p>

                                                    <small>
                                                        Administered
                                                        by:{" "}
                                                        {
                                                            record.administeredBy
                                                        }
                                                    </small>
                                                </div>

                                                <div className="vaccination-record-right">
                                                    <span
                                                        className={`vaccination-status-label ${getClassName(
                                                            record.status
                                                        )}`}
                                                    >
                                                        {
                                                            record.status
                                                        }
                                                    </span>

                                                    <small>
                                                        Next due
                                                    </small>

                                                    <strong>
                                                        {formatDate(
                                                            record.nextDue
                                                        )}
                                                    </strong>
                                                </div>
                                            </article>
                                        )
                                    )
                                ) : (
                                    <div className="livestock-empty-record">
                                        <span className="material-symbols-outlined">
                                            vaccines
                                        </span>

                                        <p>
                                            No vaccination
                                            records available.
                                        </p>
                                    </div>
                                )}
                            </div>

                            {showVaccinationForm && (
                                <form
                                    className="livestock-inline-form"
                                    onSubmit={
                                        handleVaccinationSubmit
                                    }
                                >
                                    <h4>
                                        New Vaccination
                                        Record
                                    </h4>

                                    <div className="livestock-form-grid">
                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccineName">
                                                Selected Vaccine
                                                <span>
                                                    *
                                                </span>
                                            </label>

                                            <input
                                                id="vaccineName"
                                                name="vaccine"
                                                type="text"
                                                placeholder="Choose a Vaccine Inventory item"
                                                value={vaccinationForm.vaccine}
                                                readOnly
                                            />
                                        </div>

                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccinationInventoryItem">
                                                Vaccine Inventory <span>*</span>
                                            </label>
                                            <select
                                                id="vaccinationInventoryItem"
                                                name="inventoryItemId"
                                                value={vaccinationForm.inventoryItemId}
                                                onChange={handleVaccinationChange}
                                                required
                                            >
                                                <option value="">Select available vaccine stock</option>
                                                {vaccineInventory.map((item) => (
                                                    <option key={item.id} value={item.id}>
                                                        {item.name} — {item.quantity} {item.unit}
                                                        {item.batchNumber ? ` — Batch ${item.batchNumber}` : ""}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>

                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccinationInventoryQuantity">
                                                Inventory Quantity Used
                                            </label>
                                            <input
                                                id="vaccinationInventoryQuantity"
                                                name="inventoryQuantity"
                                                type="number"
                                                min="0.01"
                                                step="0.01"
                                                value={vaccinationForm.inventoryQuantity}
                                                onChange={handleVaccinationChange}
                                                disabled={!vaccinationForm.inventoryItemId}
                                                placeholder="Example: 1"
                                            />
                                            {vaccinationForm.inventoryItemId && (() => {
                                                const selected = vaccineInventory.find(
                                                    (item) => String(item.id) === String(vaccinationForm.inventoryItemId)
                                                );
                                                return selected ? (
                                                    <small className="vaccination-inventory-stock-note">
                                                        Available: {selected.quantity} {selected.unit}
                                                        {selected.expirationDate
                                                            ? ` • Expires ${formatDate(selected.expirationDate)}`
                                                            : ""}
                                                    </small>
                                                ) : null;
                                            })()}
                                        </div>

                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccinationDate">
                                                Date
                                                Administered
                                                <span>
                                                    *
                                                </span>
                                            </label>

                                            <input
                                                id="vaccinationDate"
                                                name="dateAdministered"
                                                type="date"
                                                value={
                                                    vaccinationForm.dateAdministered
                                                }
                                                onChange={
                                                    handleVaccinationChange
                                                }
                                                required
                                            />
                                        </div>

                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccinationNextDue">
                                                Next Due
                                            </label>

                                            <input
                                                id="vaccinationNextDue"
                                                name="nextDue"
                                                type="date"
                                                value={
                                                    vaccinationForm.nextDue
                                                }
                                                onChange={
                                                    handleVaccinationChange
                                                }
                                            />
                                        </div>

                                        <div className="livestock-form-group">
                                            <label htmlFor="vaccinationStatus">
                                                Status
                                            </label>

                                            <select
                                                id="vaccinationStatus"
                                                name="status"
                                                value={
                                                    vaccinationForm.status
                                                }
                                                onChange={
                                                    handleVaccinationChange
                                                }
                                            >
                                                {vaccinationStatuses.map(
                                                    (
                                                        status
                                                    ) => (
                                                        <option
                                                            key={
                                                                status
                                                            }
                                                            value={
                                                                status
                                                            }
                                                        >
                                                            {
                                                                status
                                                            }
                                                        </option>
                                                    )
                                                )}
                                            </select>
                                        </div>

                                        <div className="livestock-form-group full-width">
                                            <label htmlFor="vaccinationAdministeredBy">
                                                Administered
                                                By
                                            </label>

                                            <input
                                                id="vaccinationAdministeredBy"
                                                name="administeredBy"
                                                type="text"
                                                placeholder="Enter veterinarian or staff name"
                                                value={
                                                    vaccinationForm.administeredBy
                                                }
                                                onChange={
                                                    handleVaccinationChange
                                                }
                                            />
                                        </div>
                                    </div>

                                    <div className="livestock-form-group">
                                        <label htmlFor="vaccinationNotes">
                                            Notes
                                        </label>

                                        <textarea
                                            id="vaccinationNotes"
                                            name="notes"
                                            rows="3"
                                            placeholder="Enter vaccination notes..."
                                            value={
                                                vaccinationForm.notes
                                            }
                                            onChange={
                                                handleVaccinationChange
                                            }
                                        />
                                    </div>

                                    <div className="livestock-inline-buttons">
                                        <button
                                            type="button"
                                            disabled={savingVaccination}
                                            onClick={() =>
                                                setShowVaccinationForm(
                                                    false
                                                )
                                            }
                                        >
                                            Cancel
                                        </button>

                                        <button type="submit" disabled={savingVaccination}>
                                            {savingVaccination ? "Saving…" : "Save Vaccination"}
                                        </button>
                                    </div>
                                </form>
                            )}
                        </section>
                    )}

                    {activeTab === "feeding" && (
                        <section className="livestock-detail-section">
                            <div className="livestock-detail-section-heading">
                                <div>
                                    <h3>Feeding Schedule</h3>
                                    <p>Choose the exact Feed Inventory item and standardized daily periods. Actual Inventory deduction happens only when each feeding occurrence is confirmed.</p>
                                </div>
                            </div>
                            <form className="livestock-edit-form" onSubmit={handleFeedingSubmit}>
                                <div className="livestock-form-grid">
                                    <div className="livestock-form-group">
                                        <label>Feed Inventory Item</label>
                                        <select name="inventoryItemId" value={feedingForm.inventoryItemId} onChange={handleFeedingChange} required>
                                            <option value="">Select available feed stock</option>
                                            {feedInventory.map((item) => <option key={item.id} value={item.id}>{item.name} — {item.quantity} {item.unit} available</option>)}
                                        </select>
                                    </div>
                                    <div className="livestock-form-group">
                                        <label>Feedings Per Day</label>
                                        <select name="frequency" value={feedingForm.frequency} onChange={handleFeedingChange}>
                                            {feedingFrequencies.map((item) => <option key={item.value} value={item.value}>{item.value}</option>)}
                                        </select>
                                    </div>
                                    <div className="livestock-form-group">
                                        <label>Daily Feed per Animal</label>
                                        <div className="livestock-unit-input"><input name="dailyAmountKg" type="number" min="0.001" step="0.001" value={feedingForm.dailyAmountKg} onChange={handleFeedingChange} required /><span>kg</span></div>
                                    </div>
                                </div>
                                <div className="livestock-form-group">
                                    <label>Feeding Periods</label>
                                    <div className="livestock-choice-chips">
                                        {feedingPeriods.map((period) => <button key={period} type="button" className={(feedingForm.periods || []).includes(period) ? "active" : ""} onClick={() => toggleDetailFeedingPeriod(period)}>{period}{(feedingForm.periods || []).includes(period) ? " ✓" : ""}</button>)}
                                    </div>
                                    <small className="livestock-field-help">Select exactly {feedingCount(feedingForm.frequency)} period(s). Current linked feed: {feedingForm.feedType || "none"}.</small>
                                </div>
                                <div className="livestock-form-group"><label>Feeding Notes</label><textarea name="notes" rows="4" value={feedingForm.notes} onChange={handleFeedingChange} /></div>
                                <div className="livestock-edit-footer"><button type="submit"><span className="material-symbols-outlined">save</span>Save Feeding Schedule</button></div>
                            </form>
                        </section>
                    )}

                    {activeTab ===
                        "resources" && (
                        <ResourceUsagePanel
                            module="Livestock"
                            target={animal}
                            canEdit={canEditResources}
                        />
                    )}

                    {activeTab ===
                        "reproduction" && (
                        <LivestockReproductionPanel
                            animal={
                                animal
                            }
                            onSave={
                                onSaveReproduction
                            }
                        />
                    )}

                    {activeTab ===
                        "production" && (
                        <LivestockProductionPanel
                            animal={
                                animal
                            }
                            onSave={
                                onSaveProduction
                            }
                        />
                    )}

                    {activeTab === "health" && (
                        <section className="livestock-detail-section">
                            <div className="livestock-detail-section-heading">
                                <div>
                                    <h3>Health Notes</h3>
                                    <p>{animal.recordType === "Batch" ? "Update the current head-count health breakdown for the batch so one sick animal does not mark the whole group as sick." : "Update the current health condition, last checkup, and observations."}</p>
                                </div>
                            </div>
                            <form className="livestock-edit-form" onSubmit={handleHealthSubmit}>
                                {animal.recordType === "Batch" ? (
                                    <>
                                        <div className="livestock-health-count-summary"><strong>Batch quantity: {animal.quantity} head</strong><span>The four current-health counts must total {animal.quantity}.</span></div>
                                        <div className="livestock-form-grid health-count-grid">
                                            <div className="livestock-form-group"><label>Healthy</label><input name="healthyQuantity" type="number" min="0" max={animal.quantity} value={healthForm.healthyQuantity} onChange={handleHealthChange} /></div>
                                            <div className="livestock-form-group"><label>At Risk</label><input name="atRiskQuantity" type="number" min="0" max={animal.quantity} value={healthForm.atRiskQuantity} onChange={handleHealthChange} /></div>
                                            <div className="livestock-form-group"><label>Sick</label><input name="sickQuantity" type="number" min="0" max={animal.quantity} value={healthForm.sickQuantity} onChange={handleHealthChange} /></div>
                                            <div className="livestock-form-group"><label>Under Treatment</label><input name="underTreatmentQuantity" type="number" min="0" max={animal.quantity} value={healthForm.underTreatmentQuantity} onChange={handleHealthChange} /></div>
                                        </div>
                                    </>
                                ) : (
                                    <div className="livestock-form-group"><label>Health Status</label><select name="healthStatus" value={healthForm.healthStatus} onChange={handleHealthChange}>{healthStatuses.filter((status) => status !== "Mixed").map((status) => <option key={status} value={status}>{status}</option>)}</select></div>
                                )}
                                <div className="livestock-form-grid">
                                    <div className="livestock-form-group"><label>Last Checkup</label><input name="lastCheckup" type="date" max={getTodayDate()} value={healthForm.lastCheckup} onChange={handleHealthChange} /></div>
                                </div>
                                <div className="livestock-form-group"><label>Health Observation / Symptoms / Treatment Notes</label><textarea name="healthNotes" rows="7" placeholder="Record findings, symptoms, diagnosis, treatment, isolation, or follow-up instructions..." value={healthForm.healthNotes} onChange={handleHealthChange} /></div>
                                <div className="livestock-edit-footer"><button type="submit"><span className="material-symbols-outlined">save</span>Save Health Record</button></div>
                            </form>
                        </section>
                    )}
                </div>

                <footer className="livestock-details-footer">
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
