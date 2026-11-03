import assert from "node:assert/strict";
import test from "node:test";
import { backupService } from "../src/services/backupService.js";
import { invalidateReadCache } from "../src/services/httpClient.js";

const original = Object.fromEntries(["window", "sessionStorage", "localStorage", "fetch"].map((key) => [key, globalThis[key]]));
test.beforeEach(() => {
    invalidateReadCache();
    globalThis.window = { location: { origin: "http://farm.local:3000" }, setTimeout, clearTimeout };
    globalThis.sessionStorage = globalThis.localStorage = { getItem: () => null };
});
test.after(() => Object.assign(globalThis, original));

test("backup history distinguishes complete recovery archives and existing JSON backups", async () => {
    globalThis.fetch = async () => Response.json([
        { id: 1, recovery_available: true, recovery_file_size_bytes: 234, file_size_bytes: 123 },
        { id: 2, filename: "legacy.json", file_size_bytes: 120 },
    ]);
    const [current, legacy] = await backupService.getBackups();
    assert.equal(current.recoveryAvailable, true);
    assert.equal(current.recoverySizeBytes, 234);
    assert.equal(current.fileSizeBytes, 123);
    assert.equal(legacy.recoveryAvailable, false);
    assert.equal(legacy.filename, "legacy.json");
});

test("recovery downloads preserve binary bytes and retain the JSON API", async () => {
    const requested = [], bytes = new Uint8Array([80, 75, 3, 4, 0, 255]);
    globalThis.fetch = async (url, options) => {
        requested.push({ url, options });
        return url.endsWith("/recovery-package")
            ? new Response(bytes, { headers: { "Content-Type": "application/zip" } })
            : Response.json({ format_version: "1.0", tables: {} });
    };
    const blob = await backupService.getRecoveryPackage(1);
    assert.ok(blob instanceof Blob);
    assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), bytes);
    assert.equal(new URL(requested[0].url).pathname, "/api/v1/backups/1/recovery-package");
    assert.equal((await backupService.getBackupContent(2)).format_version, "1.0");
    assert.equal(new URL(requested[1].url).pathname, "/api/v1/backups/2/content");
});

test("a failed recovery download surfaces the error instead of saving an error blob", async () => {
    globalThis.fetch = async () => Response.json({ detail: "The archive failed its integrity check." }, { status: 409 });
    await assert.rejects(backupService.getRecoveryPackage(1), { status: 409, message: "The archive failed its integrity check." });
});
