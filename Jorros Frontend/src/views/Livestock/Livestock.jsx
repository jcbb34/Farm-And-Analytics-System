"use client";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";
import { requestArchive } from "../../services/archiveService.js";

import { RecordFilters, RecordSearch, RecordHeader, RecordTableSurface } from "../../components/Records/RecordsLayout.jsx";

import ArchiveWorkspace from "../../components/Archives/Archives.jsx";

import { MonitoringStatus } from "../../components/Monitoring/Monitoring.jsx";

import { notify, notifyError } from "../../context/NotificationContext.jsx";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import { createPortal } from "react-dom";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";

import { confirmAction } from "../../context/NotificationContext.jsx";

import {
    addTimelineEntry,
    logAudit,
} from "../../services/farmIntelligenceService.js";
import { livestockService } from "../../services/livestockService.js";
import {
    clearStableIdempotencyKey,
    stableIdempotencyKey,
} from "../../services/idempotencyKey.js";

import {
    LivestockDetailsModal,
    LivestockFormModal,
} from "../../components/LivestockModals/LivestockModals.jsx";

import LivestockAnalytics from "../../components/LivestockAnalytics/LivestockAnalytics.jsx";
import PenManagementModal from "./components/PenManagementModal.jsx";
import LivestockMovementModal from "./components/LivestockMovementModal.jsx";
import useModalScrollLock from "../../hooks/useModalScrollLock.js";

import "./Livestock.css";

const healthStatuses = [
    "Healthy",
    "Mixed",
    "Under Treatment",
    "At Risk",
    "Sick",
];

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

function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "—";
    }

    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function calculateAge(dateOfBirth) {
    if (!dateOfBirth) {
        return "Not specified";
    }

    const birthDate = new Date(
        `${dateOfBirth}T00:00:00`
    );

    const today = new Date();

    let months =
        (today.getFullYear() -
            birthDate.getFullYear()) *
            12 +
        today.getMonth() -
        birthDate.getMonth();

    if (
        today.getDate() <
        birthDate.getDate()
    ) {
        months -= 1;
    }

    if (months < 1) {
        const days = Math.max(
            0,
            Math.floor(
                (today - birthDate) /
                    86400000
            )
        );

        return `${days} ${
            days === 1 ? "Day" : "Days"
        }`;
    }

    if (months < 12) {
        return `${months} ${
            months === 1
                ? "Month"
                : "Months"
        }`;
    }

    const years = Math.floor(
        months / 12
    );

    const remainingMonths =
        months % 12;

    if (remainingMonths === 0) {
        return `${years} ${
            years === 1
                ? "Year"
                : "Years"
        }`;
    }

    return `${years} ${
        years === 1 ? "Year" : "Years"
    }, ${remainingMonths} ${
        remainingMonths === 1
            ? "Month"
            : "Months"
    }`;
}

function isRecentBirth(dateOfBirth) {
    if (!dateOfBirth) {
        return false;
    }

    const birthDate = new Date(
        `${dateOfBirth}T00:00:00`
    );

    const difference =
        Date.now() -
        birthDate.getTime();

    return (
        difference >= 0 &&
        difference <=
            90 * 24 * 60 * 60 * 1000
    );
}

function getClassName(value = "") {
    return value
        .toLowerCase()
        .replaceAll(" ", "-");
}

function FeedingHistoryModal({ animal, onClose }) {
    const [details, setDetails] = useState(null);
    const [loading, setLoading] = useState(true);
    const [loadError, setLoadError] = useState("");
    const [retryCount, setRetryCount] = useState(0);
    const modalRef = useRef(null);
    const onCloseRef = useRef(onClose);
    onCloseRef.current = onClose;

    useModalScrollLock(true);

    useEffect(() => {
        let active = true;
        setLoading(true);
        setLoadError("");
        livestockService.getLivestockRecord(animal.id)
            .then((record) => {
                if (active) setDetails(record);
            })
            .catch((error) => {
                if (active) setLoadError(error?.message || "Unable to load feeding history.");
            })
            .finally(() => {
                if (active) setLoading(false);
            });
        return () => { active = false; };
    }, [animal.id, retryCount]);

    useEffect(() => {
        const previousFocus = document.activeElement;
        modalRef.current?.focus({ preventScroll: true });
        const handleKeyDown = (event) => {
            if (event.key === "Escape") onCloseRef.current();
        };
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("keydown", handleKeyDown);
            if (previousFocus instanceof HTMLElement && previousFocus.isConnected) {
                previousFocus.focus({ preventScroll: true });
            }
        };
    }, []);

    const records = useMemo(() => [...(details?.feedingRecords || [])].sort(
        (first, second) =>
            String(second.confirmedAt || "").localeCompare(String(first.confirmedAt || ""))
    ), [details]);

    return createPortal(
        <div
            className="feeding-history-overlay"
            onMouseDown={(event) => event.target === event.currentTarget && onClose()}
        >
            <div
                ref={modalRef}
                role="dialog"
                aria-modal="true"
                aria-labelledby="feeding-history-title"
                tabIndex={-1}
                className="feeding-history-modal"
            >
                <header className="feeding-history-modal-header">
                    <div>
                        <span className="feeding-history-eyebrow">Feeding Records</span>
                        <h2 id="feeding-history-title">{animal.recordName}</h2>
                        <p>
                            Permanent confirmed feeding history for this livestock batch.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="feeding-history-close"
                        onClick={onClose}
                        aria-label="Close feeding history"
                    >
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </header>

                <div className="feeding-history-table-wrap">
                    <table className="feeding-history-table">
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>Feeding</th>
                                <th>Feed Item</th>
                                <th>Planned</th>
                                <th>Actual Used</th>
                                <th>Status</th>
                                <th>Confirmed At</th>
                                <th>Notes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {loading || loadError ? (
                                <tr>
                                    <td colSpan="8" className="feeding-history-table-empty" role="status">
                                        {loading ? "Loading feeding records..." : (
                                            <>
                                                {loadError}{" "}
                                                <button type="button" onClick={() => setRetryCount((count) => count + 1)}>Retry</button>
                                            </>
                                        )}
                                    </td>
                                </tr>
                            ) : records.length > 0 ? (
                                records.map((record) => (
                                    <tr key={record.id}>
                                        <td>{formatDate(record.feedingDate)}</td>
                                        <td>{record.feedingSlot || "—"}</td>
                                        <td>{record.feedType || "—"}</td>
                                        <td>
                                            {Number(record.plannedQuantityKg || 0).toFixed(3)} kg
                                        </td>
                                        <td>
                                            <strong>
                                                {Number(record.actualQuantityKg || 0).toFixed(3)} kg
                                            </strong>
                                        </td>
                                        <td>
                                            <span className="feeding-history-status">
                                                Confirmed
                                            </span>
                                        </td>
                                        <td>{formatDateTime(record.confirmedAt)}</td>
                                        <td className="feeding-history-notes">
                                            {record.notes || "—"}
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan="8" className="feeding-history-table-empty">
                                        No confirmed feeding records yet.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                <footer className="feeding-history-modal-footer">
                    <span>{loading ? "Loading records..." : loadError ? "History unavailable" : `${records.length} confirmed record(s)`}</span>
                    <button type="button" onClick={onClose}>
                        Close
                    </button>
                </footer>
            </div>
        </div>,
        document.body
    );
}

function Livestock() {
    const livestockCreateRequestRef = useRef(null);
    const livestockSaveInFlight = useRef(false);
    const [savingLivestock, setSavingLivestock] = useState(false);

    const [
        livestock,
        setLivestock,
    ] = useState([]);

    const [
        livestockLoading,
        setLivestockLoading,
    ] = useState(true);

    const [
        livestockError,
        setLivestockError,
    ] = useState("");

    const [
        searchText,
        setSearchText,
    ] = useState("");

    const [
        typeFilter,
        setTypeFilter,
    ] = useState("All");

    const [
        statusFilter,
        setStatusFilter,
    ] = useState("All");

    const [
        penFilter,
        setPenFilter,
    ] = useState("All");

    const [
        openProfile,
        setOpenProfile,
    ] = useState(false);

    const [
        livestockFormOpen,
        setLivestockFormOpen,
    ] = useState(false);

    const [
        editingAnimal,
        setEditingAnimal,
    ] = useState(null);

    const [
        selectedAnimal,
        setSelectedAnimal,
    ] = useState(null);

    const [selectedFeedingHistoryAnimal, setSelectedFeedingHistoryAnimal] = useState(null);
    const vaccinationRequestRef = useRef(null);
    const vaccinationInFlightRef = useRef(false);
    const [savingVaccination, setSavingVaccination] = useState(false);
    const [penManagementOpen, setPenManagementOpen] = useState(false);
    const [movementAnimal, setMovementAnimal] = useState(null);

    const decorateLivestockRecord =
        useCallback((record) => ({
            ...record,
            age: calculateAge(
                record.dateOfBirth
            ),
            isNewBirth:
                isRecentBirth(
                    record.dateOfBirth
                ),
        }), []);

    const loadLivestock =
        useCallback(async () => {
            try {
                setLivestockLoading(true);
                setLivestockError("");

                const livestockList =
                    await livestockService.getLivestock();

                // Card data comes from one list request. Histories are fetched
                // only when an authorized user opens the corresponding record.
                const detailedLivestock = livestockList.map(decorateLivestockRecord);

                setLivestock(
                    detailedLivestock
                );

                return detailedLivestock;
            } catch (error) {
                console.error(
                    "Failed to load livestock:",
                    error
                );

                setLivestockError(
                    error?.message ||
                        "Unable to load livestock records."
                );

                return [];
            } finally {
                setLivestockLoading(false);
            }
        }, [decorateLivestockRecord]);

    const openDetailedAnimal = useCallback(async (animal, setTarget) => {
        try {
            const details = await livestockService.getLivestockRecord(animal.id);
            setTarget(decorateLivestockRecord(details));
        } catch (error) {
            notify(error?.message || "Unable to load livestock details.");
        }
    }, [decorateLivestockRecord]);

    useEffect(() => {
        loadLivestock();
    }, [loadLivestock]);

    useEffect(() => {
        const refreshFromWorkflow = async () => {
            const rows = await loadLivestock();
            setSelectedAnimal((current) =>
                current ? (rows.find((row) => row.id === current.id) || null) : current
            );
        };
        window.addEventListener("joross:livestock-updated", refreshFromWorkflow);
        return () => window.removeEventListener("joross:livestock-updated", refreshFromWorkflow);
    }, [loadLivestock]);

    const livestockTypes =
        useMemo(() => {
            return [
                ...new Set(
                    livestock.map(
                        (animal) =>
                            animal.type
                    )
                ),
            ];
        }, [livestock]);

    const penLocations =
        useMemo(() => {
            return [
                ...new Set(
                    livestock.map(
                        (animal) =>
                            animal.penLocation
                    )
                ),
            ];
        }, [livestock]);

    const filteredLivestock =
        useMemo(() => {
            const search =
                searchText
                    .trim()
                    .toLowerCase();

            return livestock.filter(
                (animal) => {
                    const matchesSearch =
                        !search ||
                        animal.animalId
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        animal.recordName
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        animal.type
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        animal.breed
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        animal.penLocation
                            .toLowerCase()
                            .includes(
                                search
                            );

                    const matchesType =
                        typeFilter ===
                            "All" ||
                        animal.type ===
                            typeFilter;

                    const statusCounts = {
                        Healthy: Number(animal.healthyQuantity || 0),
                        "At Risk": Number(animal.atRiskQuantity || 0),
                        Sick: Number(animal.sickQuantity || 0),
                        "Under Treatment": Number(animal.underTreatmentQuantity || 0),
                    };
                    const matchesStatus =
                        statusFilter === "All" ||
                        animal.healthStatus === statusFilter ||
                        (statusFilter !== "Mixed" && Number(statusCounts[statusFilter] || 0) > 0);

                    const matchesPen =
                        penFilter ===
                            "All" ||
                        animal.penLocation ===
                            penFilter;

                    return (
                        matchesSearch &&
                        matchesType &&
                        matchesStatus &&
                        matchesPen
                    );
                }
            );
        }, [
            livestock,
            searchText,
            typeFilter,
            statusFilter,
            penFilter,
        ]);

    const statistics = useMemo(() => {
        const totalAnimalCount =
            livestock.reduce(
                (total, animal) =>
                    total +
                    Number(
                        animal.quantity
                    ),
                0
            );

        const healthy = livestock.reduce((total, animal) => {
            const explicit = Number(animal.healthyQuantity || 0);
            if (explicit > 0 || animal.healthStatus === "Mixed") return total + explicit;
            return animal.healthStatus === "Healthy" ? total + Number(animal.quantity || 0) : total;
        }, 0);

        const sickOrAtRisk = livestock.reduce((total, animal) => {
            const breakdown =
                Number(animal.sickQuantity || 0) +
                Number(animal.atRiskQuantity || 0) +
                Number(animal.underTreatmentQuantity || 0);
            if (breakdown > 0 || animal.healthStatus === "Mixed") return total + breakdown;
            return ["Sick", "At Risk", "Under Treatment"].includes(animal.healthStatus)
                ? total + Number(animal.quantity || 0)
                : total;
        }, 0);

        const vaccinationDue =
            livestock.reduce(
                (total, animal) =>
                    [
                        "Due",
                        "Due Soon",
                    ].includes(
                        animal.vaccinationStatus
                    )
                        ? total +
                          Number(
                              animal.quantity
                          )
                        : total,
                0
            );

        const births =
            livestock.reduce(
                (total, animal) =>
                    animal.isNewBirth
                        ? total +
                          Number(
                              animal.quantity
                          )
                        : total,
                0
            );

        return [
            {
                id: 1,
                title:
                    "Total Livestock",
                value:
                    totalAnimalCount,
                icon: "pets",
                className: "total",
            },
            {
                id: 2,
                title:
                    "Healthy Animals",
                value: healthy,
                icon:
                    "health_and_safety",
                className: "healthy",
            },
            {
                id: 3,
                title:
                    "Sick / At Risk",
                value:
                    sickOrAtRisk,
                icon:
                    "medical_information",
                className: "risk",
            },
            {
                id: 4,
                title:
                    "Due for Vaccination",
                value:
                    vaccinationDue,
                icon: "vaccines",
                className:
                    "vaccination",
            },
            {
                id: 5,
                title:
                    "Total Births",
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

    const openEditLivestock = (
        animal
    ) => {
        setEditingAnimal(animal);

        setLivestockFormOpen(true);
    };

    const handleSaveLivestock = async (
        livestockData
    ) => {
        const normalizedRecord = {
            ...livestockData,

            age: calculateAge(
                livestockData.dateOfBirth
            ),

            isNewBirth:
                isRecentBirth(
                    livestockData.dateOfBirth
                ),
        };

        const animalBeingEdited =
            editingAnimal;

        if (livestockSaveInFlight.current) return;
        livestockSaveInFlight.current = true;
        setSavingLivestock(true);
        try {
            let savedAnimal;

            if (animalBeingEdited) {
                savedAnimal =
                    await livestockService.updateLivestock(
                        animalBeingEdited.id,
                        normalizedRecord
                    );
            } else {
                const idempotencyKey =
                    stableIdempotencyKey(
                        livestockCreateRequestRef,
                        normalizedRecord,
                        "livestock-create"
                    );

                savedAnimal =
                    await livestockService.createLivestock(
                        normalizedRecord,
                        { idempotencyKey }
                    );

                clearStableIdempotencyKey(
                    livestockCreateRequestRef
                );
            }

            const refreshedLivestock =
                await loadLivestock();

            const refreshedAnimal =
                refreshedLivestock.find(
                    (record) =>
                        record.id ===
                        savedAnimal.id
                );

            if (
                selectedAnimal?.id ===
                savedAnimal.id
            ) {
                setSelectedAnimal(
                    refreshedAnimal ||
                        decorateLivestockRecord(
                            savedAnimal
                        )
                );
            }

            if (animalBeingEdited) {
                notify(
                    "Livestock record updated successfully."
                );
            } else {
                notify(
                    "Livestock record added successfully."
                );
            }

            setLivestockFormOpen(false);
            setEditingAnimal(null);
        } catch (error) {
            console.error(
                "Failed to save livestock:",
                error
            );

            notifyError(
                error?.message ||
                    "Unable to save livestock record."
            );
        } finally {
            livestockSaveInFlight.current = false;
            setSavingLivestock(false);
        }
    };

    const replaceAnimalInState = (
        updatedAnimal
    ) => {
        const decoratedAnimal =
            decorateLivestockRecord(
                updatedAnimal
            );

        setLivestock(
            (currentLivestock) =>
                currentLivestock.map(
                    (animal) =>
                        animal.id ===
                        decoratedAnimal.id
                            ? decoratedAnimal
                            : animal
                )
        );

        setSelectedAnimal(
            (currentAnimal) =>
                currentAnimal?.id ===
                decoratedAnimal.id
                    ? decoratedAnimal
                    : currentAnimal
        );

        return decoratedAnimal;
    };

    const handleSaveVaccination = async (
        animalId,
        vaccinationRecord
    ) => {
        if (vaccinationInFlightRef.current) return false;
        vaccinationInFlightRef.current = true;
        setSavingVaccination(true);
        const { id: _localId, ...entry } = vaccinationRecord;
        const idempotencyKey = stableIdempotencyKey(vaccinationRequestRef, { animalId, ...entry }, "livestock-vaccination");
        const vaccinatedAnimal =
            livestock.find(
                (animal) =>
                    animal.id === animalId
            );

        try {
            await livestockService.addVaccinationRecord(
                animalId,
                vaccinationRecord,
                { idempotencyKey }
            );

            const updatedAnimal =
                await livestockService.getLivestockRecord(
                    animalId
                );

            replaceAnimalInState(
                updatedAnimal
            );
            clearStableIdempotencyKey(vaccinationRequestRef);

            if (vaccinatedAnimal) {
                logAudit({
                    action:
                        "Saved vaccination record",
                    module: "Livestock",
                    recordName:
                        vaccinatedAnimal.recordName,
                    entityId:
                        vaccinatedAnimal.animalId,
                    details:
                        vaccinationRecord.vaccine ||
                        vaccinationRecord.vaccineName ||
                        "Vaccination",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName:
                        vaccinatedAnimal.recordName,
                    entityId:
                        vaccinatedAnimal.animalId,
                    title:
                        "Vaccination recorded",
                    details:
                        vaccinationRecord.vaccine ||
                        vaccinationRecord.vaccineName ||
                        "Vaccination record saved.",
                    icon: "vaccines",
                });
            }

            window.dispatchEvent(new CustomEvent("joross:inventory-updated"));
            window.dispatchEvent(new CustomEvent("joross:alerts-updated"));
            notify(
                "Vaccination record saved successfully. Inventory was updated."
            );
        } catch (error) {
            console.error(
                "Failed to save vaccination:",
                error
            );

            notify(
                error?.message ||
                    "Unable to save vaccination record."
            );
            return false;
        } finally {
            vaccinationInFlightRef.current = false;
            setSavingVaccination(false);
        }
    };

    const handleSaveGrowth = async (
        animalId,
        growthRecord
    ) => {
        const growthAnimal =
            livestock.find(
                (animal) =>
                    animal.id === animalId
            );

        try {
            const savedRecord =
                await livestockService.addGrowthRecord(
                    animalId,
                    growthRecord
                );

            const updatedAnimal =
                await livestockService.getLivestockRecord(
                    animalId
                );

            replaceAnimalInState(updatedAnimal);

            if (growthAnimal) {
                logAudit({
                    action: "Recorded livestock weight measurement",
                    module: "Livestock",
                    recordName: growthAnimal.recordName,
                    entityId: growthAnimal.animalId,
                    details: `${Number(savedRecord.weightKg).toFixed(2)} kg on ${savedRecord.measurementDate}`,
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName: growthAnimal.recordName,
                    entityId: growthAnimal.animalId,
                    title: "Growth measurement recorded",
                    details: `${Number(savedRecord.weightKg).toFixed(2)} kg`,
                    icon: "monitor_weight",
                });
            }

            notify("Growth measurement saved successfully.");
            return savedRecord;
        } catch (error) {
            console.error("Failed to save growth measurement:", error);
            notify(
                error?.message ||
                    "Unable to save growth measurement."
            );
            return false;
        }
    };

    const handleSaveFeeding = async (
        animalId,
        feedingSchedule
    ) => {
        const fedAnimal =
            livestock.find(
                (animal) =>
                    animal.id === animalId
            );

        try {
            await livestockService.updateLivestock(
                animalId,
                {
                    feedInventoryItemId: feedingSchedule.inventoryItemId || null,
                    feedingSchedule,
                }
            );

            const updatedAnimal =
                await livestockService.getLivestockRecord(
                    animalId
                );

            replaceAnimalInState(
                updatedAnimal
            );

            if (fedAnimal) {
                logAudit({
                    action:
                        "Updated feeding schedule",
                    module: "Livestock",
                    recordName:
                        fedAnimal.recordName,
                    entityId:
                        fedAnimal.animalId,
                    details:
                        feedingSchedule.feedType ||
                        "Feeding schedule",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName:
                        fedAnimal.recordName,
                    entityId:
                        fedAnimal.animalId,
                    title:
                        "Feeding schedule updated",
                    details:
                        feedingSchedule.feedType ||
                        "Feeding schedule updated.",
                    icon: "restaurant",
                });
            }

            notify(
                "Feeding schedule updated successfully."
            );
        } catch (error) {
            console.error(
                "Failed to update feeding schedule:",
                error
            );

            notify(
                error?.message ||
                    "Unable to update feeding schedule."
            );
        }
    };

    const handleSaveHealth = async (
        animalId,
        healthRecord
    ) => {
        const healthAnimal =
            livestock.find(
                (animal) =>
                    animal.id === animalId
            );

        try {
            await livestockService.updateLivestock(
                animalId,
                healthRecord
            );

            const updatedAnimal =
                await livestockService.getLivestockRecord(
                    animalId
                );

            replaceAnimalInState(
                updatedAnimal
            );

            if (healthAnimal) {
                logAudit({
                    action:
                        "Updated livestock health record",
                    module: "Livestock",
                    recordName:
                        healthAnimal.recordName,
                    entityId:
                        healthAnimal.animalId,
                    details:
                        healthRecord.healthStatus ||
                        healthRecord.healthNotes ||
                        "Health record updated",
                });

                addTimelineEntry({
                    module: "Livestock",
                    recordName:
                        healthAnimal.recordName,
                    entityId:
                        healthAnimal.animalId,
                    title:
                        "Health record updated",
                    details:
                        healthRecord.healthStatus ||
                        healthRecord.healthNotes ||
                        "Livestock health record updated.",
                    icon:
                        "health_and_safety",
                });
            }

            notify(
                "Health record updated successfully."
            );
        } catch (error) {
            console.error(
                "Failed to update health record:",
                error
            );

            notify(
                error?.message ||
                    "Unable to update health record."
            );
        }
    };

    const archiveLivestock = async (
        animalId
    ) => {
        const animal =
            livestock.find(
                (record) =>
                    record.id === animalId
            );

        if (!animal) {
            return;
        }

        const confirmed = await requestArchive("Livestock", animalId, animal.recordName);

        if (!confirmed) {
            return;
        }

        try {

            await loadLivestock();

            if (
                selectedAnimal?.id ===
                animalId
            ) {
                setSelectedAnimal(null);
            }

            if (
                editingAnimal?.id ===
                animalId
            ) {
                setEditingAnimal(null);
                setLivestockFormOpen(false);
            }

            logAudit({
                action:
                    "Archived livestock record",
                module: "Livestock",
                recordName:
                    animal.recordName,
                entityId:
                    animal.animalId,
                details:
                    animal.penLocation,
            });

            addTimelineEntry({
                module: "Livestock",
                recordName:
                    animal.recordName,
                entityId:
                    animal.animalId,
                title:
                    "Livestock archived",
                details:
                    `${animal.type} record archived.`,
                icon: "archive",
            });

            notify(
                `${animal.recordName} was archived successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to archive livestock:",
                error
            );

            notify(
                error?.message ||
                    "Unable to archive livestock record."
            );
        }
    };


    useFarmModuleUpdates(["livestock", "archives"], loadLivestock, { editing: livestockFormOpen || Boolean(selectedAnimal) });

    return (
        <div className="livestock-layout">
            <Sidebar />

            <main className="livestock-page">
                <header className="livestock-header">
                    <div className="livestock-heading">
                        <h1>
                            Livestock Management
                        </h1>

                        <p>
                            Monitor livestock health,
                            productivity, feeding,
                            vaccination, and overall
                            farm performance.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <section className="livestock-summary-grid">
                    {statistics.map(
                        (card) => (
                            <article
                                className={`livestock-summary-card ${card.className}`}
                                key={card.id}
                            >
                                <div className="livestock-summary-icon">
                                    <span className="material-symbols-outlined">
                                        {card.icon}
                                    </span>
                                </div>

                                <div>
                                    <p>
                                        {card.title}
                                    </p>

                                    <h2>
                                        {card.value}
                                    </h2>
                                </div>
                            </article>
                        )
                    )}
                </section>

                <ArchiveWorkspace module="Livestock" before={<>
                <RecordFilters className="livestock-toolbar" label="Livestock filters">
                    <RecordSearch className="livestock-search-box" label="Search livestock" placeholder="Search livestock, ID, breed, or pen..." value={searchText} onChange={(event) => setSearchText(event.target.value)}/>

                    <select aria-label="Livestock type"
                        value={typeFilter}
                        onChange={(event) =>
                            setTypeFilter(
                                event.target.value
                            )
                        }
                    >
                        <option value="All">
                            All Types
                        </option>

                        {livestockTypes.map(
                            (type) => (
                                <option
                                    key={type}
                                    value={type}
                                >
                                    {type}
                                </option>
                            )
                        )}
                    </select>

                    <select aria-label="Health status"
                        value={statusFilter}
                        onChange={(event) =>
                            setStatusFilter(
                                event.target.value
                            )
                        }
                    >
                        <option value="All">
                            All Health Status
                        </option>

                        {healthStatuses.map(
                            (status) => (
                                <option
                                    key={status}
                                    value={status}
                                >
                                    {status}
                                </option>
                            )
                        )}
                    </select>

                    <select aria-label="Livestock pen"
                        value={penFilter}
                        onChange={(event) =>
                            setPenFilter(
                                event.target.value
                            )
                        }
                    >
                        <option value="All">
                            All Pens
                        </option>

                        {penLocations.map(
                            (pen) => (
                                <option
                                    key={pen}
                                    value={pen}
                                >
                                    {pen}
                                </option>
                            )
                        )}
                    </select>

                    <button
                        type="button"
                        className="livestock-clear-button"
                        onClick={clearFilters}
                    >
                        Clear
                    </button>
                </RecordFilters>

                </>}>
                {(navigation) => <>
                <RecordHeader className="livestock-action-row" title="Livestock Records" navigation={navigation}
                    summary={`${filteredLivestock.length} livestock records found`} actions={<><button
                            type="button"
                            className="livestock-manage-pens-button"
                            onClick={() => setPenManagementOpen(true)}
                        >
                            <span className="material-symbols-outlined">fence</span>
                            Manage Pens
                        </button>
                        <button
                            type="button"
                            className="livestock-add-button"
                            onClick={
                                openAddLivestock
                            }
                        >
                            <span className="material-symbols-outlined">
                                add
                            </span>

                            Add Livestock
                        </button></>}/>


                <RecordTableSurface className="livestock-table-card" scrollClassName="livestock-table-wrapper" busy={livestockLoading} footer={<div className="livestock-table-footer records-footer">
                        <span>
                            Showing{" "}
                            {
                                filteredLivestock.length
                            }{" "}
                            of{" "}
                            {livestock.length}{" "}
                            livestock records
                        </span>
                    </div>}>
                        <table className="livestock-table">
                            <colgroup>
                                <col className="livestock-col-id" />
                                <col className="livestock-col-record" />
                                <col className="livestock-col-type" />
                                <col className="livestock-col-count" />
                                <col className="livestock-col-health" />
                                <col className="livestock-col-growth" />
                                <col className="livestock-col-age" />
                                <col className="livestock-col-location" />
                                <col className="livestock-col-actions" />
                            </colgroup>

                            <thead>
                                <tr>
                                    <th>
                                        Animal ID
                                    </th>

                                    <th>
                                        Record
                                    </th>

                                    <th>
                                        Type / Breed
                                    </th>

                                    <th>
                                        Count / Weight
                                    </th>

                                    <th>
                                        Health
                                    </th>

                                    <th>
                                        Growth Stage
                                    </th>

                                    <th>
                                        Age / Birth Date
                                    </th>

                                    <th>
                                        Pen / Checkup
                                    </th>

                                    <th>
                                        Actions
                                    </th>
                                </tr>
                            </thead>

                            <tbody>
                                {filteredLivestock.length >
                                0 ? (
                                    filteredLivestock.map(
                                        (animal) => (
                                            <tr
                                                key={
                                                    animal.id
                                                }
                                            >
                                                <td>
                                                    <strong className="animal-id">
                                                        {
                                                            animal.animalId
                                                        }
                                                    </strong>
                                                </td>

                                                <td>
                                                    <div className="animal-name-cell">
                                                        <span
                                                            className={`animal-type-icon ${animal.type.toLowerCase()}`}
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                pets
                                                            </span>
                                                        </span>

                                                        <div>
                                                            <strong>
                                                                {
                                                                    animal.recordName
                                                                }
                                                            </strong>

                                                        </div>
                                                    </div>
                                                </td>

                                                <td>
                                                    <strong>
                                                        {
                                                            animal.type
                                                        }
                                                    </strong>

                                                    <small className="table-subtext">
                                                        {
                                                            animal.breed
                                                        }
                                                    </small>
                                                </td>

                                                <td>
                                                    <div className="livestock-stacked-cell">
                                                        <strong>
                                                            {
                                                                animal.quantity
                                                            }{" "}
                                                            head
                                                        </strong>

                                                        <small>
                                                            {
                                                                animal.weight
                                                            }{" "}
                                                            kg average
                                                        </small>
                                                        <small>Min / max: {animal.minWeight ?? "—"} / {animal.maxWeight ?? "—"} kg</small>
                                                    </div>
                                                </td>

                                                <td>
                                                    <div className="livestock-health-breakdown">
                                                        <span className={`livestock-health-status ${getClassName(animal.healthStatus)}`}>
                                                            {animal.healthStatus}
                                                        </span>
                                                        {animal.recordType === "Batch" && (
                                                            <small>
                                                                {Number(animal.healthyQuantity || 0)} Healthy
                                                                {Number(animal.sickQuantity || 0) > 0 ? ` · ${animal.sickQuantity} Sick` : ""}
                                                                {Number(animal.atRiskQuantity || 0) > 0 ? ` · ${animal.atRiskQuantity} At Risk` : ""}
                                                                {Number(animal.underTreatmentQuantity || 0) > 0 ? ` · ${animal.underTreatmentQuantity} Treatment` : ""}
                                                            </small>
                                                        )}
                                                    </div>
                                                </td>

                                                <td>
                                                    <strong className="livestock-growth-stage">
                                                        {animal.growthStatus || "Not set"}
                                                    </strong>
                                                    <MonitoringStatus summary={animal.monitoringSummary} />
                                                </td>

                                                <td>
                                                    <div className="livestock-stacked-cell">
                                                        <strong>
                                                            {
                                                                animal.age
                                                            }
                                                        </strong>

                                                        <small>
                                                            {formatDate(
                                                                animal.dateOfBirth
                                                            )}
                                                        </small>
                                                    </div>
                                                </td>

                                                <td>
                                                    <div className="livestock-stacked-cell">
                                                        <strong>
                                                            {
                                                                animal.penLocation
                                                            }
                                                        </strong>

                                                        <small>
                                                            Last:{" "}
                                                            {formatDate(
                                                                animal.lastCheckup
                                                            )}
                                                        </small>
                                                    </div>
                                                </td>

                                                <td>
                                                    <div className="livestock-row-actions records-row-actions">
                                                        <button
                                                            type="button"
                                                            title="View livestock details"
                                                            onClick={() =>
                                                                openDetailedAnimal(animal, setSelectedAnimal)
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                visibility
                                                            </span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            className="feeding-history-action"
                                                            title="View feeding history"
                                                            onClick={() => setSelectedFeedingHistoryAnimal(animal)}
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                history
                                                            </span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            className="movement"
                                                            title="Transfer or split batch"
                                                            onClick={() => setMovementAnimal(animal)}
                                                        >
                                                            <span className="material-symbols-outlined">move_item</span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            title="Edit livestock"
                                                            onClick={() =>
                                                                openEditLivestock(
                                                                    animal
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                edit
                                                            </span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            className="archive"
                                                            title="Archive livestock"
                                                            onClick={() =>
                                                                archiveLivestock(
                                                                    animal.id
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                archive
                                                            </span>
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    )
                                ) : (
                                    <tr>
                                        <td
                                            colSpan="9"
                                            className="livestock-empty-table"
                                        >
                                            <span className="material-symbols-outlined">
                                                search_off
                                            </span>

                                            <p>
                                                No livestock
                                                records match
                                                the selected
                                                filters.
                                            </p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>


                </RecordTableSurface>

                <LivestockAnalytics
                    livestock={livestock}
                />
                </>}
                </ArchiveWorkspace>
            </main>

            <LivestockFormModal
                saving={savingLivestock}
                open={
                    livestockFormOpen
                }
                animal={
                    editingAnimal
                }
                onClose={() => {
                    if (livestockSaveInFlight.current) return;
                    setLivestockFormOpen(
                        false
                    );

                    setEditingAnimal(null);
                }}
                onSave={
                    handleSaveLivestock
                }
            />

            <LivestockDetailsModal
                animal={
                    selectedAnimal
                }
                onStageOverrideSaved={(animalId, stage) => {
                    setLivestock((records) => records.map((record) =>
                        record.id === animalId ? { ...record, growthStatus: stage } : record
                    ));
                    setSelectedAnimal((record) => record?.id === animalId
                        ? { ...record, growthStatus: stage }
                        : record
                    );
                }}
                onClose={() =>
                    setSelectedAnimal(null)
                }
                onSaveVaccination={
                    handleSaveVaccination
                }
                savingVaccination={savingVaccination}
                onSaveFeeding={
                    handleSaveFeeding
                }
                onSaveGrowth={
                    handleSaveGrowth
                }
                onSaveHealth={
                    handleSaveHealth
                }
            />

            {selectedFeedingHistoryAnimal && (
                <FeedingHistoryModal
                    animal={selectedFeedingHistoryAnimal}
                    onClose={() => setSelectedFeedingHistoryAnimal(null)}
                />
            )}

            <PenManagementModal
                open={penManagementOpen}
                onClose={() => setPenManagementOpen(false)}
                onChanged={async () => {
                    await loadLivestock();
                }}
            />

            {movementAnimal && (
                <LivestockMovementModal
                    animal={movementAnimal}
                    onClose={() => setMovementAnimal(null)}
                    onTransfer={async (data) => {
                        try {
                            await livestockService.transferPen(movementAnimal.id, data);
                            await loadLivestock();
                            setMovementAnimal(null);
                            notify("Livestock transferred successfully.");
                        } catch (error) {
                            notify(error?.message || "Unable to transfer livestock.");
                        }
                    }}
                    onSplit={async (data) => {
                        try {
                            await livestockService.splitBatch(movementAnimal.id, data);
                            await loadLivestock();
                            setMovementAnimal(null);
                            notify("Batch split saved successfully.");
                        } catch (error) {
                            notify(error?.message || "Unable to split livestock batch.");
                        }
                    }}
                />
            )}
        </div>
    );
}

export default Livestock;
