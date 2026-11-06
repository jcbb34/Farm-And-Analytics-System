'use client';
import { useEffect, useRef } from 'react';
import useModalScrollLock from '../../hooks/useModalScrollLock.js';
import './SessionTimeoutWarning.css';

export default function SessionTimeoutWarning({ open, seconds, reason, busy, error, onStay, onKeepWorking, onLogout }) {
    const ref = useRef(null);
    useModalScrollLock(open);
    useEffect(() => {
        if (!open) return undefined;
        const previous = document.activeElement;
        ref.current?.querySelector('button')?.focus();
        const key = (event) => {
            if (event.key === 'Tab') {
                const buttons = [...ref.current.querySelectorAll('button:not(:disabled)')];
                const first = buttons[0], last = buttons.at(-1);
                if (!buttons.includes(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first)?.focus(); }
                else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); if (reason === 'absolute') onKeepWorking(); }
        };
        document.addEventListener('keydown', key, true);
        return () => { document.removeEventListener('keydown', key, true); if (previous?.isConnected) previous.focus(); };
    }, [open, reason, onKeepWorking]);
    if (!open) return null;
    return <div className="session-warning-overlay" data-session-warning>
        <section className="session-warning" ref={ref} role="alertdialog" aria-modal="true" aria-labelledby="session-warning-title" aria-describedby="session-warning-description">
            <h2 id="session-warning-title">Your session will end soon</h2>
            <p id="session-warning-description">{reason === 'absolute' ? 'You have reached the session time limit. Save your work before signing in again.' : 'There has been no activity. Choose Stay signed in to continue working.'}</p>
            <p className="session-warning-countdown" role="timer" aria-live="off">Signing out in {seconds} seconds</p>
            {error && <p role="status" className="session-warning-error">{error}</p>}
            <footer>
                <button type="button" className="session-warning-primary" disabled={busy} onClick={reason === 'absolute' ? onKeepWorking : onStay}>{busy ? 'Checking…' : reason === 'absolute' ? 'Keep working' : 'Stay signed in'}</button>
                <button type="button" onClick={onLogout}>Sign out now</button>
            </footer>
        </section>
    </div>;
}
