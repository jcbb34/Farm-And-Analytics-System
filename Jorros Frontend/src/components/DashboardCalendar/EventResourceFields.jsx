import { resourceFitsTask } from '../../views/TaskManagement/taskManagementUtils.js';
export default function EventResourceFields({ form, onChange, resources, loading, busy }) {
    const inventory = resources.inventory.filter((item) => resourceFitsTask(item, form.sourceModule, `${form.title} ${form.type}`));
    const selected = inventory.find((item) => String(item.id) === String(form.inventoryItemId));
    return <section className="calendar-linked-work" aria-label="Linked work resources">
        <h3>Supplies for This Work</h3><p>Choose the stock to use. Actual consumption is recorded with employee evidence and deducted after approval.</p>
        <div className="calendar-form-row two-columns">
            <div className="calendar-form-group"><label htmlFor="eventInventoryResource">Inventory Resource *</label><select id="eventInventoryResource" required disabled={loading || busy} value={form.inventoryItemId} onChange={(event) => onChange({ ...form, inventoryItemId: event.target.value, plannedQuantity: '' })}><option value="">Select compatible inventory</option>{inventory.map((row) => <option key={row.id} value={row.id} disabled={Number(row.quantity) <= 0}>{row.name} — {row.quantity} {row.unit}</option>)}</select></div>
            <div className="calendar-form-group"><label htmlFor="eventPlannedQuantity">Planned Quantity *{selected ? ` (${selected.unit})` : ''}</label><input id="eventPlannedQuantity" type="number" required disabled={busy} min="0.001" step="0.001" max={selected?.quantity || undefined} value={form.plannedQuantity} onChange={(event) => onChange({ ...form, plannedQuantity: event.target.value })} /></div>
        </div>
        {!loading && !inventory.length && <p className="calendar-choice-hint">No compatible stock is available for this work. Seed usage is recorded through Crops when creating the crop.</p>}
    </section>;
}
