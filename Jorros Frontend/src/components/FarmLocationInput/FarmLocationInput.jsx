'use client';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { canonicalLocationName, cleanLocationName, farmLocationService, locationSearchKey, uniqueLocationNames } from '../../services/farmLocationService.js';
import { eventDomain } from '../../services/eventPlanning.js';
import './FarmLocationInput.css';

function locationWords(context, eventType, sourceModule) {
    let domain = context === 'crops' ? 'Crop' : context === 'inventory' ? 'Inventory' : eventDomain(eventType);
    if (domain === 'General' && sourceModule) domain = sourceModule;
    if (domain === 'Crop') return { singular: 'crop field', plural: 'crop fields', custom: 'field name' };
    if (domain === 'Inventory' || domain === 'Equipment') return { singular: 'warehouse or storage area', plural: 'storage locations', custom: 'storage name' };
    if (domain === 'Livestock') return { singular: 'pen or livestock area', plural: 'pens and livestock areas', custom: 'pen or area name' };
    return { singular: 'farm location', plural: 'farm locations', custom: 'location name' };
}

export default function FarmLocationInput({ id: suppliedId, name, label, context, value, onValueChange, active = true, required = false, maxLength = 150, knownOptions = [], eventType, sourceModule, sourceRecordId, readOnly = false }) {
    const generatedId = useId(), id = suppliedId || generatedId;
    const input = useRef(null), list = useRef(null);
    const [lookup, setLookup] = useState({ key: '', names: [], status: 'idle' });
    const [retry, setRetry] = useState(0), [open, setOpen] = useState(false), [query, setQuery] = useState(''), [highlighted, setHighlighted] = useState(-1);
    const lookupKey = JSON.stringify([context, eventType || '', sourceModule || '', sourceRecordId || '', retry]);
    const words = locationWords(context, eventType, sourceModule);
    const options = useMemo(() => uniqueLocationNames([...(lookup.key === lookupKey ? lookup.names : []), ...knownOptions]), [lookup, lookupKey, knownOptions]);
    const loading = active && (lookup.key !== lookupKey || lookup.status === 'loading');
    const error = lookup.key === lookupKey && lookup.status === 'error';
    useEffect(() => {
        setHighlighted(-1); setQuery('');
        if (!active || readOnly) { setOpen(false); return; }
        const controller = new AbortController(); let alive = true;
        setLookup({ key: lookupKey, names: [], status: 'loading' });
        farmLocationService.getChoices(context, controller.signal, { eventType, sourceModule, sourceRecordId })
            .then((names) => { if (alive) setLookup({ key: lookupKey, names, status: 'loaded' }); })
            .catch(() => { if (alive) setLookup({ key: lookupKey, names: [], status: 'error' }); });
        return () => { alive = false; controller.abort(); };
    }, [context, active, lookupKey, readOnly, eventType, sourceModule, sourceRecordId]);
    const filtered = useMemo(() => options.filter((option) => locationSearchKey(option).includes(locationSearchKey(query))), [options, query]);
    const customName = cleanLocationName(value);
    const custom = Boolean(customName && !options.some((option) => option.toLocaleLowerCase() === customName.toLocaleLowerCase()));
    const choices = custom ? [...filtered, customName] : filtered;
    const close = () => { setOpen(false); setHighlighted(-1); };
    const choose = (selected) => { onValueChange(canonicalLocationName(selected, options)); close(); };
    useEffect(() => { if (highlighted >= 0) list.current?.querySelector(`[data-choice="${highlighted}"]`)?.scrollIntoView({ block: 'nearest' }); }, [highlighted]);
    return <div className="farm-location-picker" onBlur={(event) => {
        if (readOnly || event.currentTarget.contains(event.relatedTarget)) return;
        onValueChange(canonicalLocationName(value, options)); close();
    }}>
        <div className="farm-location-control">
            <input ref={input} id={id} name={name} role="combobox" aria-label={label} aria-autocomplete="list" aria-haspopup="listbox"
                aria-expanded={open && !readOnly} aria-controls={`${id}-options`} aria-describedby={`${id}-hint`}
                aria-activedescendant={open && highlighted >= 0 && choices[highlighted] ? `${id}-choice-${highlighted}` : undefined}
                autoComplete="off" required={required} readOnly={readOnly} maxLength={maxLength} value={value || ''} placeholder={`Search or choose a ${words.singular}`}
                onFocus={() => { if (!readOnly) { setQuery(''); setHighlighted(-1); setOpen(true); } }}
                onChange={(event) => { onValueChange(event.target.value); setQuery(event.target.value); setHighlighted(-1); setOpen(true); }}
                onKeyDown={(event) => {
                    if (readOnly) return;
                    if (event.key === 'Escape' && open) { event.preventDefault(); event.stopPropagation(); close(); }
                    if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
                        event.preventDefault(); setOpen(true);
                        setHighlighted((current) => choices.length ? (current < 0 ? (event.key === 'ArrowDown' ? 0 : choices.length - 1) : Math.max(0, Math.min(choices.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)))) : -1);
                    }
                    if (event.key === 'Enter' && open) { event.preventDefault(); choose(choices[highlighted] ?? value); }
                    if (event.key === 'Tab') close();
                }} />
            {!readOnly && <button type="button" className="farm-location-toggle" aria-label={`Show saved ${words.plural}`} aria-expanded={open}
                onPointerDown={(event) => event.preventDefault()} onClick={() => { const next = !open; input.current?.focus(); setQuery(''); setHighlighted(-1); setOpen(next); }}>
                <span className="material-symbols-outlined" aria-hidden="true">expand_more</span>
            </button>}
            {open && !readOnly && <div id={`${id}-options`} className="farm-location-options" role="listbox" aria-label={`${label} suggestions`} ref={list}>
                {filtered.map((option, index) => <button key={option} type="button" role="option" id={`${id}-choice-${index}`} data-choice={index}
                    aria-selected={highlighted === index} className="farm-location-option" onPointerDown={(event) => event.preventDefault()} onClick={() => choose(option)}>{option}</button>)}
                {custom && <button type="button" role="option" id={`${id}-choice-${filtered.length}`} data-choice={filtered.length} aria-selected={highlighted === filtered.length}
                    className="farm-location-option farm-location-custom" onPointerDown={(event) => event.preventDefault()} onClick={() => choose(customName)}>Use “{customName}” as a new name</button>}
                {!choices.length && <p className="farm-location-empty">{loading ? `Loading saved ${words.plural}…` : error ? `Saved ${words.plural} are unavailable. Type a custom ${words.custom}.` : `No saved ${words.plural} found. Type a new ${words.custom}.`}</p>}
            </div>}
        </div>
        <small id={`${id}-hint`} className="farm-location-hint">{readOnly ? value ? 'From the selected record.' : 'No location is recorded. Set it in its management page first.' : error ? `Saved locations could not be loaded.${options.length ? ' Showing locations from loaded records.' : ' Custom entry is available.'}` : custom ? 'New name — saved with this record.' : `Choose an existing ${words.singular} or type a custom ${words.custom}.`}
            {error && !readOnly && <button type="button" onClick={() => setRetry((old) => old + 1)}>Retry list</button>}
        </small>
    </div>;
}
