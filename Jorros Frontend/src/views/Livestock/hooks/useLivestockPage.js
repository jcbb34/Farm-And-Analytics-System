"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { confirmAction } from "../../../context/NotificationContext.jsx";
import { useAuth } from "../../../context/AuthContext.jsx";
import { livestockService } from "../../../services/livestockService.js";
import {
    addTimelineEntry,
    logAudit,
} from "../../../services/farmIntelligenceService.js";
import {
    clearStableIdempotencyKey,
    stableIdempotencyKey,
} from "../../../services/idempotencyKey.js";

export const healthStatuses = [
    "Healthy",
    "Mixed",
    "Under Treatment",
    "At Risk",
    "Sick",
];

function calculateAge(dateOfBirth) {
    if (!dateOfBirth) {
        return "Not specified";
    }

    const birthDate = new Date(`${dateOfBirth}T00:00:00`);
    const today = new Date();

    let months =
        (today.getFullYear() - birthDate.getFullYear()) * 12 +
        today.getMonth() -
        birthDate.getMonth();

    if (today.getDate() < birthDate.getDate()) {
        months -= 1;
    }

    if (months < 1) {
        const days = Math.max(
            0,
            Math.floor((today - birthDate) / 86400000)
        );

        return `${days} ${days === 1 ? "Day" : "Days"}`;
    }

    if (months < 12) {
        return `${months} ${months === 1 ? "Month" : "Months"}`;
    }

    const years = Math.floor(months / 12);
    const remainingMonths = months % 12;

    if (remainingMonths === 0) {
        return `${years} ${years === 1 ? "Year" : "Years"}`;
    }

    return `${years} ${years === 1 ? "Year" : "Years"}, ${remainingMonths} ${
        remainingMonths === 1 ? "Month" : "Months"
    }`;
}

function isRecentBirth(dateOfBirth) {
    if (!dateOfBirth) {
        return false;
    }

    const birthDate = new Date(`${dateOfBirth}T00:00:00`);
    const difference = Date.now() - birthDate.getTime();

    return (
        difference >= 0 &&
        difference <= 90 * 24 * 60 * 60 * 1000
    );
}

// Handles Livestock page data, filters, modals, and record actions.
export default function useLivestockPage() {
    const { isAdministrator, hasPermission } = useAuth();
    const livestockCreateRequestRef = useRef(null);

    const canUpdateLivestock =
        isAdministrator || hasPermission?.("livestock:update");

    const [livestock, setLivestock] = useState([]);
    const [livestockLoading, setLivestockLoading] = useState(true);
    const [livestockError, setLivestockError] = useState("");

    // Filters
    const [searchText, setSearchText] = useState("");
    const [typeFilter, setTypeFilter] = useState("All");
    const [statusFilter, setStatusFilter] = useState("All");
    const [penFilter, setPenFilter] = useState("All");

    // Modal state
    const [livestockFormOpen, setLivestockFormOpen] = useState(false);
    const [editingAnimal, setEditingAnimal] = useState(null);
    const [selectedAnimal, setSelectedAnimal] = useState(null);
    const [movementAnimal, setMovementAnimal] = useState(null);
    const [penManagementOpen, setPenManagementOpen] = useState(false);

    const decorateLivestockRecord = useCallback(
        (record) => ({
            ...record,
            age: calculateAge(record.dateOfBirth),
            isNewBirth: isRecentBirth(record.dateOfBirth),
        }),
        []
    );

    const loadLivestock = useCallback(async () => {
        try {
            setLivestockLoading(true);
            setLivestockError("");

            const livestockList = await livestockService.getLivestock(
                false,
                true
            );

            const detailedLivestock = livestockList.map(
                decorateLivestockRecord
            );

            setLivestock(detailedLivestock);
            return detailedLivestock;
        } catch (error) {
            console.error("Failed to load livestock:", error);
            setLivestockError(
                error?.message || "Unable to load livestock records."
            );
            return [];
        } finally {
            setLivestockLoading(false);
        }
    }, [decorateLivestockRecord]);

    useEffect(() => {
        loadLivestock();
    }, [loadLivestock]);

    const livestockTypes = useMemo(
        () => [
            ...new Set(
                livestock
                    .map((animal) => animal.type)
                    .filter(Boolean)
            ),
        ],
        [livestock]
    );

    const penLocations = useMemo(
        () => [
            ...new Set(
                livestock
                    .map((animal) => animal.penLocation)
                    .filter(Boolean)
            ),
        ],
        [livestock]
    );

    const filteredLivestock = useMemo(() => {
        const search = searchText.trim().toLowerCase();

        return livestock.filter((animal) => {
            const animalId = String(animal.animalId || "").toLowerCase();
            const recordName = String(animal.recordName || "").toLowerCase();
            const type = String(animal.type || "").toLowerCase();
            const breed = String(animal.breed || "").toLowerCase();
            const penLocation = String(
                animal.penLocation || ""
            ).toLowerCase();

            const matchesSearch =
                !search ||
                animalId.includes(search) ||
                recordName.includes(search) ||
                type.includes(search) ||
                breed.includes(search) ||
                penLocation.includes(search);

            const matchesType =
                typeFilter === "All" || animal.type === typeFilter;

            const matchesStatus =
                statusFilter === "All" ||
                (statusFilter === "Healthy" && Number(animal.healthyQuantity || 0) > 0) ||
                (statusFilter === "At Risk" && Number(animal.atRiskQuantity || 0) > 0) ||
                (statusFilter === "Sick" && Number(animal.sickQuantity || 0) > 0) ||
                (statusFilter === "Under Treatment" && Number(animal.underTreatmentQuantity || 0) > 0) ||
                (statusFilter === "Mixed" && animal.healthStatus === "Mixed");

            const matchesPen =
                penFilter === "All" || animal.penLocation === penFilter;

            return (
                matchesSearch &&
                matchesType &&
                matchesStatus &&
                matchesPen
            );
        });
    }, [
        livestock,
        searchText,
        typeFilter,
        statusFilter,
        penFilter,
    ]);

    const statistics = useMemo(() => {
        const totalAnimalCount = livestock.reduce(
            (total, animal) => total + Number(animal.quantity || 0),
            0
        );

        const healthy = livestock.reduce(
            (total, animal) => total + Number(animal.healthyQuantity || 0),
            0
        );

        const sickOrAtRisk = livestock.reduce(
            (total, animal) =>
                total +
                Number(animal.sickQuantity || 0) +
                Number(animal.atRiskQuantity || 0) +
                Number(animal.underTreatmentQuantity || 0),
            0
        );

        const vaccinationDue = livestock.reduce(
            (total, animal) =>
                ["Due", "Due Soon"].includes(animal.vaccinationStatus)
                    ? total + Number(animal.quantity || 0)
                    : total,
            0
        );

        const births = livestock.reduce(
            (total, animal) =>
                animal.isNewBirth
                    ? total + Number(animal.quantity || 0)
                    : total,
            0
        );

        return [
            {
                id: 1,
                title: "Total Livestock",
                value: totalAnimalCount,
                icon: "pets",
                className: "total",
            },
            {
                id: 2,
                title: "Healthy Animals",
                value: healthy,
                icon: "health_and_safety",
                className: "healthy",
            },
            {
                id: 3,
                title: "Sick / At Risk",
                value: sickOrAtRisk,
                icon: "medical_information",
                className: "risk",
            },
            {
                id: 4,
                title: "Due for Vaccination",
                value: vaccinationDue,
                icon: "vaccines",
                className: "vaccination",
            },
            {
                id: 5,
                title: "Total Births",
                value: births,
                icon: "child_care",
                className: "births",
            },
        ];
    }, [livestock]);

    const clearFilters = () => {
        setSearchText("");
        setTypeFilter("All");
        setStatusFilter("All");
        setPenFilter("All");
    };

    const openAddLivestock = () => {
        setEditingAnimal(null);
        setLivestockFormOpen(true);
    };

    const openEditLivestock = (animal) => {
        setEditingAnimal(animal);
        setLivestockFormOpen(true);
    };

    const closeLivestockForm = () => {
        setLivestockFormOpen(false);
        setEditingAnimal(null);
    };

    const handleSaveLivestock = async (livestockData) => {
        const normalizedRecord = {
            ...livestockData,
            age: calculateAge(livestockData.dateOfBirth),
            isNewBirth: isRecentBirth(livestockData.dateOfBirth),
        };

        const animalBeingEdited = editingAnimal;

        try {
            let savedAnimal;

            if (animalBeingEdited) {
                savedAnimal = await livestockService.updateLivestock(
                    animalBeingEdited.id,
                    normalizedRecord
                );
            } else {
                const idempotencyKey = stableIdempotencyKey(
                    livestockCreateRequestRef,
                    normalizedRecord,
                    "livestock-create"
                );
                savedAnimal = await livestockService.createLivestock(
                    normalizedRecord,
                    { idempotencyKey }
                );
                clearStableIdempotencyKey(livestockCreateRequestRef);
            }

            const refreshedLivestock = await loadLivestock();
            const refreshedAnimal = refreshedLivestock.find(
                (record) => record.id === savedAnimal.id
            );

            if (selectedAnimal?.id === savedAnimal.id) {
                setSelectedAnimal(
                    refreshedAnimal || decorateLivestockRecord(savedAnimal)
                );
            }

            if (animalBeingEdited) {
                notify("Livestock record updated successfully.");
            } else {
                notify("Livestock record added successfully.");
            }

            closeLivestockForm();
        } catch (error) {
            console.error("Failed to save livestock:", error);
            notify(
                error?.message || "Unable to save livestock record."
            );
        }
    };

    const replaceAnimalInState = useCallback(
        (updatedAnimal) => {
            const decoratedAnimal = decorateLivestockRecord(updatedAnimal);

            setLivestock((currentLivestock) =>
                currentLivestock.map((animal) =>
                    animal.id === decoratedAnimal.id
                        ? decoratedAnimal
                        : animal
                )
            );

            setSelectedAnimal((currentAnimal) =>
                currentAnimal?.id === decoratedAnimal.id
                    ? decoratedAnimal
                    : currentAnimal
            );

            return decoratedAnimal;
        },
        [decorateLivestockRecord]
    );

    const handleSaveVaccination = async (
        animalId,
        vaccinationRecord
    ) => {
        const vaccinatedAnimal = livestock.find(
            (animal) => animal.id === animalId
        );

        try {
            await livestockService.addVaccinationRecord(
                animalId,
                vaccinationRecord
            );

            const updatedAnimal = await livestockService.getLivestockRecord(
                animalId
            );

            replaceAnimalInState(updatedAnimal);

            if (vaccinatedAnimal) {
                logAudit({
                    action: "Saved vaccination record",
                    module: "Livestock",
                    recordName: vaccinatedAnimal.recordName,
                    entityId: vaccinatedAnimal.animalId,
                    details:
                        vaccinationRecord.vaccine ||
                        vaccinationRecord.vaccineName ||
                        "Vaccination",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: vaccinatedAnimal.recordName,
                    entityId: vaccinatedAnimal.animalId,
                    title: "Vaccination recorded",
                    details:
                        vaccinationRecord.vaccine ||
                        vaccinationRecord.vaccineName ||
                        "Vaccination record saved.",
                    icon: "vaccines",
                });
            }

            notify("Vaccination record saved successfully.");
            return true;
        } catch (error) {
            console.error("Failed to save vaccination:", error);
            notify(
                error?.message || "Unable to save vaccination record."
            );
            return false;
        }
    };

    const handleSaveReproduction = async (
        animalId,
        reproductionRecord
    ) => {
        const selectedRecord = livestock.find(
            (animal) => animal.id === animalId
        );

        try {
            await livestockService.addReproductionRecord(
                animalId,
                reproductionRecord
            );

            const updatedAnimal = await livestockService.getLivestockRecord(
                animalId
            );

            replaceAnimalInState(updatedAnimal);

            if (selectedRecord) {
                logAudit({
                    action: "Saved reproduction record",
                    module: "Livestock",
                    recordName: selectedRecord.recordName,
                    entityId: selectedRecord.animalId,
                    details: `${reproductionRecord.recordType} • ${reproductionRecord.reproductiveStatus}`,
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: selectedRecord.recordName,
                    entityId: selectedRecord.animalId,
                    title: "Reproduction record saved",
                    details: `${reproductionRecord.recordType} recorded for ${reproductionRecord.eventDate}.`,
                    icon: "family_history",
                });
            }

            notify("Reproduction record saved successfully.");
        } catch (error) {
            console.error("Failed to save reproduction record:", error);
            notify(
                error?.message || "Unable to save reproduction record."
            );
            throw error;
        }
    };

    const handleSaveProduction = async (
        animalId,
        productionRecord
    ) => {
        const selectedRecord = livestock.find(
            (animal) => animal.id === animalId
        );

        try {
            await livestockService.addProductionRecord(
                animalId,
                productionRecord
            );

            const updatedAnimal = await livestockService.getLivestockRecord(
                animalId
            );

            replaceAnimalInState(updatedAnimal);

            if (selectedRecord) {
                logAudit({
                    action: "Saved livestock production output",
                    module: "Livestock",
                    recordName: selectedRecord.recordName,
                    entityId: selectedRecord.animalId,
                    details: `${productionRecord.outputType}: ${productionRecord.quantity} ${productionRecord.unit}`,
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: selectedRecord.recordName,
                    entityId: selectedRecord.animalId,
                    title: "Production output recorded",
                    details: `${productionRecord.outputType}: ${productionRecord.quantity} ${productionRecord.unit}`,
                    icon: "monitoring",
                });
            }

            notify("Production output saved successfully.");
        } catch (error) {
            console.error("Failed to save production output:", error);
            notify(
                error?.message || "Unable to save production output."
            );
            throw error;
        }
    };

    const handleSaveFeeding = async (animalId, feedingSchedule) => {
        const fedAnimal = livestock.find((animal) => animal.id === animalId);

        try {
            await livestockService.updateLivestock(animalId, {
                feedingSchedule,
            });

            const updatedAnimal = await livestockService.getLivestockRecord(
                animalId
            );

            replaceAnimalInState(updatedAnimal);

            if (fedAnimal) {
                logAudit({
                    action: "Updated feeding schedule",
                    module: "Livestock",
                    recordName: fedAnimal.recordName,
                    entityId: fedAnimal.animalId,
                    details: feedingSchedule.feedType || "Feeding schedule",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: fedAnimal.recordName,
                    entityId: fedAnimal.animalId,
                    title: "Feeding schedule updated",
                    details:
                        feedingSchedule.feedType ||
                        "Feeding schedule updated.",
                    icon: "restaurant",
                });
            }

            notify("Feeding schedule updated successfully.");
        } catch (error) {
            console.error("Failed to update feeding schedule:", error);
            notify(
                error?.message || "Unable to update feeding schedule."
            );
        }
    };

    const handleSaveHealth = async (animalId, healthRecord) => {
        const healthAnimal = livestock.find(
            (animal) => animal.id === animalId
        );

        try {
            const quantity = Number(healthAnimal?.quantity || 1);
            const healthStatus = healthRecord.healthStatus || healthAnimal?.healthStatus || "Healthy";
            const aggregateHealthUpdate = {
                ...healthRecord,
                healthyQuantity: healthStatus === "Healthy" ? quantity : 0,
                atRiskQuantity: healthStatus === "At Risk" ? quantity : 0,
                sickQuantity: healthStatus === "Sick" ? quantity : 0,
                underTreatmentQuantity: healthStatus === "Under Treatment" ? quantity : 0,
            };
            await livestockService.updateLivestock(animalId, aggregateHealthUpdate);

            const updatedAnimal = await livestockService.getLivestockRecord(
                animalId
            );

            replaceAnimalInState(updatedAnimal);

            if (healthAnimal) {
                logAudit({
                    action: "Updated livestock health record",
                    module: "Livestock",
                    recordName: healthAnimal.recordName,
                    entityId: healthAnimal.animalId,
                    details:
                        healthRecord.healthStatus ||
                        healthRecord.healthNotes ||
                        "Health record updated",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: healthAnimal.recordName,
                    entityId: healthAnimal.animalId,
                    title: "Health record updated",
                    details:
                        healthRecord.healthStatus ||
                        healthRecord.healthNotes ||
                        "Livestock health record updated.",
                    icon: "health_and_safety",
                });
            }

            notify("Health record updated successfully.");
        } catch (error) {
            console.error("Failed to update health record:", error);
            notify(
                error?.message || "Unable to update health record."
            );
        }
    };

    const handleTransferPen = async (data) => {
        if (!movementAnimal) return;

        try {
            const updated = await livestockService.transferPen(
                movementAnimal.id,
                data
            );
            await loadLivestock();

            logAudit({
                action: "Transferred livestock pen",
                module: "Livestock",
                recordName: movementAnimal.recordName,
                entityId: movementAnimal.animalId,
                details: `${movementAnimal.penLocation} → ${updated.penLocation}`,
            });
            addTimelineEntry({
                module: "Livestock",
                recordName: movementAnimal.recordName,
                entityId: movementAnimal.animalId,
                title: "Livestock transferred",
                details: `${movementAnimal.penLocation} → ${updated.penLocation}`,
                icon: "swap_horiz",
            });

            setMovementAnimal(null);
            notify("Livestock transferred successfully.");
        } catch (error) {
            console.error("Failed to transfer livestock:", error);
            notify(error?.message || "Unable to transfer livestock.");
            throw error;
        }
    };

    const handleSplitBatch = async (data) => {
        if (!movementAnimal) return;

        try {
            const created = await livestockService.splitBatch(
                movementAnimal.id,
                data
            );
            await loadLivestock();

            logAudit({
                action: "Split livestock batch",
                module: "Livestock",
                recordName: movementAnimal.recordName,
                entityId: movementAnimal.animalId,
                details: `${data.quantity} animal(s) moved to ${created.animalId}.`,
            });
            addTimelineEntry({
                module: "Livestock",
                recordName: created.recordName,
                entityId: created.animalId,
                title: "Livestock batch split",
                details: `${data.quantity} animal(s) split from ${movementAnimal.animalId}.`,
                icon: "call_split",
            });

            setMovementAnimal(null);
            notify("Batch split successfully.");
        } catch (error) {
            console.error("Failed to split livestock batch:", error);
            notify(error?.message || "Unable to split livestock batch.");
            throw error;
        }
    };

    const archiveLivestock = async (animalId) => {
        const animal = livestock.find((record) => record.id === animalId);

        if (!animal) {
            return;
        }

        const confirmed = await confirmAction({
            title: "Archive Livestock Record",
            message: `Archive ${animal.recordName} (${animal.animalId})?`,
            type: "warning",
            confirmText: "Archive",
            cancelText: "Cancel",
        });

        if (!confirmed) {
            return;
        }

        try {
            await livestockService.archiveLivestock(animalId);
            await loadLivestock();

            if (selectedAnimal?.id === animalId) {
                setSelectedAnimal(null);
            }

            if (editingAnimal?.id === animalId) {
                closeLivestockForm();
            }

            if (movementAnimal?.id === animalId) {
                setMovementAnimal(null);
            }

            logAudit({
                action: "Archived livestock record",
                module: "Livestock",
                recordName: animal.recordName,
                entityId: animal.animalId,
                details: animal.penLocation,
            });

            addTimelineEntry({
                module: "Livestock",
                recordName: animal.recordName,
                entityId: animal.animalId,
                title: "Livestock archived",
                details: `${animal.type} record archived.`,
                icon: "archive",
            });

            notify(`${animal.recordName} was archived successfully.`);
        } catch (error) {
            console.error("Failed to archive livestock:", error);
            notify(
                error?.message || "Unable to archive livestock record."
            );
        }
    };

    return {
        canUpdateLivestock,
        livestock,
        livestockLoading,
        livestockError,
        filteredLivestock,
        statistics,
        livestockTypes,
        penLocations,
        loadLivestock,

        searchText,
        setSearchText,
        typeFilter,
        setTypeFilter,
        statusFilter,
        setStatusFilter,
        penFilter,
        setPenFilter,
        clearFilters,

        livestockFormOpen,
        editingAnimal,
        selectedAnimal,
        setSelectedAnimal,
        movementAnimal,
        setMovementAnimal,
        penManagementOpen,
        setPenManagementOpen,
        openAddLivestock,
        openEditLivestock,
        closeLivestockForm,

        handleSaveLivestock,
        handleSaveVaccination,
        handleSaveFeeding,
        handleSaveHealth,
        handleSaveReproduction,
        handleSaveProduction,
        handleTransferPen,
        handleSplitBatch,
        archiveLivestock,
    };
}
