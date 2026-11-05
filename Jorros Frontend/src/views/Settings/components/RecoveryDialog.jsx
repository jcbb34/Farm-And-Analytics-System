'use client';
import { useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import useModalScrollLock from '../../../hooks/useModalScrollLock.js';
export function RecoveryDialog({ title, onClose, busy = false, children, wide = false, returnFocusRef }) {
    const id = useId(), ref = useRef(), latest = useRef({ onClose, busy }); latest.current = { onClose, busy };
    useModalScrollLock(true);
    useEffect(() => {
        const previous = returnFocusRef?.current || document.activeElement;
        ref.current.querySelector('button:not(:disabled),input:not(:disabled),select:not(:disabled)')?.focus();
        const keyboard = event => {
            if (event.key === 'Escape' && !latest.current.busy) { event.preventDefault(); latest.current.onClose(); }
            if (event.key !== 'Tab') return;
            const controls = [...ref.current.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]')].filter(el => el.getClientRects().length);
            const first = controls[0], last = controls.at(-1);
            if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
            else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        };
        document.addEventListener('keydown', keyboard);
        return () => { document.removeEventListener('keydown', keyboard); if (previous?.isConnected) previous.focus(); };
    }, []);
    useEffect(() => {
        if (!busy && ref.current && !ref.current.contains(document.activeElement)) {
            ref.current.querySelector('button:not(:disabled),input:not(:disabled),select:not(:disabled)')?.focus();
        }
    }, [busy]);
    return createPortal(<div className="br-overlay" onMouseDown={event => { if (event.target === event.currentTarget && !busy) { event.preventDefault(); onClose(); } }}><section role="dialog" aria-modal="true" aria-labelledby={id} ref={ref} className={'br-dialog' + (wide ? ' br-wide-dialog' : '')}><header><h2 id={id}>{title}</h2><button type="button" aria-label={'Close ' + title} disabled={busy} onClick={onClose}>×</button></header><div className="br-dialog-body">{children}</div></section></div>, document.body);
}
export function CredentialsForm({ action, onSubmit, onBusy = () => {}, confirmation = false }) {
    const [password, setPassword] = useState(''), [otp, setOtp] = useState(''), [word, setWord] = useState(''), [agreed, setAgreed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
    return <form className="br-form" onSubmit={async event => {
        event.preventDefault(); if (busy) return; setBusy(true); onBusy(true); setError('');
        try { await onSubmit({ password, otp_code: otp, ...(confirmation ? { confirmation: word } : {}) }); }
        catch (failure) { setError(failure.message || 'Administrator verification failed.'); }
        finally { setPassword(''); setOtp(''); setBusy(false); onBusy(false); }
    }}>
        <p>{confirmation ? 'The verified copy replaces current farm records and photos. A safety backup and the previous copy will be retained.' : 'Verify your administrator account. Keep the downloaded recovery key separately from your backups.'}</p>
        <label>Current password<input type="password" autoComplete="current-password" maxLength={128} required value={password} onChange={event => setPassword(event.target.value)}/></label>
        <label>6-digit authenticator code (if enabled)<input inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={otp} onChange={event => setOtp(event.target.value.replace(/\D/g, ''))}/></label>
        {confirmation && <><label>Type RESTORE to confirm<input required pattern="RESTORE" autoComplete="off" value={word} onChange={event => setWord(event.target.value)}/></label><label className="br-check"><input type="checkbox" required checked={agreed} onChange={event => setAgreed(event.target.checked)}/>I understand this replaces current farm data and requires everyone to sign in again.</label></>}
        {error && <p role="alert" className="br-error">{error}</p>}
        <footer><button className={confirmation ? 'br-danger' : 'br-primary'} disabled={busy || (confirmation && (!agreed || word !== 'RESTORE'))}>{busy ? 'Verifying...' : action}</button></footer>
    </form>;
}
export function Status({ value = 'Not recorded' }) {
    const positive = ['Completed', 'Connected', 'Ready', 'File validated', 'Restore tested'].includes(value), negative = ['Failed', 'Partial', 'Incomplete', 'Test failed', 'Needs attention', 'Needs reconnection'].includes(value);
    return <span className={'br-status ' + (positive ? 'positive' : negative ? 'negative' : '')}>{value}</span>;
}
export function backupDate(value, fallback = 'Not recorded', zone = 'Asia/Manila') {
    if (!value || Number.isNaN(new Date(value).getTime())) return fallback;
    return new Date(value).toLocaleString('en-PH', { timeZone: zone, year: 'numeric', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}
export function backupSize(value = 0) { const units = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0, size = Number(value); while (size >= 1024 && i < 4) { size /= 1024; i++; } return size.toFixed(i ? 1 : 0) + ' ' + units[i]; }
