"use client";

import { useVoidAuthorization } from "../../context/VoidAuthorizationContext.jsx";

import { confirmAction, notify, promptAction } from "../../context/NotificationContext.jsx";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { inventoryService } from "../../services/inventoryService.js";
import { resourceUsageService } from "../../services/resourceUsageService.js";
import { workforceService } from "../../services/workforceService.js";

import { stableIdempotencyKey, clearStableIdempotencyKey } from "../../services/idempotencyKey.js";
import "./ResourceUsagePanel.css";

const USAGE_TYPES = {
    Crop: ["Fertilizer", "Pesticide", "Herbicide", "Other"],
    Livestock: ["Medicine", "Vitamin / Supplement", "Disinfectant", "Treatment Supply", "Sanitation Supply", "Other"],
};

const CATEGORY_ALIASES = {
    Fertilizer: ["fertilizer", "fertilizers"],
    Pesticide: ["pesticide", "pesticides"],
    Herbicide: ["herbicide", "herbicides"],
    Medicine: ["medicine", "medicines", "animal medicine", "livestock medicine"],
    "Vitamin / Supplement": ["vitamin", "vitamins", "supplement", "supplements", "vitamin supplement", "vitamin supplements"],
    Disinfectant: ["disinfectant", "disinfectants"],
    "Treatment Supply": ["treatment supply", "treatment supplies", "medical supply", "medical supplies"],
    "Sanitation Supply": ["sanitation supply", "sanitation supplies", "sanitation", "cleaning supply", "cleaning supplies"],
};

function todayKey() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(
        now.getDate()
    ).padStart(2, "0")}`;
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

function normalizeCategory(value) {
    return String(value || "")
        .trim()
        .toLowerCase()
        .replaceAll("-", " ")
        .replace(/\s+/g, " ");
}

function categoryMatches(item, usageType, module) {
    const category = normalizeCategory(item.category);
    const cropSeedTerms = ["seed", "seeds", "seedling", "seedlings", "planting material", "planting materials"];
    const cropMapped = new Set([
        "fertilizer", "fertilizers", "pesticide", "pesticides",
        "herbicide", "herbicides", "fungicide", "fungicides",
    ]);
    const livestockMapped = new Set([
        "livestock feed", "animal feed", "feed", "feeds",
        "medicine", "medicines", "animal medicine", "livestock medicine",
        "vaccine", "vaccines", "vitamin", "vitamins", "supplement", "supplements",
        "disinfectant", "disinfectants", "treatment supply", "treatment supplies",
        "medical supply", "medical supplies", "sanitation supply", "sanitation supplies",
        "cleaning supply", "cleaning supplies",
    ]);

    if (module === "Crop") {
        if (cropSeedTerms.some((term) => category === term || category.includes(term))) return false;
        if (livestockMapped.has(category)) return false;
        if (usageType === "Other") return !cropMapped.has(category);
    }

    if (module === "Livestock") {
        if (cropSeedTerms.some((term) => category === term || category.includes(term))) return false;
        if (cropMapped.has(category)) return false;
        // Feed and vaccines intentionally stay in their dedicated Feeding and
        // Vaccination workflows, even when the user chooses "Other".
        if (usageType === "Other") return !livestockMapped.has(category);
    }

    const aliases = CATEGORY_ALIASES[usageType] || [];
    return aliases.includes(category);
}

function isExpired(item, usageDate) {
    return Boolean(
        item.expirationDate && usageDate && String(usageDate) > String(item.expirationDate)
    );
}

function emptyForm(module) {
    return {
        usageType: USAGE_TYPES[module]?.[0] || "Other",
        inventoryItemId: "",
        quantity: "",
        usageDate: todayKey(),
        notes: "",
    };
}

function emptyScheduleForm(module) {
    return {
        usageType: USAGE_TYPES[module]?.[0] || "Other",
        inventoryItemId: "",
        quantity: "",
        activityDate: todayKey(),
        startTime: "08:00",
        priority: "Medium",
        instructions: "",
        requiresEvidence: false,
    };
}

export default function ResourceUsagePanel({ module, target, canEdit = true, onChanged }) {
    const requestVoid = useVoidAuthorization();
    const [inventory, setInventory] = useState([]);
    const [usages, setUsages] = useState([]);
    const [scheduledTasks, setScheduledTasks] = useState([]);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const usageRequestRef = useRef(null);
    const usageInFlightRef = useRef(false);
    const [scheduling, setScheduling] = useState(false);
    const [error, setError] = useState("");
    const [showForm, setShowForm] = useState(false);
    const [showScheduleForm, setShowScheduleForm] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [form, setForm] = useState(() => emptyForm(module));
    const [scheduleForm, setScheduleForm] = useState(() => emptyScheduleForm(module));

    const targetId = target?.id;
    const usageTypes = USAGE_TYPES[module] || ["Other"];

    const loadData = useCallback(async () => {
        if (!targetId) return;
        setLoading(true);
        setError("");
        try {
            const [inventoryRows, usageRows] = await Promise.all([
                inventoryService.getInventory(false),
                resourceUsageService.getUsages({ module, targetId }),
            ]);
            let taskRows = [];
            try {
                taskRows = await workforceService.getTasks({
                    source_module: module,
                    source_record_id: targetId,
                });
            } catch (taskLoadError) {
                // Resource history should still load for users who can view the
                // farm record but do not have workforce/task permissions.
                console.debug("Scheduled task list unavailable:", taskLoadError);
            }
            setInventory(inventoryRows);
            setUsages(usageRows);
            setScheduledTasks((taskRows || []).filter((task) =>
                !["Completed", "Cancelled", "Resolved", "Voided"].includes(task.status) &&
                Boolean(task.resource_required || task.planned_inventory_item_id)
            ));
        } catch (loadError) {
            console.error("Failed to load resource usage:", loadError);
            setError(loadError?.message || "Unable to load resource usage records.");
        } finally {
            setLoading(false);
        }
    }, [module, targetId]);

    useEffect(() => {
        loadData();
    }, [loadData]);

    useEffect(() => {
        setForm(emptyForm(module));
        setScheduleForm(emptyScheduleForm(module));
        setEditingId(null);
        setShowForm(false);
        setShowScheduleForm(false);
    }, [module, targetId]);

    useEffect(() => {
        const refresh = () => loadData();
        window.addEventListener("joross:resource-usage-updated", refresh);
        window.addEventListener("joross:farm-data-updated", refresh);
        return () => {
            window.removeEventListener("joross:resource-usage-updated", refresh);
            window.removeEventListener("joross:farm-data-updated", refresh);
        };
    }, [loadData]);

    const eligibleItems = useMemo(() => {
        return inventory.filter((item) => {
            if (!categoryMatches(item, form.usageType, module)) return false;
            if (item.isArchived) return false;
            if (isExpired(item, form.usageDate)) return false;
            if (editingId && Number(item.id) === Number(form.inventoryItemId)) return true;
            return Number(item.quantity || 0) > 0;
        });
    }, [inventory, form.usageType, form.usageDate, form.inventoryItemId, editingId, module]);

    const selectedItem = useMemo(
        () => inventory.find((item) => Number(item.id) === Number(form.inventoryItemId)) || null,
        [inventory, form.inventoryItemId]
    );

    const scheduleEligibleItems = useMemo(() => {
        return inventory.filter((item) => {
            if (!categoryMatches(item, scheduleForm.usageType, module)) return false;
            if (item.isArchived) return false;
            if (isExpired(item, scheduleForm.activityDate)) return false;
            return Number(item.quantity || 0) > 0;
        });
    }, [inventory, scheduleForm.usageType, scheduleForm.activityDate, module]);

    const selectedScheduleItem = useMemo(
        () => inventory.find((item) => Number(item.id) === Number(scheduleForm.inventoryItemId)) || null,
        [inventory, scheduleForm.inventoryItemId]
    );

    const currentEdit = useMemo(
        () => usages.find((usage) => usage.id === editingId) || null,
        [usages, editingId]
    );

    const effectiveAvailable = selectedItem
        ? Number(selectedItem.quantity || 0) +
          (currentEdit && Number(currentEdit.inventoryItemId) === Number(selectedItem.id)
              ? Number(currentEdit.quantity || 0)
              : 0)
        : 0;

    const previewEfficiency = useMemo(() => {
        const quantity = Number(form.quantity || 0);
        if (!quantity || !selectedItem) return null;
        if (module === "Crop") {
            const area = Number(target?.area ?? target?.areaHectares ?? 0);
            if (area > 0) {
                return `${(quantity / area).toFixed(2)} ${selectedItem.unit}/ha`;
            }
        }
        if (module === "Livestock") {
            const head = Number(target?.quantity || 0);
            if (head > 0) {
                return `${(quantity / head).toFixed(2)} ${selectedItem.unit}/animal`;
            }
        }
        return null;
    }, [form.quantity, module, selectedItem, target]);

    const openNewForm = () => {
        setShowScheduleForm(false);
        setEditingId(null);
        setForm(emptyForm(module));
        setShowForm(true);
    };

    const openScheduleForm = () => {
        setShowForm(false);
        setEditingId(null);
        setScheduleForm(emptyScheduleForm(module));
        setShowScheduleForm(true);
    };

    const closeScheduleForm = () => {
        setShowScheduleForm(false);
        setScheduleForm(emptyScheduleForm(module));
    };

    const handleScheduleChange = (event) => {
        const { name, value, type, checked } = event.target;
        setScheduleForm((current) => {
            const next = { ...current, [name]: type === "checkbox" ? checked : value };
            if (name === "usageType") {
                next.inventoryItemId = "";
                next.quantity = "";
            }
            return next;
        });
    };

    const handleScheduleSubmit = async (event) => {
        event.preventDefault();
        if (!target?.assignedEmployeeId) {
            notify(`Assign an active employee to this ${module.toLowerCase()} record before scheduling work.`);
            return;
        }
        if (!scheduleForm.inventoryItemId || Number(scheduleForm.quantity) <= 0) {
            notify("Select an inventory item and enter a planned quantity greater than zero.");
            return;
        }
        if (!selectedScheduleItem) {
            notify("Select a valid inventory item.");
            return;
        }
        if (scheduleForm.activityDate < todayKey()) {
            notify("Scheduled work cannot be created in the past.");
            return;
        }
        if (isExpired(selectedScheduleItem, scheduleForm.activityDate)) {
            notify(`This item expires on ${selectedScheduleItem.expirationDate} and cannot be scheduled after that date.`);
            return;
        }
        if (Number(scheduleForm.quantity) > Number(selectedScheduleItem.quantity || 0)) {
            notify(`Insufficient stock. Only ${selectedScheduleItem.quantity} ${selectedScheduleItem.unit} is available.`);
            return;
        }

        setScheduling(true);
        try {
            await workforceService.scheduleResourceWork({
                module,
                target_id: Number(targetId),
                inventory_item_id: Number(scheduleForm.inventoryItemId),
                usage_type: scheduleForm.usageType,
                planned_quantity: Number(scheduleForm.quantity),
                activity_date: scheduleForm.activityDate,
                start_time: scheduleForm.startTime || "08:00",
                priority: scheduleForm.priority,
                instructions: scheduleForm.instructions || null,
                requires_evidence: Boolean(scheduleForm.requiresEvidence),
            });
            closeScheduleForm();
            await loadData();
            notify("Work scheduled successfully. It will appear in the assigned employee's My Tasks when due.");
            window.dispatchEvent(new CustomEvent("joross:activities-updated"));
            onChanged?.();
        } catch (scheduleError) {
            notify(scheduleError?.message || "Unable to schedule this resource work.");
        } finally {
            setScheduling(false);
        }
    };

    const openEditForm = (usage) => {
        if (module === "Livestock" && !usageTypes.includes(usage.usageType)) {
            notify(`${usage.usageType} is a historical Resource Usage record. New feed usage is handled by Feeding and vaccine usage by Vaccination, so this old record is view-only here.`);
            return;
        }
        setEditingId(usage.id);
        setForm({
            usageType: usage.usageType,
            inventoryItemId: String(usage.inventoryItemId),
            quantity: String(usage.quantity),
            usageDate: usage.usageDate,
            notes: usage.notes || "",
        });
        setShowForm(true);
    };

    const closeForm = () => {
        setShowForm(false);
        setEditingId(null);
        setForm(emptyForm(module));
    };

    const handleChange = (event) => {
        const { name, value } = event.target;
        setForm((current) => {
            const next = { ...current, [name]: value };
            if (name === "usageType") {
                next.inventoryItemId = "";
                next.quantity = "";
            }
            return next;
        });
    };

    const handleSubmit = async (event) => {
        event.preventDefault();
        if (usageInFlightRef.current) return;
        if (!form.inventoryItemId || !form.usageDate || Number(form.quantity) <= 0) {
            notify("Select an inventory item, date, and a quantity greater than zero.");
            return;
        }
        if (!selectedItem) {
            notify("Select a valid inventory item.");
            return;
        }
        if (module === "Crop" && target?.plantingDate && form.usageDate < target.plantingDate) {
            notify("Crop resource usage date cannot be earlier than the planting date.");
            return;
        }
        if (isExpired(selectedItem, form.usageDate)) {
            notify(`This item expired on ${selectedItem.expirationDate} and cannot be used.`);
            return;
        }
        if (Number(form.quantity) > effectiveAvailable) {
            notify(
                `Insufficient stock. Only ${effectiveAvailable} ${selectedItem.unit} is available.`
            );
            return;
        }

        usageInFlightRef.current = true;
        setSaving(true);
        try {
            const payload = {
                module, targetId, inventoryItemId: form.inventoryItemId,
                usageType: form.usageType, quantity: form.quantity,
                usageDate: form.usageDate, notes: form.notes,
            };
            if (editingId) {
                await resourceUsageService.updateUsage(editingId, payload);
            } else {
                const idempotencyKey = stableIdempotencyKey(usageRequestRef, payload, "manual-resource-usage");
                await resourceUsageService.createUsage(payload, { idempotencyKey });
                clearStableIdempotencyKey(usageRequestRef);
            }
            closeForm();
            await loadData();
            window.dispatchEvent(new CustomEvent("joross:resource-usage-updated"));
            onChanged?.();
        } catch (saveError) {
            console.error("Failed to save resource usage:", saveError);
            notify(saveError?.message || "Unable to save the resource usage record.");
        } finally {
            usageInFlightRef.current = false;
            setSaving(false);
        }
    };

    const handleDelete = async (usage) => {
        if (await requestVoid({ action: "resource_usage", recordId: usage.id, onStale: loadData })) {
            await loadData();
            window.dispatchEvent(new CustomEvent("joross:resource-usage-updated"));
            onChanged?.();
        }
    };

    const usageTotals = useMemo(() => {
        const grouped = new Map();
        usages.forEach((usage) => {
            const key = `${usage.usageType}|${usage.unit}`;
            grouped.set(key, (grouped.get(key) || 0) + Number(usage.quantity || 0));
        });
        return [...grouped.entries()].map(([key, quantity]) => {
            const [usageType, unit] = key.split("|");
            return { usageType, unit, quantity: Math.round(quantity * 100) / 100 };
        });
    }, [usages]);

    return (
        <section className="resource-usage-panel">
            <div className="resource-usage-heading">
                <div>
                    <h3>Inventory Resource Usage</h3>
                    <p>
                        {module === "Crop"
                            ? "Schedule fertilizer/pesticide/herbicide work for the crop employee, or record usage only when the work already happened. Seeds and planting materials stay in Crops Management."
                            : "Schedule medicine, supplement, treatment, or sanitation work for the livestock employee, or record usage only when it already happened. Feeding and vaccination keep their dedicated workflows."}
                    </p>
                </div>
                {canEdit && (
                    <div className="resource-usage-heading-actions">
                        <button type="button" className="secondary" onClick={openScheduleForm}>
                            <span className="material-symbols-outlined">event_upcoming</span>
                            Schedule Work
                        </button>
                        <button type="button" onClick={openNewForm}>
                            <span className="material-symbols-outlined">add</span>
                            Record Usage
                        </button>
                    </div>
                )}
            </div>

            <div className="resource-usage-workflow-note">
                <span className="material-symbols-outlined">info</span>
                <div>
                    <strong>Schedule Work</strong> creates an employee task and does not deduct stock yet.
                    <strong> Record Usage</strong> is for work that already happened and deducts Inventory immediately.
                </div>
            </div>

            {scheduledTasks.length > 0 && (
                <div className="resource-scheduled-work">
                    <div className="resource-scheduled-work-title">
                        <span className="material-symbols-outlined">event_note</span>
                        <div><strong>Scheduled Resource Work</strong><small>These tasks are linked to this record and assigned through Task Management.</small></div>
                    </div>
                    <div className="resource-scheduled-work-list">
                        {scheduledTasks.slice(0, 6).map((task) => (
                            <div className="resource-scheduled-work-row" key={task.id}>
                                <div>
                                    <strong>{task.name}</strong>
                                    <small>{formatDate(task.activity_date)} · {task.employee_name || "Unassigned"}</small>
                                </div>
                                <div className="resource-scheduled-work-meta">
                                    {task.planned_quantity != null && <span>{task.planned_quantity} {task.planned_inventory_unit || task.planned_unit || ""}</span>}
                                    <span className={`resource-task-status ${String(task.status || "").toLowerCase().replaceAll(" ", "-")}`}>{task.status}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                    {scheduledTasks.length > 6 && <small className="resource-scheduled-more">+{scheduledTasks.length - 6} more scheduled task(s) in Task Management.</small>}
                </div>
            )}

            {usageTotals.length > 0 && (
                <div className="resource-usage-totals">
                    {usageTotals.map((total) => (
                        <div key={`${total.usageType}-${total.unit}`}>
                            <small>{total.usageType}</small>
                            <strong>
                                {total.quantity} {total.unit}
                            </strong>
                        </div>
                    ))}
                </div>
            )}

            {error && <div className="resource-usage-error">{error}</div>}

            {showScheduleForm && (
                <form className="resource-usage-form resource-schedule-form" onSubmit={handleScheduleSubmit}>
                    <div className="resource-schedule-title">
                        <span className="material-symbols-outlined">assignment_add</span>
                        <div><strong>Schedule Resource Work</strong><small>The employee assigned to this {module.toLowerCase()} record will receive the task.</small></div>
                    </div>
                    {!target?.assignedEmployeeId && <div className="resource-usage-error">Assign an active employee to this {module.toLowerCase()} record first.</div>}
                    <div className="resource-usage-form-grid">
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-schedule-type`}>Work / Usage Type</label>
                            <select id={`${module}-schedule-type`} name="usageType" value={scheduleForm.usageType} onChange={handleScheduleChange}>
                                {usageTypes.map((type) => <option value={type} key={type}>{type}</option>)}
                            </select>
                        </div>
                        <div className="resource-usage-field resource-usage-item-field">
                            <label htmlFor={`${module}-schedule-item`}>Inventory Resource</label>
                            <select id={`${module}-schedule-item`} name="inventoryItemId" value={scheduleForm.inventoryItemId} onChange={handleScheduleChange} required>
                                <option value="">Select inventory item</option>
                                {scheduleEligibleItems.map((item) => <option value={item.id} key={item.id}>{item.name} — {item.quantity} {item.unit} available</option>)}
                            </select>
                        </div>
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-schedule-quantity`}>Planned Quantity</label>
                            <div className="resource-usage-unit-input">
                                <input id={`${module}-schedule-quantity`} name="quantity" type="number" min="0.001" step="0.001" value={scheduleForm.quantity} onChange={handleScheduleChange} required/>
                                <span>{selectedScheduleItem?.unit || "unit"}</span>
                            </div>
                        </div>
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-schedule-date`}>Work Date</label>
                            <input id={`${module}-schedule-date`} name="activityDate" type="date" min={todayKey()} value={scheduleForm.activityDate} onChange={handleScheduleChange} required/>
                        </div>
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-schedule-time`}>Start Time</label>
                            <input id={`${module}-schedule-time`} name="startTime" type="time" value={scheduleForm.startTime} onChange={handleScheduleChange} required/>
                        </div>
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-schedule-priority`}>Priority</label>
                            <select id={`${module}-schedule-priority`} name="priority" value={scheduleForm.priority} onChange={handleScheduleChange}>
                                <option>Low</option><option>Medium</option><option>High</option><option>Critical</option>
                            </select>
                        </div>
                    </div>
                    {selectedScheduleItem && <div className={`resource-usage-stock-preview ${Number(scheduleForm.quantity || 0) > Number(selectedScheduleItem.quantity || 0) ? "insufficient" : ""}`}>
                        <span>Available: <strong>{selectedScheduleItem.quantity} {selectedScheduleItem.unit}</strong></span>
                        <span>Planned: <strong>{Number(scheduleForm.quantity || 0) || 0} {selectedScheduleItem.unit}</strong></span>
                        {Number(scheduleForm.quantity || 0) > Number(selectedScheduleItem.quantity || 0) && <span className="resource-stock-warning"><strong>Insufficient stock</strong></span>}
                    </div>}
                    <div className="resource-usage-field">
                        <label htmlFor={`${module}-schedule-instructions`}>Instructions</label>
                        <textarea id={`${module}-schedule-instructions`} name="instructions" rows="3" value={scheduleForm.instructions} onChange={handleScheduleChange} placeholder="What should the employee do?"/>
                    </div>
                    <label className="resource-schedule-checkbox">
                        <input type="checkbox" name="requiresEvidence" checked={scheduleForm.requiresEvidence} onChange={handleScheduleChange}/>
                        Require photo/evidence when the employee submits this work
                    </label>
                    <div className="resource-usage-form-actions">
                        <button type="button" className="secondary" onClick={closeScheduleForm} disabled={scheduling}>Cancel</button>
                        <button type="submit" disabled={scheduling || !target?.assignedEmployeeId || !selectedScheduleItem || Number(scheduleForm.quantity || 0) <= 0 || Number(scheduleForm.quantity || 0) > Number(selectedScheduleItem?.quantity || 0)}>
                            <span className="material-symbols-outlined">assignment_add</span>
                            {scheduling ? "Scheduling..." : "Schedule for Employee"}
                        </button>
                    </div>
                </form>
            )}

            {showForm && (
                <form className="resource-usage-form" onSubmit={handleSubmit}>
                    <div className="resource-usage-form-grid">
                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-resource-type`}>Usage Type</label>
                            <select
                                id={`${module}-resource-type`}
                                name="usageType"
                                value={form.usageType}
                                onChange={handleChange}
                            >
                                {usageTypes.map((type) => (
                                    <option value={type} key={type}>
                                        {type}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="resource-usage-field resource-usage-item-field">
                            <label htmlFor={`${module}-inventory-item`}>Inventory Item</label>
                            <select
                                id={`${module}-inventory-item`}
                                name="inventoryItemId"
                                value={form.inventoryItemId}
                                onChange={handleChange}
                                required
                            >
                                <option value="">Select inventory item</option>
                                {eligibleItems.map((item) => (
                                    <option value={item.id} key={item.id}>
                                        {item.name} — {item.quantity} {item.unit}
                                        {item.batchNumber ? ` — Batch ${item.batchNumber}` : ""}
                                    </option>
                                ))}
                            </select>
                        </div>

                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-usage-quantity`}>Quantity Used</label>
                            <div className="resource-usage-unit-input">
                                <input
                                    id={`${module}-usage-quantity`}
                                    name="quantity"
                                    type="number"
                                    min="0.01"
                                    step="0.01"
                                    value={form.quantity}
                                    onChange={handleChange}
                                    required
                                />
                                <span>{selectedItem?.unit || "unit"}</span>
                            </div>
                        </div>

                        <div className="resource-usage-field">
                            <label htmlFor={`${module}-usage-date`}>Date Used</label>
                            <input
                                id={`${module}-usage-date`}
                                name="usageDate"
                                type="date"
                                max={todayKey()}
                                value={form.usageDate}
                                onChange={handleChange}
                                required
                            />
                        </div>
                    </div>

                    {selectedItem && (
                        <div className="resource-usage-stock-preview">
                            <span>
                                Available: <strong>{effectiveAvailable} {selectedItem.unit}</strong>
                            </span>
                            {selectedItem.batchNumber && (
                                <span>Batch/Lot: <strong>{selectedItem.batchNumber}</strong></span>
                            )}
                            {selectedItem.expirationDate && (
                                <span>Expires: <strong>{formatDate(selectedItem.expirationDate)}</strong></span>
                            )}
                            {previewEfficiency && (
                                <span>Usage rate: <strong>{previewEfficiency}</strong></span>
                            )}
                        </div>
                    )}

                    <div className="resource-usage-field">
                        <label htmlFor={`${module}-usage-notes`}>Notes</label>
                        <textarea
                            id={`${module}-usage-notes`}
                            name="notes"
                            rows="3"
                            value={form.notes}
                            onChange={handleChange}
                            placeholder="Application, treatment, feeding, or usage notes..."
                        />
                    </div>

                    <div className="resource-usage-form-actions">
                        <button type="button" className="secondary" onClick={closeForm} disabled={saving}>
                            Cancel
                        </button>
                        <button type="submit" disabled={saving}>
                            <span className="material-symbols-outlined">save</span>
                            {saving ? "Saving..." : editingId ? "Save Correction" : "Save Usage"}
                        </button>
                    </div>
                </form>
            )}

            <div className="resource-usage-list">
                {loading ? (
                    <div className="resource-usage-empty">Loading resource usage...</div>
                ) : usages.length === 0 ? (
                    <div className="resource-usage-empty">
                        <span className="material-symbols-outlined">inventory_2</span>
                        <p>No inventory-linked usage has been recorded yet.</p>
                    </div>
                ) : (
                    usages.map((usage) => (
                        <article className="resource-usage-row" key={usage.id}>
                            <span className="resource-usage-row-icon material-symbols-outlined">
                                {usage.usageType === "Feed"
                                    ? "nutrition"
                                    : usage.usageType === "Vaccine"
                                      ? "vaccines"
                                      : usage.usageType === "Fertilizer"
                                        ? "compost"
                                        : "inventory_2"}
                            </span>
                            <div className="resource-usage-row-main">
                                <div className="resource-usage-row-title">
                                    <strong>{usage.inventoryItemName}</strong>
                                    <span>{usage.usageType}</span>
                                </div>
                                <small>
                                    {formatDate(usage.usageDate)}
                                    {usage.batchNumber ? ` • Batch ${usage.batchNumber}` : ""}
                                    {usage.efficiencyValue !== null && usage.efficiencyValue !== undefined
                                        ? ` • ${usage.efficiencyValue} ${usage.efficiencyLabel}`
                                        : ""}
                                </small>
                                {usage.notes && <p>{usage.notes}</p>}
                            </div>
                            <div className="resource-usage-row-quantity">
                                <strong>{usage.quantity} {usage.unit}</strong>
                                <small>{usage.inventoryItemCode}</small>
                            </div>
                            {canEdit && (
                                <div className="resource-usage-row-actions">
                                    <button type="button" title="Correct usage" onClick={() => openEditForm(usage)}>
                                        <span className="material-symbols-outlined">edit</span>
                                    </button>
                                    <button type="button" className="delete" title="Request authorized void and restore stock" onClick={() => handleDelete(usage)}>
                                        <span className="material-symbols-outlined">delete</span>
                                    </button>
                                </div>
                            )}
                        </article>
                    ))
                )}
            </div>
        </section>
    );
}
