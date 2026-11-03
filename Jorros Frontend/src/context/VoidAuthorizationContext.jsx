"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { voidAuthorizationService } from "../services/voidAuthorizationService.js";
import "./VoidAuthorization.css";
const Context = createContext(null);

function AuthorizationDialog({ target, onClose, onDone }) {
    const [preview, setPreview] = useState(null), [error, setError] = useState(""), [loading, setLoading] = useState(true), [reload, setReload] = useState(0);
    const [reason, setReason] = useState(""), [username, setUsername] = useState(""), [password, setPassword] = useState(""), [otp, setOtp] = useState(""), [saving, setSaving] = useState(false);
    const busy = useRef(false), dialog = useRef(null), closeButton = useRef(null);
    useEffect(() => {
        const abort = new AbortController();
        setLoading(true); setPreview(null); setError("");
        voidAuthorizationService.preview(target.action, target.recordId, abort.signal).then((data) => { if (!abort.signal.aborted) setPreview(data); })
            .catch((failure) => { if (!abort.signal.aborted) setError(failure.message || "Unable to load the record."); }).finally(() => { if (!abort.signal.aborted) setLoading(false); });
        return () => abort.abort();
    }, [target.action, target.recordId, reload]);
    useEffect(() => {
        const previousFocus = document.activeElement, overflow = document.body.style.overflow;
        document.body.style.overflow = "hidden"; closeButton.current?.focus();
        return () => { document.body.style.overflow = overflow; previousFocus?.focus?.(); };
    }, []);
    const cancel = () => { if (!busy.current) onClose(); };
    const submit = async (event) => {
        event.preventDefault();
        if (busy.current || !preview) return;
        if (reason.trim().length < 3) { setError("Enter a reason of at least three non-space characters."); return; }
        busy.current = true; setSaving(true); setError("");
        try {
            await voidAuthorizationService.authorize({ preview_token: preview.preview_token, reason: reason.trim(), ...(preview.requires_owner_credentials ? { owner_username: username.trim(), owner_password: password, otp_code: otp || null } : {}) });
            onDone();
        } catch (failure) {
            setError(failure.message || "Authorization failed. Check the record before retrying.");
            if (failure.status === 409) { try { await target.onStale?.(); } catch {} }
        }
        finally { setPassword(""); setOtp(""); busy.current = false; setSaving(false); }
    };
    return createPortal(<div className="void-authorization-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) cancel(); }}>
        <section ref={dialog} role="dialog" aria-modal="true" aria-labelledby="void-authorization-title" className="void-authorization-dialog" onKeyDown={(event) => {
            if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); cancel(); }
            if (event.key === "Tab") {
                const fields = [...dialog.current.querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled)')], first = fields[0], last = fields.at(-1);
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
        }}><header><div><h2 id="void-authorization-title">Owner/Admin Void Authorization</h2><p>Review the record and its reversal before confirming.</p></div><button ref={closeButton} type="button" aria-label="Close void authorization" disabled={saving} onClick={cancel}>×</button></header>
            <form onSubmit={submit} autoComplete="off"><div className="void-authorization-body">
                {loading && <p role="status">Loading current record...</p>}
                {preview && <><article className="void-record-preview"><strong>{preview.label}</strong><p>{preview.impact}</p></article>
                    <label htmlFor="void-authorization-reason">Reason for voiding *</label><textarea id="void-authorization-reason" required minLength={3} maxLength={300} rows={3} value={reason} disabled={saving} onChange={(event) => setReason(event.target.value)}/>
                    {preview.requires_owner_credentials && <fieldset disabled={saving}><legend>Owner/Admin confirmation</legend><p>The Owner/Admin must enter their credentials personally. Your employee account stays signed in.</p>
                        <label htmlFor="void-owner-username">Owner/Admin username *</label><input id="void-owner-username" required maxLength={50} autoComplete="off" value={username} onChange={(event) => setUsername(event.target.value)}/>
                        <label htmlFor="void-owner-password">Owner/Admin password *</label><input id="void-owner-password" type="password" required maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)}/>
                        <label htmlFor="void-owner-code">Authenticator code (if enabled)</label><input id="void-owner-code" inputMode="numeric" autoComplete="off" maxLength={6} pattern="[0-9]{6}" value={otp} onChange={(event) => setOtp(event.target.value)}/>
                    </fieldset>}
                    <p className="void-authorization-note">Approval applies only to this record. Original history, requester, authorizer and reason are retained.</p></>}
                {error && <div className="void-authorization-error" role="alert"><p>{error}</p><button type="button" disabled={saving} onClick={() => setReload((current) => current + 1)}>Reload current record</button></div>}
            </div><footer><button type="button" disabled={saving} onClick={cancel}>Cancel</button><button type="submit" className="void-confirm" disabled={saving || loading || !preview}>{saving ? "Authorizing..." : preview?.requires_owner_credentials ? "Authorize & Void" : "Void Record"}</button></footer></form>
        </section></div>, document.body);
}

export function VoidAuthorizationProvider({ children }) {
    const [target, setTarget] = useState(null), resolver = useRef(null);
    const requestVoid = useCallback((value) => resolver.current ? Promise.resolve(false) : new Promise((resolve) => { resolver.current = resolve; setTarget(value); }), []);
    const finish = (approved) => { const resolve = resolver.current; resolver.current = null; setTarget(null); resolve?.(approved); };
    useEffect(() => () => resolver.current?.(false), []);
    return <Context.Provider value={requestVoid}>{children}{target && <AuthorizationDialog target={target} onClose={() => finish(false)} onDone={() => finish(true)}/>}</Context.Provider>;
}
export function useVoidAuthorization() {
    const requestVoid = useContext(Context);
    if (!requestVoid) throw new Error("VoidAuthorizationProvider is required.");
    return requestVoid;
}
