import { eventDomain, eventRecordChoices, eventRecordLocation } from '../../services/eventPlanning.js';
export default function EventContextFields({ form, onChange, resources, loading, error, retry, busy, needsResource }) {
    const domain = eventDomain(form.type);
    const general = domain === 'General';
    if (general && !needsResource) return null;
    const inventoryPlan = ['Inventory', 'Equipment'].includes(domain);
    const targets = [...eventRecordChoices(form, resources)].sort((a, b) => inventoryPlan
        ? Number(Number(a.quantity) > Number(a.reorder_level || 0)) - Number(Number(b.quantity) > Number(b.reorder_level || 0)) || a.name.localeCompare(b.name)
        : a.name.localeCompare(b.name));
    const selected = targets.find((row) => String(row.id) === String(form.sourceRecordId));
    const required = needsResource || domain === 'Inventory' || Boolean(form.assignedEmployeeId && ['Crop', 'Livestock'].includes(domain));
    const title = domain === 'Inventory' ? 'Item to Restock' : domain === 'Equipment' ? 'Equipment Maintenance' : 'Related Farm Record';
    const label = domain === 'Inventory' ? 'Inventory Item' : domain === 'Equipment' ? 'Equipment / Tool' : 'Related Record';
    return <section className="calendar-linked-work" aria-label="Event record selection">
        <h3>{title}</h3>
        {error && <p className="calendar-choice-error" role="status">{error} <button type="button" onClick={retry}>Retry records</button></p>}
        <div className="calendar-form-row two-columns">
            {general && <div className="calendar-form-group"><label htmlFor="eventSourceModule">Record Type *</label><select id="eventSourceModule" value={form.sourceModule} disabled={busy} onChange={(event) => onChange({ ...form, sourceModule: event.target.value, sourceRecordId: '', inventoryItemId: '', plannedQuantity: '', feedingSlot: '', location: '' })}><option value="Crop">Crop</option><option value="Livestock">Livestock</option></select></div>}
            <div className="calendar-form-group"><label htmlFor="eventSourceRecord">{label}{required ? ' *' : ' (optional)'}</label>
                <select id="eventSourceRecord" required={required} disabled={loading || busy} value={form.sourceRecordId} onChange={(event) => {
                    const target = targets.find((row) => String(row.id) === event.target.value);
                    onChange({ ...form, sourceRecordId: event.target.value, location: eventRecordLocation(target, form.sourceModule), inventoryItemId: '', plannedQuantity: '', feedingSlot: '' });
                }}><option value="">{loading ? 'Loading records…' : domain === 'Inventory' ? 'Select the item to restock' : domain === 'Equipment' ? 'Select equipment or use a custom location' : 'Select a related record or use a custom location'}</option>
                {targets.map((row) => <option key={row.id} value={row.id}>{row.name}{row.field ? ` — ${row.field}` : row.location ? ` — ${row.location}` : row.code ? ` — ${row.code}` : ''}{inventoryPlan ? ` (${Number(row.quantity) || 0} ${row.unit})` : ''}</option>)}</select>
            </div>
            {form.type === 'Livestock Feeding' && selected && <div className="calendar-form-group"><label htmlFor="eventFeedingSlot">Feeding Slot *</label><select id="eventFeedingSlot" value={form.feedingSlot || ''} disabled={busy} required={(selected.feeding_slots || []).length > 1} onChange={(event) => onChange({ ...form, feedingSlot: event.target.value })}><option value="">{selected.feeding_slots?.length === 1 ? selected.feeding_slots[0] : 'Select feeding slot'}</option>{(selected.feeding_slots || []).map((slot) => <option key={slot}>{slot}</option>)}</select></div>}
            {inventoryPlan && selected && <div className="calendar-form-group"><label>Current Stock</label><p className="calendar-stock-context">{Number(selected.quantity) || 0} {selected.unit} · Reorder level: {Number(selected.reorder_level) || 0} {selected.unit}</p></div>}
        </div>
        {!loading && !targets.length && <p className="calendar-choice-hint">{required ? 'Add the related record in its management page before scheduling this work.' : 'No related records are available. You can enter a custom location.'}</p>}
        {!form.assignedEmployeeId && !(['Livestock Feeding', 'Harvesting'].includes(form.type) && selected) && ['Crop', 'Livestock'].includes(domain) && <p>Without an assigned employee, this is a calendar reminder. Record performed work in its farm record or assign a task for review.</p>}
        {['Livestock Feeding', 'Harvesting'].includes(form.type) && selected && <p>This schedules operational work. Assign an employee before submission; approved work updates feeding or harvest records.</p>}
        <p>{domain === 'Inventory' ? 'This event schedules a delivery. Record received stock through Inventory → Stock Adjustment; scheduling or approving the task does not add or deduct stock.' : domain === 'Equipment' ? 'Choose equipment to use its storage location, or enter a location for unlisted equipment.' : 'Locations come from this type of farm record. You can also enter a custom field or pen name.'}</p>
    </section>;
}
