export const NOTIFICATION_PREFERENCES_KEY =
    "joross-notification-preferences-v1";

export const DEFAULT_NOTIFICATION_PREFERENCES = Object.freeze({
    cropAlerts: true,
    livestockAlerts: true,
    weatherAlerts: true,
    inventoryAlerts: true,
    systemAlerts: true,
    emailNotifications: true,
    inAppNotifications: true,
    soundNotifications: true,
    notificationFrequency: "Immediate",
});

export function readNotificationPreferences(fallback = {}) {
    const defaults = {
        ...DEFAULT_NOTIFICATION_PREFERENCES,
        ...fallback,
    };

    if (typeof window === "undefined") {
        return defaults;
    }

    try {
        const stored = localStorage.getItem(NOTIFICATION_PREFERENCES_KEY);
        if (!stored) return defaults;

        const parsed = JSON.parse(stored);
        return {
            ...defaults,
            ...(parsed && typeof parsed === "object" ? parsed : {}),
        };
    } catch {
        return defaults;
    }
}

export function saveNotificationPreferences(settings = {}) {
    const next = {
        ...DEFAULT_NOTIFICATION_PREFERENCES,
        ...settings,
    };

    if (typeof window === "undefined") {
        return next;
    }

    try {
        localStorage.setItem(
            NOTIFICATION_PREFERENCES_KEY,
            JSON.stringify(next)
        );

        window.dispatchEvent(
            new CustomEvent("joross:notification-preferences-updated", {
                detail: next,
            })
        );
    } catch {
        // Keep UI preferences usable even when browser storage is unavailable.
    }

    return next;
}
