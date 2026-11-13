/** Only authenticated, relative evidence endpoints may be requested. */
export function evidencePaths(value) {
    const path = String(value || "");
    const asset = path.match(/^\/workforce\/evidence-assets\/([A-Za-z0-9_-]+)(?:\/thumbnail)?$/);
    if (asset) {
        const original = `/workforce/evidence-assets/${asset[1]}`;
        return { original, thumbnail: `${original}/thumbnail` };
    }
    const legacy = path.match(/^\/workforce\/evidence\/([^/?#\\]+)$/);
    if (legacy) {
        try {
            const filename = decodeURIComponent(legacy[1]);
            if (![".", ".."].includes(filename) && !/[\/\\\u0000-\u001f]/.test(filename)) {
                return { original: path, thumbnail: null };
            }
        } catch { /* Malformed paths do not reach the network. */ }
    }
    return null;
}
