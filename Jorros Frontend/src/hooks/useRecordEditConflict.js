"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { isRecordEditConflict, recordEditVersion } from "../services/recordEditing.js";

export default function useRecordEditConflict({ open, id, loadRecord, replaceForm }) {
    const [message, setMessage] = useState("");
    const [error, setError] = useState("");
    const [reloading, setReloading] = useState(false);
    const sequence = useRef(0), busy = useRef(false);
    useEffect(() => {
        setMessage(""); setError(""); setReloading(false); busy.current = false;
        return () => { ++sequence.current; };
    }, [open, id]);
    const handleError = useCallback(failure => {
        if (!isRecordEditConflict(failure)) return false;
        setMessage(failure.message); setError("");
        return true;
    }, []);
    const reload = useCallback(async () => {
        if (!open || !id || busy.current) return;
        busy.current = true; const request = ++sequence.current;
        setReloading(true); setError("");
        try {
            const latest = await loadRecord(id);
            if (request !== sequence.current) return;
            recordEditVersion(latest);
            replaceForm(latest); setMessage("");
        } catch (failure) {
            if (request === sequence.current) setError(failure?.message || "Unable to reload this record. Your entries are kept.");
        } finally {
            if (request === sequence.current) { busy.current = false; setReloading(false); }
        }
    }, [open, id, loadRecord, replaceForm]);
    return { message, error, reloading, handleError, reload };
}
