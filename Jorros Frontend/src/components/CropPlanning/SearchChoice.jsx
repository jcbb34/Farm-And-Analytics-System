'use client';
import { useId, useState } from 'react';
import { cropPlanningService } from '../../services/cropPlanningService.js';

export default function SearchChoice({ label, value, options, onChange, disabled = false, allowCustom = false, required = false }) {
    const id = useId();
    const [open, setOpen] = useState(false), [query, setQuery] = useState(''), [index, setIndex] = useState(0);
    const [error, setError] = useState('');
    const selected = options.find(option => String(option.value) === String(value));
    const filtered = options.filter(option => option.label.toLowerCase().includes(query.toLowerCase()));
    const custom = query.trim() && allowCustom && !options.some(option => option.label.toLowerCase() === query.trim().toLowerCase());
    const choices = custom ? [...filtered, { value: `custom:${query.trim().toLowerCase()}`, label: query.trim() }] : filtered;
    const choose = async option => {
        if (!option) return;
        if (custom && option.value === choices[choices.length - 1]?.value) {
            try {
                const result = await cropPlanningService.customReference(option.label);
                option = { ...option, value: result.reference };
            } catch (e) { setError(e.message || 'Unable to validate the custom name.'); return; }
        }
        onChange(option); setError(''); setOpen(false); setQuery(''); setIndex(0);
    };
    return <div className="crop-form-group crop-search-choice">
        <label htmlFor={id}>{label}{required && ' *'}</label>
        <input id={id} role="combobox" maxLength={100} autoComplete="off" aria-autocomplete="list" aria-expanded={open}
            aria-controls={`${id}-list`} aria-activedescendant={open && choices[index] ? `${id}-${index}` : undefined}
            disabled={disabled} required={required} value={open ? query : selected?.label || ''}
            placeholder={disabled ? 'Choose the parent first' : 'Search or choose…'}
            onFocus={() => { setQuery(''); setOpen(true); }}
            onBlur={() => setOpen(false)} onChange={event => { setQuery(event.target.value); setIndex(0); setOpen(true); }}
            onKeyDown={event => {
                if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); setIndex(old => Math.max(0, Math.min(choices.length - 1, old + (event.key === 'ArrowDown' ? 1 : -1)))); }
                if (event.key === 'Enter' && open) { event.preventDefault(); choose(choices[index]); }
                if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); }
            }} />
        {open && !disabled && <div className="crop-choice-list" role="listbox" id={`${id}-list`}>
            {choices.map((choice, n) => <button type="button" role="option" id={`${id}-${n}`} key={choice.value}
                aria-selected={n === index} onPointerDown={event => event.preventDefault()} onClick={() => choose(choice)}>
                {custom && n === choices.length - 1 ? `Use custom: ${choice.label}` : choice.label}
            </button>)}
            {!choices.length && <p>No saved choices. {allowCustom ? 'Type a custom name.' : 'Ask an administrator to configure this choice.'}</p>}
        </div>}
        {error && <small role="alert" className="crop-planning-error">{error}</small>}
    </div>;
}
