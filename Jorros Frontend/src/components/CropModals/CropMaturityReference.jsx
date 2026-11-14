"use client";

import { useEffect, useMemo, useState } from "react";
import { cropService } from "../../services/cropService.js";
import "./CropMaturityPanel.css";

function addDays(date, days) {
    if (!date || days == null) return null;
    const d = new Date(`${date}T12:00:00Z`);
    if (Number.isNaN(d.getTime())) return null;
    d.setUTCDate(d.getUTCDate() + Number(days));
    return d.toISOString().slice(0, 10);
}

export default function CropMaturityReference({ form, setForm, editing, disabled }) {
    const [reference, setReference] = useState(null);
    const [loadError, setLoadError] = useState("");
    const name = String(form.name || "").trim();
    const variety = String(form.variety || "").trim();
    useEffect(() => {
        let active = true;
        setReference(null);
        setLoadError("");
        if (!name || !variety) return () => { active = false; };
        cropService.getMaturityReference(name, variety).then(row => {
            if (active) setReference(row);
        }).catch(() => {
            if (active) setLoadError("Maturity reference unavailable. You can still save this crop.");
        });
        return () => { active = false; };
    }, [name, variety]);
    const proposed = useMemo(() => {
        if (!reference || reference.anchor_kind !== "planting" || !form.plantingDate || form.planting_date_precision === "unknown") return null;
        const from = addDays(form.plantingDate, reference.min_days);
        const to = addDays(form.plantingDate, reference.max_days);
        return from && to ? { from, to } : null;
    }, [reference, form.plantingDate, form.planting_date_precision]);

    if (!name || !variety) return null;
    return <div className="crop-maturity-reference crop-reference-on-form" aria-live="polite">
        <strong>Variety maturity guidance — {name} {variety}</strong>
        {reference ? <>
            <span>{reference.min_days != null ? `Reference period: ${reference.min_days}–${reference.max_days} days after ${reference.anchor_kind}.` : "A verified day/month maturity range is not available for this variety."}</span>
            {proposed && <span>Calculated window from planting date: <b>{proposed.from} to {proposed.to}</b>.
                {!form.estimatedHarvest && !disabled && <button type="button" className="crop-maturity-adopt" onClick={() => setForm(current => ({ ...current, estimatedHarvest: proposed.from }))}>Use suggested date</button>}
            </span>}
            {reference.anchor_kind === "shooting" && <span>Banana timing begins when shooting is observed, not when the sucker is first planted. Record it later in Crop Details.</span>}
            {reference.anchor_kind === "flowering" && <span>Coconut fruit maturity depends on the actual flowering date and intended product. Record flowering later in Crop Details.</span>}
            {!proposed && reference.anchor_kind === "planting" && <span>Record a planting date to calculate the variety's estimated harvest window.</span>}
            <small>{reference.source || "Agricultural reference"} · An estimate never confirms physical readiness.</small>
        </> : <span>{loadError || "Loading agricultural maturity reference…"}</span>}
    </div>;
}
