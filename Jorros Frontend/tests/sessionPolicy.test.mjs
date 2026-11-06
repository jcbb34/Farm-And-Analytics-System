import assert from 'node:assert/strict';
import test from 'node:test';
import { IDLE_MS, MAX_SESSION_MS, initialSessionPolicy, serverSessionPolicy, sessionIdentity, publishSessionSignal, mergeSessionPolicy } from '../src/services/sessionPolicy.js';

test('initial deadlines preserve an existing session across reloads and cap absolute lifetime', () => {
    const now = 100000;
    const policy = initialSessionPolicy({ accessToken: 'synthetic-token', expiresAt: now + MAX_SESSION_MS * 2 }, now);
    assert.equal(policy.idleDeadline, now + IDLE_MS);
    assert.equal(policy.absoluteDeadline, now + MAX_SESSION_MS);
    assert.equal(initialSessionPolicy({ sessionPolicy: policy }, now + 300000), policy);
});
test('a server deadline is interpreted relative to server time rather than assuming matching clocks', () => {
    const policy = serverSessionPolicy({ session_id: '1:4', server_time: 1000, idle_expires_at: 1600, absolute_expires_at: 2000 }, 5000);
    assert.equal(policy.idleDeadline, 605000);
    assert.equal(policy.absoluteDeadline, 1005000);
    assert.equal(policy.sessionId, '1:4');
    assert.equal(serverSessionPolicy([]), null);
});
test('tab signals contain no access token or account profile', () => {
    const signals = [];
    const original = globalThis.localStorage;
    globalThis.localStorage = { setItem: (_key, value) => signals.push(JSON.parse(value)), removeItem() {} };
    try {
        const session = { accessToken: 'synthetic-token-secret', user: { id: 1, fullName: 'Synthetic User' } };
        publishSessionSignal('logout', sessionIdentity(session));
        assert.equal(signals.length, 1);
        assert.equal(JSON.stringify(signals).includes(session.accessToken), false);
        assert.equal(JSON.stringify(signals).includes('Synthetic User'), false);
    } finally { globalThis.localStorage = original; }
});


test('out-of-order status responses cannot shorten a renewed lease or extend the absolute limit', () => {
    const current = { sessionId: '1:4', idleDeadline: 1500, absoluteDeadline: 2000 };
    const stale = { sessionId: '1:4', idleDeadline: 1000, absoluteDeadline: 2100 };
    assert.deepEqual(mergeSessionPolicy(current, stale), current);
    assert.equal(mergeSessionPolicy(current, { ...stale, idleDeadline: 1900 }).idleDeadline, 1900);
    assert.equal(mergeSessionPolicy(current, { ...stale, idleDeadline: 2500 }).idleDeadline, 2000);
});
