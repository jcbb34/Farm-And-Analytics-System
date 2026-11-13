"use client";

import { useEffect, useRef, useState } from "react";
import { observeWhenVisible } from "../../utils/observeWhenVisible.js";

export default function DeferredSection({ label, onReveal, children }) {
    const [visible, setVisible] = useState(false);
    const placeholder = useRef(null), onRevealRef = useRef(onReveal);
    onRevealRef.current = onReveal;
    useEffect(() => {
        if (!visible) return observeWhenVisible(placeholder.current, () => setVisible(true));
    }, [visible]);
    useEffect(() => { if (visible) onRevealRef.current?.(); }, [visible]);
    // Remove the placeholder entirely so existing grid and table layouts keep
    // their original direct children after the content is shown.
    if (visible) return children;
    return <div ref={placeholder} style={{ gridColumn: "1 / -1", minHeight: 84, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <button type="button" className="workforce-button secondary" onClick={() => setVisible(true)}>Show {label}</button>
    </div>;
}
