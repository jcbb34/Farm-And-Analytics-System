export const SHARED_DEVICE_STORAGE_KEY = "joross-shared-device-enabled-v1";
export const SHARED_DEVICE_LANGUAGE_KEY = "joross-shared-device-language-v1";
export const SHARED_DEVICE_INACTIVITY_MS = 10 * 60 * 1000;

export const SHARED_DEVICE_TRANSLATIONS = Object.freeze({
    en: Object.freeze({
        modeTitle: "Shared Device",
        signInTitle: "Employee Sign In",
        signInHelp: "Sign in before using this shared farm device. Your session will lock automatically after inactivity.",
        username: "User Account",
        password: "Password",
        signIn: "Sign In",
        lockedMessage: "The shared device was locked after inactivity. Sign in again to continue.",
        todayTasks: "Today's Tasks",
        shortHelp: "Open one task, read the instructions, start the work, then submit what you completed.",
        online: "Online",
        offline: "Offline",
        english: "English",
        filipino: "Filipino",
        lockDevice: "Lock / Sign Out",
        locking: "Locking shared device…",
        exitMode: "Exit Shared Mode",
        refresh: "Refresh",
        openTask: "Open Task",
        start: "Start",
        starting: "Starting…",
        instructions: "Instructions",
        correctionNeeded: "Correction Needed",
        managerFeedback: "Manager feedback",
        inProgress: "In Progress",
        coverageTask: "Coverage task",
        loading: "Loading…",
        unit: "Unit",
        listen: "Listen",
        stopListening: "Stop",
        listenUnavailable: "Audio unavailable",
        actualQuantity: "Actual Quantity",
        quantityHelp: "Enter the amount actually used or completed.",
        evidencePhoto: "Evidence Photo",
        takePhoto: "Take / Upload Photo",
        replacePhoto: "Replace Photo",
        selectedPhoto: "Selected photo",
        notes: "Work Notes",
        problem: "Report a Problem",
        optional: "Optional",
        submit: "Submit Work",
        submitting: "Submitting…",
        back: "Back to Today's Tasks",
        pendingSync: "Pending Sync",
        syncing: "Syncing…",
        retrySync: "Retry Sync",
        discardDraft: "Discard Draft",
        conflict: "Sync Conflict",
        noTasks: "No open tasks are due today.",
        attention: "Needs attention",
        dueToday: "Due today",
        overdue: "Overdue",
        successTitle: "Work Submitted",
        successMessage: "Your work was recorded successfully.",
        queuedTitle: "Saved for Sync",
        queuedMessage: "This submission is stored on this device and will sync when the connection returns.",
        offlineHelp: "You are offline. Started tasks can be saved as Pending Sync and sent when the connection returns.",
        startOnline: "Connect to the farm network to start this task.",
        startFirst: "Start this task before submitting your work.",
        upcomingLocked: "This task is scheduled for a future date. You can start and submit it on its scheduled day.",
        photoRequired: "Take or choose a photo before submitting this task.",
        resourceNeeded: "A manager must link the required inventory resource before this task can be submitted.",
        pendingCount: "submission waiting to sync",
        pendingCountPlural: "submissions waiting to sync",
    }),
    fil: Object.freeze({
        modeTitle: "Shared Device",
        signInTitle: "Pag-sign In ng Empleyado",
        signInHelp: "Mag-sign in bago gamitin ang shared farm device. Awtomatikong magla-lock ang session kapag walang aktibidad.",
        username: "User Account",
        password: "Password",
        signIn: "Mag-sign In",
        lockedMessage: "Na-lock ang shared device dahil walang aktibidad. Mag-sign in muli para magpatuloy.",
        todayTasks: "Mga Gawain Ngayon",
        shortHelp: "Buksan ang isang gawain, basahin ang tagubilin, simulan ang trabaho, at ipasa ang natapos.",
        online: "Online",
        offline: "Offline",
        english: "English",
        filipino: "Filipino",
        lockDevice: "I-lock / Mag-sign out",
        locking: "Nila-lock ang shared device…",
        exitMode: "Lumabas sa Shared Mode",
        refresh: "I-refresh",
        openTask: "Buksan ang Gawain",
        start: "Simulan",
        starting: "Sinisimulan…",
        instructions: "Mga Tagubilin",
        correctionNeeded: "Kailangang Itama",
        managerFeedback: "Puna ng manager",
        inProgress: "Ginagawa",
        coverageTask: "Coverage na gawain",
        loading: "Naglo-load…",
        unit: "Yunit",
        listen: "Pakinggan",
        stopListening: "Itigil",
        listenUnavailable: "Walang audio",
        actualQuantity: "Aktuwal na Dami",
        quantityHelp: "Ilagay ang aktuwal na dami na nagamit o natapos.",
        evidencePhoto: "Larawan ng Ebidensya",
        takePhoto: "Kumuha / Mag-upload ng Larawan",
        replacePhoto: "Palitan ang Larawan",
        selectedPhoto: "Napiling larawan",
        notes: "Tala sa Trabaho",
        problem: "Mag-ulat ng Problema",
        optional: "Opsyonal",
        submit: "Ipasa ang Gawain",
        submitting: "Ipinapasa…",
        back: "Bumalik sa Mga Gawain Ngayon",
        pendingSync: "Naghihintay ng Sync",
        syncing: "Nagsi-sync…",
        retrySync: "Subukan Muli ang Sync",
        discardDraft: "Burahin ang Draft",
        conflict: "Problema sa Sync",
        noTasks: "Walang bukas na gawain na nakatakda ngayon.",
        attention: "Kailangang asikasuhin",
        dueToday: "Nakatakda ngayon",
        overdue: "Lampas na sa takdang oras",
        successTitle: "Naipasa ang Trabaho",
        successMessage: "Matagumpay na naitala ang iyong trabaho.",
        queuedTitle: "Naka-save para sa Sync",
        queuedMessage: "Naka-save ang submission sa device na ito at ipapadala kapag bumalik ang koneksyon.",
        offlineHelp: "Offline ka. Ang nasimulang gawain ay puwedeng i-save bilang Pending Sync at ipadala kapag bumalik ang koneksyon.",
        startOnline: "Kumonekta sa farm network para masimulan ang gawain.",
        startFirst: "Simulan muna ang gawain bago ipasa ang iyong trabaho.",
        upcomingLocked: "Naka-iskedyul ang gawaing ito sa susunod na araw. Maaari mo itong simulan at isumite sa nakatakdang araw.",
        photoRequired: "Kumuha o pumili ng larawan bago ipasa ang gawaing ito.",
        resourceNeeded: "Kailangang i-link muna ng manager ang tamang inventory resource bago maipasa ang gawaing ito.",
        pendingCount: "submission na naghihintay ng sync",
        pendingCountPlural: "mga submission na naghihintay ng sync",
    }),
});

export function normalizeSharedLanguage(value) {
    return String(value || "").trim().toLowerCase() === "fil" ? "fil" : "en";
}

export function isSharedModeRequested(search = "") {
    return new URLSearchParams(String(search || "")).get("shared") === "1";
}

export function searchWithSharedMode(search = "", enabled = true) {
    const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
    if (enabled) {
        params.set("shared", "1");
        params.set("tab", "tasks");
    } else {
        params.delete("shared");
    }
    const next = params.toString();
    return next ? `?${next}` : "";
}

export function sharedDeviceShouldLock(lastActivityAt, now = Date.now(), timeoutMs = SHARED_DEVICE_INACTIVITY_MS) {
    const last = Number(lastActivityAt || 0);
    return last > 0 && Number(now) - last >= Number(timeoutMs);
}

const OPEN_STATUSES = new Set(["Pending", "In Progress", "Returned"]);

export function sharedDeviceTasksForToday(tasks, todayKey) {
    return (tasks || [])
        .filter((task) => {
            if (!OPEN_STATUSES.has(task?.status) || task?.is_archived) return false;
            if (task?.status === "Returned") return true;
            return String(task?.activity_date || "") <= String(todayKey || "");
        })
        .sort((left, right) => {
            const rank = (task) => {
                if (task?.status === "Returned") return 0;
                if (String(task?.activity_date || "") < String(todayKey || "")) return 1;
                if (task?.status === "In Progress") return 2;
                return 3;
            };
            return rank(left) - rank(right)
                || String(left?.start_time || "").localeCompare(String(right?.start_time || ""))
                || Number(left?.id || 0) - Number(right?.id || 0);
        });
}
