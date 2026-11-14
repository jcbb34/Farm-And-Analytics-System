'use client';

export default function HarvestProductFields({ context, value, onChange }) {
    if (!context?.harvest_parts?.length) return null;
    const part = value.harvested_part || (context.harvest_parts.length === 1 ? context.harvest_parts[0] : '');
    const removes = ['roots', 'corms'].includes(part);
    return <>
        <label className="workforce-field crop-form-group">Harvested product<select required value={part} onChange={event => onChange({ ...value, harvested_part: event.target.value, plants_harvested_out: 0 })}>
            <option value="">Choose leaves, roots or another actual product</option>{context.harvest_parts.map(item => <option key={item}>{item}</option>)}
        </select></label>
        {removes && <label className="workforce-field crop-form-group">Plants harvested out<input type="number" min="1" step="1" required value={value.plants_harvested_out || ''} onChange={event => onChange({ ...value, harvested_part: part, plants_harvested_out: Number(event.target.value) })} /></label>}
        <p className="crop-planning-note">{context.guidance} Enter the actual measured harvest weight in kg; pieces or bunches are not converted automatically. Harvesting does not confirm that the land is cleared.</p>
    </>;
}
