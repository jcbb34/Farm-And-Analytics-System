// Deadlines are a UI aid. The API independently enforces every session limit.
export const IDLE_MS = 15 * 60 * 1000;
export const MAX_SESSION_MS = 8 * 60 * 60 * 1000;
export const WARNING_MS = 60 * 1000;
export const SESSION_SIGNAL_KEY = 'joross-session-signal-v1';

export function sessionIdentity(session) {
    if (session?.sessionPolicy?.sessionId) return session.sessionPolicy.sessionId;
    // A notification fingerprint, never a credential, is safe to send between tabs.
    let hash = 2166136261;
    for (const char of String(session?.accessToken || '')) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
    return session?.accessToken ? `${session.user?.id || ''}:${hash >>> 0}` : '';
}

export function initialSessionPolicy(session, now = Date.now()) {
    if (session?.sessionPolicy && Number.isFinite(session.sessionPolicy.idleDeadline)
        && Number.isFinite(session.sessionPolicy.absoluteDeadline)) return session.sessionPolicy;
    const expiry = Number(session?.expiresAt);
    const absoluteDeadline = Math.min(Number.isFinite(expiry) && expiry > 0 ? expiry : now + MAX_SESSION_MS, now + MAX_SESSION_MS);
    return { sessionId: sessionIdentity(session), idleDeadline: Math.min(now + IDLE_MS, absoluteDeadline), absoluteDeadline, warningMs: WARNING_MS };
}

export function serverSessionPolicy(response, receivedAt = Date.now()) {
    const fields = ['server_time', 'idle_expires_at', 'absolute_expires_at'];
    if (!response?.session_id || fields.some((key) => !Number.isFinite(response[key]))) return null;
    return {
        sessionId: String(response.session_id),
        idleDeadline: receivedAt + (Math.min(response.idle_expires_at, response.absolute_expires_at) - response.server_time) * 1000,
        absoluteDeadline: receivedAt + (response.absolute_expires_at - response.server_time) * 1000,
        warningMs: Math.min(WARNING_MS, Math.max(0, Number(response.warning_seconds) || 60) * 1000),
    };
}

export function publishSessionSignal(kind, sessionId, policy) {
    if (!sessionId) return;
    try { liveSessionChannel?.postMessage({ kind, sessionId, policy }); } catch {}
    try {
        // Only public deadlines/identity are transiently broadcast; tokens stay in sessionStorage.
        localStorage.setItem(SESSION_SIGNAL_KEY, JSON.stringify({ kind, sessionId, policy, nonce: `${Date.now()}:${Math.random()}` }));
        localStorage.removeItem(SESSION_SIGNAL_KEY);
    } catch { /* API revocation/expiry still protects tabs if storage events are unavailable. */ }
}

let liveSessionChannel = null;

// A new tab may join a still-open tab's login without persisting credentials.
// A fresh browser context has no live peer and must authenticate normally.
export function connectSessionTabs({ read, adopt, ready, signal }) {
    let channel;
    try { channel = new BroadcastChannel('joross-live-session-v1'); }
    catch { ready(); return () => {}; }
    liveSessionChannel = channel;
    const nonce = `${Date.now()}:${Math.random()}`;
    let waiting = !read();
    const finish = () => { waiting = false; ready(); };
    const timeout = waiting ? setTimeout(finish, 250) : null;
    channel.onmessage = ({ data }) => {
        if (data?.kind === 'request-session') {
            const current = read();
            const policy = current ? initialSessionPolicy(current) : null;
            if (current?.accessToken && Math.min(policy.idleDeadline, policy.absoluteDeadline) > Date.now()) {
                channel.postMessage({ kind: 'share-session', nonce: data.nonce, session: current });
            }
        } else if (data?.kind === 'share-session' && data.nonce === nonce && waiting) {
            const candidate = data.session;
            const policy = candidate?.accessToken && candidate?.user ? initialSessionPolicy(candidate) : null;
            if (policy && Math.min(policy.idleDeadline, policy.absoluteDeadline) > Date.now()) {
                try { adopt(candidate); } catch { /* Keep the sign-in page usable when storage is restricted. */ }
                clearTimeout(timeout); finish();
            }
        } else if (data?.kind === 'logout' || data?.kind === 'activity') signal(data);
    };
    if (waiting) channel.postMessage({ kind: 'request-session', nonce });
    else ready();
    return () => { clearTimeout(timeout); if (liveSessionChannel === channel) liveSessionChannel = null; channel.close(); };
}

export function mergeSessionPolicy(previous, next) {
    if (!previous || previous.sessionId !== next.sessionId) return next;
    const absoluteDeadline = Math.min(previous.absoluteDeadline, next.absoluteDeadline);
    return { ...next, absoluteDeadline, idleDeadline: Math.min(Math.max(previous.idleDeadline, next.idleDeadline), absoluteDeadline) };
}
