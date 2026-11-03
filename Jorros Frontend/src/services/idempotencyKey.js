export function createIdempotencyKey(prefix = "request") {
    const randomPart = globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}:${randomPart}`;
}

export function stableIdempotencyKey(requestRef, payload, prefix) {
    const fingerprint = JSON.stringify(payload);
    if (
        !requestRef.current?.key
        || requestRef.current.fingerprint !== fingerprint
    ) {
        requestRef.current = {
            fingerprint,
            key: createIdempotencyKey(prefix),
        };
    }
    return requestRef.current.key;
}

export function clearStableIdempotencyKey(requestRef) {
    requestRef.current = null;
}
