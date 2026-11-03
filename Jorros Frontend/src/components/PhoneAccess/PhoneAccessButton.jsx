"use client";

import { useEffect, useRef, useState } from "react";

import useModalScrollLock from "../../hooks/useModalScrollLock.js";
import { httpClient } from "../../services/httpClient.js";

import "./PhoneAccessButton.css";

export default function PhoneAccessButton() {
    const dialogRef = useRef(null);
    const [open, setOpen] = useState(false);
    const [refresh, setRefresh] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [data, setData] = useState(null);
    const [selectedUrl, setSelectedUrl] = useState("");

    useModalScrollLock(open);

    useEffect(() => {
        if (!open) return undefined;
        const controller = new AbortController();
        setLoading(true);
        setError("");
        setData(null);
        httpClient.get("/system/phone-access", {
            cache: "no-store",
            signal: controller.signal,
        }).then((result) => {
            if (controller.signal.aborted) return;
            setData(result);
            setSelectedUrl(result.links?.[0]?.url || "");
        }).catch((requestError) => {
            if (!controller.signal.aborted) {
                setError(requestError.message || "Unable to load the phone QR code. Please try again.");
            }
        }).finally(() => {
            if (!controller.signal.aborted) setLoading(false);
        });
        return () => controller.abort();
    }, [open, refresh]);

    const links = data?.links || [];
    const selected = links.find((link) => link.url === selectedUrl) || links[0];

    const openDialog = () => {
        dialogRef.current.showModal();
        window.dispatchEvent(new Event("joross:modal-open"));
        setOpen(true);
    };

    const handleDialogKeyDown = (event) => {
        if (event.key !== "Tab") return;
        const controls = [...event.currentTarget.querySelectorAll("button:not(:disabled), a[href], select:not(:disabled)")];
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first?.focus();
        }
    };

    return (
        <>
            <button
                type="button"
                className="phone-access-trigger"
                title="Show phone QR code"
                aria-label="Show phone QR code"
                aria-haspopup="dialog"
                aria-expanded={open}
                aria-controls="phone-access-dialog"
                onClick={openDialog}
            >
                <span className="material-symbols-outlined" aria-hidden="true">qr_code_2</span>
            </button>
            <dialog
                id="phone-access-dialog"
                className="phone-access-dialog"
                ref={dialogRef}
                aria-labelledby="phone-access-title"
                aria-describedby="phone-access-description"
                onKeyDown={handleDialogKeyDown}
                onClose={() => setOpen(false)}
                onClick={(event) => {
                    if (event.target === event.currentTarget) dialogRef.current.close();
                }}
            >
                <div className="phone-access-content">
                    <header className="phone-access-heading">
                        <h2 id="phone-access-title">Open Joross Farm on your phone</h2>
                        <button type="button" aria-label="Close QR code" onClick={() => dialogRef.current.close()}>
                            <span className="material-symbols-outlined" aria-hidden="true">close</span>
                        </button>
                    </header>
                    <p id="phone-access-description">Scan the QR code with your phone camera, then sign in with your own account.</p>
                    <div className="phone-access-result" aria-live="polite" aria-busy={loading}>
                        {loading && <p role="status">Loading the current phone link…</p>}
                        {error && <p className="phone-access-error" role="alert">{error}</p>}
                        {!loading && !error && data && !selected && <p role="status">{data.message}</p>}
                        {!loading && !error && selected && (
                            <>
                                {links.length > 1 && (
                                    <label className="phone-access-select">
                                        Connection
                                        <select value={selected.url} onChange={(event) => setSelectedUrl(event.target.value)}>
                                            {links.map((link) => <option key={link.url} value={link.url}>{link.label} — {link.url}</option>)}
                                        </select>
                                    </label>
                                )}
                                <img className="phone-access-qr" src={selected.qrDataUrl} alt="QR code to open Joross Farm on your phone" width="256" height="256" />
                                <a className="phone-access-link" href={selected.url} target="_blank" rel="noopener noreferrer">{selected.url}</a>
                                <p className="phone-access-help">{selected.kind === "tailscale"
                                    ? "Keep Tailscale connected on this computer and your phone."
                                    : "Keep this computer and your phone on the same Wi-Fi or LAN."} Leave the farm system running on this computer.</p>
                            </>
                        )}
                    </div>
                    <button type="button" className="phone-access-refresh" disabled={loading} onClick={() => setRefresh((value) => value + 1)}>
                        Refresh QR code
                    </button>
                </div>
            </dialog>
        </>
    );
}
