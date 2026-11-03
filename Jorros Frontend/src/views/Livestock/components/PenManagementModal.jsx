"use client";

import { confirmAction, notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useMemo, useState } from "react";
import { livestockService } from "../../../services/livestockService.js";
import "../../../components/LivestockModals/LivestockModals.css";
import "./PenManagementModal.css";

const PURPOSES = [
    "General",
    "Brooder / Nursery",
    "Nursing / Farrowing",
    "Weaner",
    "Growing",
    "Breeding",
    "Pregnancy / Maternity",
    "Layer / Egg Production",
    "Meat / Finisher",
    "Market Ready",
    "Isolation / Sick",
    "Observation",
    "Quarantine",
    "Recovery",
];

const SPECIES = ["", "Pig", "Goat", "Chicken", "Duck", "Cattle", "All Livestock"];
const STATUSES = ["Active", "Maintenance", "Inactive", "Closed"];

function emptyPen() {
    return {
        name: "",
        purpose: "General",
        animalType: "",
        capacity: "",
        locationArea: "",
        status: "Active",
        notes: "",
    };
}

function penToForm(pen) {
    return {
        name: pen.name || "",
        purpose: pen.purpose || "General",
        animalType: pen.animalType || "",
        capacity: pen.capacity ?? "",
        locationArea: pen.locationArea || "",
        status: pen.status === "Full" ? "Active" : (pen.status || "Active"),
        notes: pen.notes || "",
    };
}

function statusClass(status = "") {
    return status.toLowerCase().replaceAll(" ", "-");
}

export default function PenManagementModal({ open, onClose, onChanged }) {
    const [pens, setPens] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editingPen, setEditingPen] = useState(null);
    const [formOpen, setFormOpen] = useState(false);
    const [form, setForm] = useState(emptyPen);
    const [busy, setBusy] = useState(false);

    const loadPens = async () => {
        setLoading(true);
        try {
            setPens(await livestockService.getPens(true));
        } catch (error) {
            console.error("Failed to load pens:", error);
            notify(error?.message || "Unable to load pen records.");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        if (!open) return;
        loadPens();
        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = "";
        };
    }, [open]);

    const activePens = useMemo(
        () => pens.filter((pen) => ["Active", "Full"].includes(pen.status)),
        [pens]
    );

    if (!open) return null;

    const startAdd = () => {
        setEditingPen(null);
        setForm(emptyPen());
        setFormOpen(true);
    };

    const startEdit = (pen) => {
        setEditingPen(pen);
        setForm(penToForm(pen));
        setFormOpen(true);
    };

    const updateField = (event) => {
        const { name, value } = event.target;
        setForm((current) => ({ ...current, [name]: value }));
    };

    const savePen = async (event) => {
        event.preventDefault();
        if (!form.name.trim()) {
            notify("Pen name is required.");
            return;
        }
        if (form.capacity && Number(form.capacity) < 1) {
            notify("Capacity must be at least 1.");
            return;
        }

        setBusy(true);
        try {
            const payload = {
                ...form,
                capacity: form.capacity ? Number(form.capacity) : null,
            };
            if (editingPen) {
                await livestockService.updatePen(editingPen.id, payload);
            } else {
                await livestockService.createPen(payload);
            }
            await loadPens();
            await onChanged?.();
            setFormOpen(false);
            setEditingPen(null);
            setForm(emptyPen());
            notify(editingPen ? "Pen updated successfully." : "Pen created successfully.");
        } catch (error) {
            console.error("Failed to save pen:", error);
            notify(error?.message || "Unable to save pen.");
        } finally {
            setBusy(false);
        }
    };

    const closePen = async (pen) => {
        const confirmed = await confirmAction({
            title: "Close Pen",
            message: `Close ${pen.name}? The pen must have zero active livestock before it can be closed.`,
            type: "warning",
            confirmText: "Close Pen",
            cancelText: "Cancel",
        });
        if (!confirmed) return;
        setBusy(true);
        try {
            await livestockService.updatePen(pen.id, {
                name: pen.name,
                animalType: pen.animalType,
                purpose: pen.purpose,
                capacity: pen.capacity,
                locationArea: pen.locationArea,
                status: "Closed",
                notes: pen.notes,
            });
            await loadPens();
            await onChanged?.();
            notify("Pen closed successfully.");
        } catch (error) {
            notify(error?.message || "Unable to close pen.");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div className="livestock-modal-overlay" onMouseDown={onClose}>
            <section className="pen-management-modal" onMouseDown={(event) => event.stopPropagation()}>
                <header className="livestock-modal-header">
                    <div>
                        <h2>Pen Management</h2>
                        <p>Create purpose-based pens and monitor capacity without leaving Livestock Management.</p>
                    </div>
                    <button type="button" onClick={onClose} aria-label="Close">
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </header>

                <div className="pen-management-body">
                    <div className="pen-management-toolbar">
                        <div>
                            <strong>{activePens.length} active pens</strong>
                            <span>Purpose, species compatibility, and occupancy are used when assigning livestock.</span>
                        </div>
                        <button type="button" className="pen-add-button" onClick={startAdd}>
                            <span className="material-symbols-outlined">add</span>
                            Add Pen
                        </button>
                    </div>

                    {formOpen && (
                        <form className="pen-editor-card" onSubmit={savePen}>
                            <div className="pen-editor-heading">
                                <div>
                                    <h3>{editingPen ? "Edit Pen" : "Add Pen"}</h3>
                                    <p>Set the pen purpose, species, capacity, area, and availability.</p>
                                </div>
                                <button type="button" onClick={() => setFormOpen(false)}>
                                    <span className="material-symbols-outlined">close</span>
                                </button>
                            </div>

                            <div className="pen-editor-grid">
                                <label>
                                    <span>Pen Name *</span>
                                    <input name="name" value={form.name} onChange={updateField} placeholder="Example: Layer Pen 1" required />
                                </label>
                                <label>
                                    <span>Purpose *</span>
                                    <select name="purpose" value={form.purpose} onChange={updateField}>
                                        {PURPOSES.map((item) => <option key={item}>{item}</option>)}
                                    </select>
                                </label>
                                <label>
                                    <span>Species Allowed</span>
                                    <select name="animalType" value={form.animalType} onChange={updateField}>
                                        {SPECIES.map((item) => (
                                            <option key={item || "any"} value={item}>{item || "Any / Not Restricted"}</option>
                                        ))}
                                    </select>
                                </label>
                                <label>
                                    <span>Capacity</span>
                                    <input name="capacity" type="number" min="1" step="1" value={form.capacity} onChange={updateField} placeholder="Optional" />
                                </label>
                                <label>
                                    <span>Area / Location</span>
                                    <input name="locationArea" value={form.locationArea} onChange={updateField} placeholder="Example: Poultry Area" />
                                </label>
                                <label>
                                    <span>Status</span>
                                    <select name="status" value={form.status} onChange={updateField}>
                                        {STATUSES.map((item) => <option key={item}>{item}</option>)}
                                    </select>
                                </label>
                                <label className="pen-editor-full">
                                    <span>Notes</span>
                                    <textarea name="notes" rows="3" value={form.notes} onChange={updateField} placeholder="Optional pen notes" />
                                </label>
                            </div>
                            <div className="pen-editor-actions">
                                <button type="button" className="pen-secondary-button" onClick={() => setFormOpen(false)}>Cancel</button>
                                <button type="submit" className="pen-primary-button" disabled={busy}>{busy ? "Saving..." : editingPen ? "Save Changes" : "Create Pen"}</button>
                            </div>
                        </form>
                    )}

                    <div className="pen-table-card">
                        <div className="pen-table-wrapper">
                            <table className="pen-table">
                                <thead>
                                    <tr>
                                        <th>Pen</th>
                                        <th>Purpose</th>
                                        <th>Species</th>
                                        <th>Capacity</th>
                                        <th>Occupancy</th>
                                        <th>Status</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {loading ? (
                                        <tr><td colSpan="7" className="pen-empty-row">Loading pens...</td></tr>
                                    ) : pens.length === 0 ? (
                                        <tr><td colSpan="7" className="pen-empty-row">No pens yet. Use Add Pen to create the first one.</td></tr>
                                    ) : pens.map((pen) => {
                                        const percent = pen.capacity ? Math.min(100, Math.round((pen.currentOccupancy / pen.capacity) * 100)) : null;
                                        return (
                                            <tr key={pen.id}>
                                                <td>
                                                    <strong>{pen.name}</strong>
                                                    <small>{pen.locationArea || "No area specified"}</small>
                                                </td>
                                                <td><span className="pen-purpose-badge">{pen.purpose || "General"}</span></td>
                                                <td>{pen.animalType || "Any"}</td>
                                                <td>{pen.capacity ?? "No limit"}</td>
                                                <td>
                                                    <div className="pen-occupancy-cell">
                                                        <strong>{pen.currentOccupancy}{pen.capacity ? ` / ${pen.capacity}` : ""}</strong>
                                                        {percent !== null && <div className="pen-progress"><span style={{ width: `${percent}%` }} /></div>}
                                                    </div>
                                                </td>
                                                <td><span className={`pen-status-badge ${statusClass(pen.status)}`}>{pen.status}</span></td>
                                                <td>
                                                    <div className="pen-row-actions">
                                                        <button type="button" title="Edit pen" onClick={() => startEdit(pen)}><span className="material-symbols-outlined">edit</span></button>
                                                        {pen.status !== "Closed" && (
                                                            <button type="button" className="close-pen" title="Close pen" disabled={busy} onClick={() => closePen(pen)}><span className="material-symbols-outlined">block</span></button>
                                                        )}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </section>
        </div>
    );
}
