/** Parse event-stream frames split at arbitrary network boundaries. */
export function parseEventFrames(buffer, onFrame) {
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const values = {};
        for (const line of frame.split("\n")) {
            const colon = line.indexOf(":");
            if (colon < 0) continue;
            const key = line.slice(0, colon);
            if (["id", "event", "data"].includes(key)) values[key] = line.slice(colon + 1).trimStart();
        }
        if (values.event || values.data) onFrame(values);
    }
    return buffer;
}
