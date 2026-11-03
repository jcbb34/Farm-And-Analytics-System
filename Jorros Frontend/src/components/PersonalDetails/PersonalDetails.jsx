"use client";
import { useEffect, useId, useRef, useState } from "react";
import { getLocationChoices } from "../../services/locationReferenceService.js";
import { emptyPersonalDetails, SUFFIXES } from "./personalDetails.js";
import "./PersonalDetails.css";

function Location({ label, value, code, options, onChange, loading, error, retry }) {
    const id = useId(), [open, setOpen] = useState(false), [active, setActive] = useState(-1);
    const filtered = options.filter((option) => option.name.toLocaleLowerCase().includes((value || "").toLocaleLowerCase()));
    const choose = (option) => { onChange(option.name, option.code); setOpen(false); setActive(-1); };
    return <div className="personal-field personal-location" onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
        <label htmlFor={id}>{label}</label><input id={id} role="combobox" aria-expanded={open} aria-controls={`${id}-options`} aria-autocomplete="list" aria-activedescendant={active >= 0 ? `${id}-${active}` : undefined}
            autoComplete="off" maxLength={100} value={value || ""} placeholder={loading ? "Loading locations..." : "Search or type a custom entry"}
            onFocus={() => { setOpen(true); setActive(-1); }} onChange={(event) => { onChange(event.target.value, null); setOpen(true); setActive(-1); }}
            onKeyDown={(event) => {
                if (event.key === "Escape" && open) { event.preventDefault(); event.stopPropagation(); setOpen(false); }
                if (["ArrowDown", "ArrowUp"].includes(event.key)) {
                    event.preventDefault(); setOpen(true);
                    setActive((current) => current < 0 ? (event.key === "ArrowDown" ? 0 : filtered.length) : Math.max(0, Math.min(filtered.length, current + (event.key === "ArrowDown" ? 1 : -1))));
                }
                if (event.key === "Enter" && open) {
                    event.preventDefault();
                    const selected = active >= 0 ? filtered[active] : filtered.find((option) => option.name.toLocaleLowerCase() === (value || "").trim().toLocaleLowerCase());
                    if (selected) choose(selected);
                    else { onChange(value || "", null); setOpen(false); setActive(-1); }
                }
                if (event.key === "Tab") setOpen(false);
            }}/>
        {open && <div id={`${id}-options`} role="listbox" aria-label={`${label} choices`} className="personal-location-options">
            {filtered.map((option, index) => <button type="button" role="option" tabIndex={-1} id={`${id}-${index}`} key={option.code} aria-selected={code === option.code} className={active === index ? "active" : ""} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(option)}>{option.name}</button>)}
            <button type="button" role="option" tabIndex={-1} id={`${id}-${filtered.length}`} aria-selected={!code && Boolean(value)} className={`personal-custom-option ${active === filtered.length ? "active" : ""}`} onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(value || "", null); setOpen(false); }}>{value ? `Use “${value}” as a custom entry` : "Use custom entry — type the location above"}</button>
        </div>}
        <small>{code ? "Selected from address list" : value ? "Custom entry — saved as typed" : "Select a suggestion or type a location that is not listed."}</small>
        {error && <small className="personal-reference-error" role="status">Locations unavailable. Custom entry is available. <button type="button" onClick={retry}>Retry list</button></small>}
    </div>;
}

export function PersonalNameFields({ value, onChange, legacyFullName = "", isNew = false }) {
    const details = value || emptyPersonalDetails(), id = useId(), required = isNew || [details.first_name, details.middle_name, details.surname, details.suffix].some(Boolean);
    return <div className="personal-details-names">{!details.first_name && !details.surname && legacyFullName && <p className="personal-legacy-name">Recorded full name: <strong>{legacyFullName}</strong>. Leave the name fields blank to keep it, or enter the first name and surname to update it.</p>}
        <div className="personal-name-grid">{[["first_name", "First name", "given-name"], ["middle_name", "Middle name (optional)", "additional-name"], ["surname", "Surname", "family-name"]].map(([key, label, complete]) => <div className="personal-field" key={key}>
            <label htmlFor={`${id}-${key}`}>{label}{required && key !== "middle_name" ? " *" : ""}</label><input id={`${id}-${key}`} name={key} autoComplete={complete} required={required && key !== "middle_name"} maxLength={60} value={details[key] || ""} onChange={(event) => onChange({ ...details, [key]: event.target.value })}/></div>)}
            <div className="personal-field"><label htmlFor={`${id}-suffix`}>Suffix (optional)</label><select id={`${id}-suffix`} autoComplete="honorific-suffix" value={details.suffix || ""} onChange={(event) => onChange({ ...details, suffix: event.target.value })}><option value="">None</option>{SUFFIXES.map((suffix) => <option key={suffix}>{suffix}</option>)}</select></div>
        </div>
    </div>;
}

export function PersonalAddressFields({ value, onChange, legacyAddress = "" }) {
    const details = value || emptyPersonalDetails(), address = details.address || {}, id = useId();
    const [lists, setLists] = useState({ provinces: [], cities: [], barangays: [] }), [errors, setErrors] = useState({}), [loading, setLoading] = useState({}), [retry, setRetry] = useState(0);
    const cache = useRef({});
    useEffect(() => {
        let active = true;
        for (const [level, parent] of [["provinces", null], ["cities", address.province_code], ["barangays", address.city_code]]) {
            const key = `${level}:${parent || ""}`;
            if (level !== "provinces" && !parent) { setLists((current) => ({ ...current, [level]: [] })); setErrors((current) => ({ ...current, [level]: false })); setLoading((current) => ({ ...current, [level]: false })); continue; }
            if (cache.current[key]) { setLists((current) => ({ ...current, [level]: cache.current[key] })); setErrors((current) => ({ ...current, [level]: false })); setLoading((current) => ({ ...current, [level]: false })); continue; }
            setLists((current) => ({ ...current, [level]: [] })); setLoading((current) => ({ ...current, [level]: true }));
            getLocationChoices(level, parent).then((items) => {
                if (!active) return;
                cache.current[key] = items; setLists((current) => ({ ...current, [level]: cache.current[key] })); setErrors((current) => ({ ...current, [level]: false }));
            }).catch(() => { if (active) setErrors((current) => ({ ...current, [level]: true })); }).finally(() => { if (active) setLoading((current) => ({ ...current, [level]: false })); });
        }
        return () => { active = false; };
    }, [address.province_code, address.city_code, retry]);
    const update = (changes) => onChange({ ...details, address: { ...address, ...changes } });
    const location = (name, level, label) => <Location key={name} label={label} value={address[name]} code={address[`${name}_code`]} options={lists[level]} loading={loading[level]} error={errors[level]} retry={() => setRetry((current) => current + 1)}
        onChange={(text, code) => update({ [name]: text, [`${name}_code`]: code, ...(name === "province" ? { city: "", city_code: null, barangay: "", barangay_code: null } : name === "city" ? { barangay: "", barangay_code: null } : {}) })}/>;
    return <div className="personal-details-address"><h4>Address <small>(optional)</small></h4>{legacyAddress && !details.address && <p className="personal-legacy-name">Existing address: <strong>{legacyAddress}</strong>. It stays unchanged until a new address is entered.</p>}
        <div className="personal-address-grid"><div className="personal-field personal-wide"><label htmlFor={`${id}-street`}>House/Building Number and Street</label><input id={`${id}-street`} autoComplete="address-line1" maxLength={100} value={address.street || ""} onChange={(event) => update({ street: event.target.value })}/></div>
            <div className="personal-field personal-wide"><label htmlFor={`${id}-subdivision`}>Subdivision, Village, or Building Name (optional)</label><input id={`${id}-subdivision`} autoComplete="address-line2" maxLength={100} value={address.subdivision || ""} onChange={(event) => update({ subdivision: event.target.value })}/></div>
            {location("province", "provinces", "Province / address area")}{location("city", "cities", "City / Municipality")}{location("barangay", "barangays", "Barangay")}
            <div className="personal-field"><label htmlFor={`${id}-postal`}>Postal / ZIP Code</label><input id={`${id}-postal`} autoComplete="postal-code" inputMode="numeric" pattern="[0-9]{4}" maxLength={4} placeholder="Four digits" value={address.postal_code || ""} onChange={(event) => update({ postal_code: event.target.value })}/></div>
        </div></div>;
}
