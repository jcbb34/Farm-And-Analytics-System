// Shared auth-only mock for other module tests. Business/API assertions remain
// in their original fixtures. Session behavior has its own independent suite.
const sessions = new WeakMap();
export async function serveSessionPolicy(route, page) {
    const path = new URL(route.request().url()).pathname;
    if (!['/api/v1/auth/session', '/api/v1/auth/session/activity'].includes(path)) return false;
    let snapshot;
    try { snapshot = await page.evaluate(() => ({ now: Date.now(), session: JSON.parse(sessionStorage.getItem('joross-auth-session-v1') || 'null') })); }
    catch { try { await route.abort('aborted'); } catch {} return true; }
    const { now, session } = snapshot;
    const token = route.request().headers().authorization;
    if (!session?.accessToken || token !== `Bearer ${session.accessToken}`) {
        await route.fulfill({ status: 401, json: { detail: 'Session unavailable' } }); return true;
    }
    let state = sessions.get(page);
    if (!state || state.token !== token) {
        const absolute = Math.min(Number(session.expiresAt) || now + 28800000, now + 28800000);
        state = { token, id: `${session.user?.id || 'test'}:module-fixture`, absolute, idle: Math.min(now + 900000, absolute) };
        sessions.set(page, state);
    }
    if (now >= state.idle || now >= state.absolute) {
        await route.fulfill({ status: 401, json: { detail: 'Session expired' } }); return true;
    }
    if (path.endsWith('/activity')) state.idle = Math.min(now + 900000, state.absolute);
    await route.fulfill({ json: { session_id: state.id, server_time: now / 1000,
        idle_expires_at: state.idle / 1000, absolute_expires_at: state.absolute / 1000,
        idle_timeout_seconds: 900, warning_seconds: 60 } });
    return true;
}
