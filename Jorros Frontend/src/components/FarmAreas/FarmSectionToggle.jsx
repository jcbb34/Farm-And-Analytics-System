'use client';
import './FarmSectionToggle.css';

// One disclosure control for measured fields, master-plan sections and facility sub-areas.
export default function FarmSectionToggle({ label, count, expanded, onToggle, controls, variant = 'card', noun = 'section' }) {
    const plural = count === 1 ? noun : `${noun}s`;
    return <button type="button"
        className={`farm-section-toggle farm-section-toggle--${variant}${expanded ? ' is-expanded' : ''}`}
        onClick={onToggle} disabled={count === 0} aria-expanded={expanded} aria-controls={controls}
        aria-label={`${expanded ? 'Collapse' : 'Expand'} ${count} ${plural} for ${label}`}>
        <span className="material-symbols-outlined farm-section-toggle-arrow" aria-hidden="true">chevron_right</span>
        {variant === 'table' && <span className="farm-section-toggle-label">{label}</span>}
        <span className="farm-section-toggle-count">{count} {plural}</span>
    </button>;
}
