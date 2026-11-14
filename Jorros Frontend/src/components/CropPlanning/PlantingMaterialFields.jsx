"use client";
import { useEffect, useMemo, useState } from "react";
import { cropPlanningService } from "../../services/cropPlanningService.js";

export default function PlantingMaterialFields({ form, setForm, capacity, disabled = false }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const count = Number(form.quantityPlanted || 0);
    const validCount = Number.isInteger(count) && count > 0;
    const selected = useMemo(
        () => items.find(item => Number(item.id) === Number(form.planting_inventory_item_id)),
        [items, form.planting_inventory_item_id],
    );
    const unitsPerPosition = Number(selected?.units_per_position);
    const needed = selected && validCount && Number.isFinite(unitsPerPosition) && unitsPerPosition > 0
        ? count * unitsPerPosition : null;
    const available = Number(selected?.available);
    const stockOK = needed !== null && Number.isFinite(available) && available >= needed;
    const varietyChosen = Boolean(form.crop_reference && form.variety_reference);
    const exceedsCapacity = capacity != null && validCount && count > capacity;

    useEffect(() => {
        if (!form.crop_reference || !form.variety_reference) {
            setItems([]);
            setError("");
            return;
        }
        let alive = true;
        // Clear stale stock figures while switching crop varieties.
        setItems([]);
        setLoading(true);
        setError("");
        cropPlanningService.plantingMaterials(
            form.crop_reference,
            form.variety_reference,
            form.plantingDate || null,
            validCount ? count : null,
        )
            .then(data => { if (alive) setItems(data.items || []); })
            .catch(err => {
                if (alive) {
                    setItems([]);
                    setError(err.message || "Unable to verify planting materials.");
                }
            })
            .finally(() => { if (alive) setLoading(false); });
        return () => { alive = false; };
    }, [form.crop_reference, form.variety_reference, form.plantingDate, count]);

    const inventoryPlaceholder = !varietyChosen ? "Choose a crop and variety first"
        : loading ? "Checking matching inventory…"
        : !items.length ? "No matching planting material available"
        : "Choose planting material from Inventory";
    const stockState = loading ? "Checking inventory"
        : error ? "Unable to check"
        : !selected ? "Inventory not selected"
        : needed === null ? "Enter planting quantity"
        : stockOK ? "Enough stock" : "Stock shortage";

    return <section className="crop-form-section crop-planting-materials" aria-labelledby="planting-materials-title">
        <div className="crop-form-section-title crop-material-title">
            <span className="material-symbols-outlined" aria-hidden="true">inventory_2</span>
            <div className="crop-material-title-copy">
                <h3 id="planting-materials-title">Planting Materials &amp; Inventory</h3>
                <p>Select stock for this crop variety and set the employee's planting time.</p>
            </div>
            <span className="crop-material-context">New planting</span>
        </div>

        <div className="crop-form-grid crop-material-inputs">
            <div className="crop-material-field">
                <label htmlFor="crop-planting-inventory">Planting material <span aria-hidden="true">*</span></label>
                <select id="crop-planting-inventory" required disabled={disabled || loading || !varietyChosen}
                    value={form.planting_inventory_item_id || ""}
                    aria-describedby="crop-planting-inventory-help"
                    onChange={event => setForm(old => ({
                        ...old,
                        planting_inventory_item_id: event.target.value ? Number(event.target.value) : null,
                    }))}>
                    <option value="">{inventoryPlaceholder}</option>
                    {items.map(item => <option key={item.id} value={item.id}>
                        {item.name} ({item.code}) — {item.available} {item.unit} available
                    </option>)}
                </select>
                <p className="crop-material-field-hint" id="crop-planting-inventory-help">
                    Only stock tagged to the selected crop and variety is listed.
                </p>
            </div>
            <div className="crop-material-field">
                <label htmlFor="crop-planting-time">Planting start time <span aria-hidden="true">*</span></label>
                <input id="crop-planting-time" required type="time"
                    value={form.planting_start_time || "08:00"} disabled={disabled}
                    aria-describedby="crop-planting-time-help"
                    onChange={event => setForm(old => ({ ...old, planting_start_time: event.target.value }))} />
                <p className="crop-material-field-hint" id="crop-planting-time-help">
                    The assigned employee's task uses the selected planting date and time.
                </p>
            </div>
        </div>

        <div className="crop-material-overview">
            <div className="crop-material-overview-heading">
                <div className="crop-material-overview-label">
                    <span className="material-symbols-outlined" aria-hidden="true">calculate</span>
                    <strong>Planting requirement</strong>
                </div>
                <span className={`crop-material-stock-state${stockOK ? " is-sufficient" : ""}${selected && needed !== null && !stockOK ? " is-insufficient" : ""}`}>
                    {stockState}
                </span>
            </div>
            <div className="crop-material-summary" aria-live="polite">
                <div><small>Spacing capacity</small><strong>{capacity == null ? "Not calculated" : `${capacity.toLocaleString()} positions`}</strong></div>
                <div><small>Planned positions</small><strong>{validCount ? count.toLocaleString() : "Enter quantity"}</strong></div>
                <div><small>Required material</small><strong>{needed === null ? "Select stock & quantity" : `${needed.toLocaleString()} ${selected.unit}`}</strong></div>
                <div><small>Available stock</small><strong>{selected && Number.isFinite(available) ? `${available.toLocaleString()} ${selected.unit}` : "Not selected"}</strong></div>
            </div>
        </div>

        {error && <p className="crop-material-warning" role="alert">{error}</p>}
        {exceedsCapacity && <p className="crop-material-warning" role="alert">
            Planned quantity exceeds the {capacity.toLocaleString()} positions allowed by this area and spacing. Reduce the count or adjust the measured area.
        </p>}
        {selected && needed !== null && !stockOK && <p className="crop-material-warning" role="alert">
            Insufficient inventory: requires {needed.toLocaleString()} {selected.unit}, but only {Number.isFinite(available) ? available.toLocaleString() : "an unknown quantity"} are unreserved. Restock or reduce the planting quantity; Save Crop will reject this plan.
        </p>}
        {!loading && !error && varietyChosen && !items.length && <p className="crop-material-guidance" role="status">
            <span className="material-symbols-outlined" aria-hidden="true">info</span>
            <span>No matching material is registered. Add a planting-material item in Inventory and tag it to this exact crop and variety.</span>
        </p>}
        {stockOK && !exceedsCapacity && <p className="crop-material-success">
            <span className="material-symbols-outlined" aria-hidden="true">check_circle</span>
            Enough matching material is available for the planned planting. Actual stock is deducted only after approved planting work.
        </p>}
    </section>;
}
