import { useCallback, useEffect, useRef, useState } from 'react';
import { authService } from '../services/authService.js';
import { appConfig } from '../config/appConfig.js';
import { IDLE_MS, initialSessionPolicy, serverSessionPolicy, publishSessionSignal, mergeSessionPolicy } from '../services/sessionPolicy.js';

export default function useSessionPolicy({ session, onPolicy, onExpire }) {
    const callbacks = useRef({ onPolicy, onExpire });
    callbacks.current = { onPolicy, onExpire };
    const runtime = useRef(null);
    const [view, setView] = useState({});
    const token = session?.accessToken;

    useEffect(() => {
        if (!token) { runtime.current = null; setView({}); return undefined; }
        const state = { token, policy: initialSessionPolicy(session), pending: false, lastSent: 0, trailing: null, ended: false, error: '', absoluteDismissed: false };
        runtime.current = state;
        const current = () => runtime.current === state && !state.ended;
        const tick = () => {
            if (!current()) return;
            const now = Date.now();
            const deadline = Math.min(state.policy.idleDeadline, state.policy.absoluteDeadline);
            if (deadline <= now) {
                state.ended = true;
                callbacks.current.onExpire(state.policy.absoluteDeadline <= now ? 'absolute' : 'idle', token);
                return;
            }
            const reason = state.policy.absoluteDeadline <= state.policy.idleDeadline ? 'absolute' : 'idle';
            setView({ token, warning: deadline - now <= state.policy.warningMs && !(reason === 'absolute' && state.absoluteDismissed), reason,
                seconds: Math.ceil((deadline - now) / 1000), busy: Boolean(state.renewing), error: state.error });
        };
        const update = (policy, broadcast = false) => {
            if (!current() || !policy) return;
            state.policy = mergeSessionPolicy(state.policy, policy);
            callbacks.current.onPolicy(state.policy, token);
            if (broadcast) publishSessionSignal('activity', state.policy.sessionId, state.policy);
            tick();
        };
        state.accept = (policy) => { if (current()) { state.policy = mergeSessionPolicy(state.policy, policy); tick(); } };
        const request = async (activity) => {
            if (!current()) return;
            if (state.pending) { if (activity) state.queuedActivity = true; return; }
            // Recheck the known deadlines before issuing any renewal request.
            tick();
            if (!current()) return;
            state.pending = true; state.renewing = activity; if (activity) state.lastSent = Date.now(); tick();
            try {
                const response = appConfig.useMockApi ? null : await (activity ? authService.reportActivity() : authService.getSessionPolicy());
                const policy = serverSessionPolicy(response);
                if (appConfig.useMockApi && activity) update({ ...state.policy, idleDeadline: Math.min(Date.now() + IDLE_MS, state.policy.absoluteDeadline) }, true);
                else if (policy) { state.error = ''; update(policy, activity); }
                else if (!appConfig.useMockApi) state.error = 'Unable to verify the session. Check your connection and try again.';
            } catch (error) {
                if (!current()) return;
                if (error?.status === 401) { state.ended = true; callbacks.current.onExpire('expired', token); }
                else state.error = 'Unable to verify the session. Check your connection and try again.';
            } finally {
                state.pending = false; state.renewing = false; tick();
                if (state.queuedActivity && current()) { state.queuedActivity = false; request(true); }
            }
        };
        state.request = request;
        const activity = (event) => {
            if (!event.isTrusted || !current() || document.hidden) return;
            if (event.target?.closest?.('[data-session-warning]')) return;
            // The warning requires an explicit choice; focus/Tab alone must not renew it.
            if (Math.min(state.policy.idleDeadline, state.policy.absoluteDeadline) - Date.now() <= state.policy.warningMs) return;
            if (Date.now() - state.lastSent >= 30000) request(true);
            else {
                clearTimeout(state.trailing);
                state.trailing = setTimeout(() => request(true), 1000);
            }
        };
        const resume = () => { tick(); if (current()) request(false); };
        const events = ['pointerdown', 'keydown', 'input', 'wheel', 'touchstart'];
        events.forEach((name) => document.addEventListener(name, activity, { passive: true }));
        window.addEventListener('focus', resume);
        document.addEventListener('visibilitychange', resume);
        const timer = setInterval(tick, 1000);
        const poll = setInterval(() => { if (current() && !document.hidden) request(false); }, 30000);
        tick(); request(false);
        return () => {
            state.ended = true;
            clearTimeout(state.trailing); clearInterval(timer); clearInterval(poll);
            events.forEach((name) => document.removeEventListener(name, activity));
            window.removeEventListener('focus', resume);
            document.removeEventListener('visibilitychange', resume);
            if (runtime.current === state) runtime.current = null;
        };
    }, [token]); // Profile refreshes do not restart an idle timer.

    useEffect(() => {
        const state = runtime.current;
        if (state?.token === token && session?.sessionPolicy && state.policy !== session.sessionPolicy) state.accept?.(session.sessionPolicy);
    }, [token, session?.sessionPolicy]);

    const staySignedIn = useCallback(() => runtime.current?.request?.(true), []);
    const keepWorking = useCallback(() => {
        if (runtime.current) { runtime.current.absoluteDismissed = true; setView((current) => ({ ...current, warning: false })); }
    }, []);
    return { ...view, warning: Boolean(token && view.token === token && view.warning), staySignedIn, keepWorking };
}
