import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
    SHARED_DEVICE_INACTIVITY_MS,
    SHARED_DEVICE_TRANSLATIONS,
    isSharedModeRequested,
    searchWithSharedMode,
    sharedDeviceShouldLock,
    sharedDeviceTasksForToday,
} from "../src/views/MyTasks/sharedDeviceMode.js";
import {
    canAttemptSyncDraft,
    coalesceQueuedDraft,
    offlineDraftId,
    shouldAutoSyncDraft,
} from "../src/services/offlineTaskQueue.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");
const myTasksSource = read("src/views/MyTasks/MyTasks.jsx");
const sharedSource = read("src/components/SharedDevice/SharedDeviceTasks.jsx");
const sharedCss = read("src/components/SharedDevice/SharedDeviceTasks.css");
const loginSource = read("src/views/Login/Login.jsx");
const serviceWorker = read("public/sw.js");
const pwaBootstrap = read("src/components/PWA/PwaBootstrap.jsx");
const manifest = JSON.parse(read("public/manifest.webmanifest"));
const nextConfig = read("next.config.mjs");
const authContextSource = read("src/context/AuthContext.jsx");
const httpClientSource = read("src/services/httpClient.js");
const workforceServiceSource = read("src/services/workforceService.js");
const twoFactorSource = read("src/views/TwoFactorVerify/TwoFactorVerify.jsx");

test("shared-device mode is optional, task-only, and preserves the normal employee page", () => {
    assert.equal(isSharedModeRequested("?shared=1&tab=tasks"), true);
    assert.equal(isSharedModeRequested("?tab=tasks"), false);
    assert.equal(searchWithSharedMode("?tab=schedule", true), "?tab=tasks&shared=1");
    assert.equal(searchWithSharedMode("?tab=tasks&shared=1", false), "?tab=tasks");
    assert.match(myTasksSource, /Shared Device Mode/);
    assert.match(myTasksSource, /if \(sharedDeviceMode\) \{[\s\S]*?return <SharedDeviceTasks/);
    assert.ok(myTasksSource.indexOf("return <SharedDeviceTasks") < myTasksSource.indexOf("<Sidebar/>"));
    assert.doesNotMatch(sharedSource, /My Schedule|Leave Requests|Sidebar/);
});

test("shared-device task list shows current/overdue active work but not future or completed history", () => {
    const today = "2026-09-12";
    const rows = sharedDeviceTasksForToday([
        { id: 1, status: "Pending", activity_date: today, start_time: "08:00" },
        { id: 2, status: "In Progress", activity_date: "2026-09-11", start_time: "09:00" },
        { id: 3, status: "Returned", activity_date: "2026-09-10", start_time: "07:00" },
        { id: 4, status: "Pending", activity_date: "2026-09-13", start_time: "06:00" },
        { id: 5, status: "Completed", activity_date: today, start_time: "10:00" },
    ], today);
    assert.deepEqual(rows.map((row) => row.id), [3, 2, 1]);
    assert.doesNotMatch(sharedSource, /original_employee_name|covering_employee_name/);
    assert.equal(SHARED_DEVICE_TRANSLATIONS.en.coverageTask, "Coverage task");
    assert.match(sharedSource, /t\.coverageTask/);
    assert.match(workforceServiceSource, /shared_device\s*=\s*true/);
    assert.match(myTasksSource, /sharedDevice:\s*sharedDeviceMode/);
    assert.match(sharedSource, /activity_date[\s\S]*?>[\s\S]*?todayKey[\s\S]*?upcomingLocked/);
    assert.ok(String(SHARED_DEVICE_TRANSLATIONS.en.upcomingLocked || "").trim());
    assert.ok(String(SHARED_DEVICE_TRANSLATIONS.fil.upcomingLocked || "").trim());
});

test("essential employee actions have English and Filipino labels", () => {
    for (const language of ["en", "fil"]) {
        const labels = SHARED_DEVICE_TRANSLATIONS[language];
        for (const key of ["signInTitle", "todayTasks", "openTask", "start", "instructions", "listen", "actualQuantity", "evidencePhoto", "submit", "successTitle", "lockDevice"]) {
            assert.ok(String(labels[key] || "").trim(), `${language}.${key} must be translated`);
        }
    }
    assert.match(loginSource, /SHARED_DEVICE_TRANSLATIONS/);
    assert.match(sharedSource, /speechSynthesis/);
    assert.match(sharedSource, /capture="environment"/);
});

test("shared-device inactivity policy locks after ten minutes and the UI logs out on lock", () => {
    assert.equal(SHARED_DEVICE_INACTIVITY_MS, 10 * 60 * 1000);
    assert.equal(sharedDeviceShouldLock(1_000, 1_000 + SHARED_DEVICE_INACTIVITY_MS - 1), false);
    assert.equal(sharedDeviceShouldLock(1_000, 1_000 + SHARED_DEVICE_INACTIVITY_MS), true);
    assert.match(myTasksSource, /await logout\(\{ forceLocal: true \}\)/);
    assert.match(myTasksSource, /serverReleased \? "" : "&releasePending=1"/);
    assert.match(myTasksSource, /locked=1/);
    assert.match(sharedSource, /SHARED_DEVICE_INACTIVITY_MS/);
    assert.match(sharedSource, /pointerdown/);
    assert.match(sharedSource, /keydown/);
    assert.match(sharedSource, /shared-device-lock-screen/);
    assert.match(sharedSource, /if \(locking\)/);
});


test("all authentication uses temporary browser storage, including shared-device and two-factor login", () => {
    assert.match(loginSource, /sharedDevice:\s*sharedLogin/);
    assert.match(authContextSource, /sessionOnly:\s*true/);
    assert.match(authContextSource, /const targetStorageName = "sessionStorage"/);
    assert.match(authContextSource, /safeStorageRemove\(otherStorageName, storageKeys\.authSession\)/);
    assert.match(httpClientSource, /sessionStorage\.getItem\(storageKeys\.authSession\)/);
    assert.doesNotMatch(httpClientSource, /localStorage\.getItem\(storageKeys\.authSession\)/);
    assert.match(twoFactorSource, /sharedDevice:\s*Boolean\(challenge\.sharedDevice\)/);
});

test("offline queue deduplicates one pending submission per employee/task and keeps a stable idempotency record", () => {
    assert.equal(offlineDraftId(8, 42), "8:42");
    const existing = { id: "8:42", status: "pending", idempotencyKey: "same-key", taskId: 42 };
    const candidate = { id: "8:42", status: "pending", idempotencyKey: "new-key", taskId: 42 };
    const resolved = coalesceQueuedDraft(existing, candidate);
    assert.equal(resolved.duplicate, true);
    assert.equal(resolved.draft.idempotencyKey, "same-key");
    assert.equal(shouldAutoSyncDraft(existing, true), true);
    assert.equal(shouldAutoSyncDraft({ ...existing, status: "conflict" }, true), false);
    assert.equal(canAttemptSyncDraft({ ...existing, status: "conflict" }, true), true);
    assert.match(sharedSource, /queueOfflineTaskDraft/);
    assert.match(sharedSource, /workforceService\.submitTask\(working\.taskId, finalPayload, working\.idempotencyKey\)/);
});

test("reconnect synchronization retries pending drafts, exposes manual retry/conflicts, and cleans synced drafts", () => {
    assert.match(sharedSource, /window\.addEventListener\("online", updateStatus\)/);
    assert.match(sharedSource, /syncPendingDrafts\(\)/);
    assert.match(sharedSource, /removeOfflineTaskDraft\(working\.id\)/);
    assert.match(sharedSource, /Retry Sync|retrySync/);
    assert.match(sharedSource, /Sync Conflict|conflict/);
    assert.match(sharedSource, /Discard Draft|discardDraft/);
    assert.match(sharedSource, /evidenceBlob:\s*null/);
});

test("PWA caches only safe static assets and never caches API, evidence, authentication, or protected page HTML", () => {
    assert.equal(manifest.display, "standalone");
    assert.match(manifest.start_url, /my-tasks/);
    assert.ok(manifest.icons.some((icon) => icon.sizes === "192x192"));
    assert.ok(manifest.icons.some((icon) => icon.sizes === "512x512"));
    assert.match(serviceWorker, /\/_next\/static\//);
    assert.match(serviceWorker, /url\.pathname\.startsWith\("\/api\/"\)/);
    assert.match(serviceWorker, /url\.pathname\.includes\("\/evidence"\)/);
    assert.match(serviceWorker, /request\.mode === "navigate"[\s\S]*?fetch\(request\)\.catch/);
    assert.doesNotMatch(serviceWorker, /Authorization|joross-auth-session|localStorage/);
    assert.match(serviceWorker, /networkFirstSafeAsset/);
    assert.match(serviceWorker, /joross-safe-assets-v2/);
    assert.match(pwaBootstrap, /process\.env\.NODE_ENV !== "production"/);
    assert.match(pwaBootstrap, /getRegistrations\(\)/);
    assert.match(pwaBootstrap, /startsWith\(SAFE_CACHE_PREFIX\)/);
    assert.match(nextConfig, /camera=\(self\)/);
});

test("shared-device controls stay large and responsive for phones and tablets", () => {
    assert.match(sharedCss, /shared-primary-button[\s\S]*?min-height:\s*54px/);
    assert.match(sharedCss, /@media \(max-width: 640px\)[\s\S]*?min-height:\s*58px/);
    assert.match(sharedCss, /grid-template-columns:\s*1fr/);
    assert.match(sharedCss, /max-width:\s*100vw/);
    assert.match(sharedCss, /overflow-x:\s*hidden/);
    assert.match(sharedSource, /material-symbols-outlined/);
});


test("mobile WLAN auth bootstrap cannot remain permanently stuck when browser storage is restricted", () => {
    assert.match(authContextSource, /safeStorageGet/);
    assert.match(authContextSource, /finally \{[\s\S]*?setIsLoading\(false\)/);
    const homeSource = read("src/app/page.jsx");
    assert.match(homeSource, /window\.location\.replace\(destination\)/);
    assert.match(nextConfig, /allowedDevOrigins:\s*getLanDevOrigins\(\)/);
});
