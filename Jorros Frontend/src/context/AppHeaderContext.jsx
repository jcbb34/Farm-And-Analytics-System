"use client";

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import { usePathname } from "next/navigation";

import { alertService } from "../services/alertService.js";
import { useAuth } from "./AuthContext.jsx";

const AppHeaderContext = createContext(null);

const PROFILE_STORAGE_KEY = "joross-profile";
const ALERT_READ_STORAGE_KEY =
    "joross-header-alert-read-state-v1";
const NOTIFICATION_SETTINGS_STORAGE_KEY =
    "joross-notification-settings-v1";

const ALERT_REFRESH_INTERVAL = 20000;

let notificationAudioContext = null;

const defaultProfile = {
    fullName: "",
    username: "",
    email: "",
    role: "",
};

// Routes are kept here because the header uses them in several pages.
const moduleRoutes = {
    Dashboard: "/dashboard",
    Crop: "/crops",
    Livestock: "/livestock",
    Inventory: "/inventory",
    Alert: "/alerts",
    Weather: "/alerts",
    System: "/alerts",
    Report: "/reports",
    Settings: "/settings",
};

function readStoredProfile() {
    if (typeof window === "undefined") {
        return defaultProfile;
    }

    try {
        const storedValue = localStorage.getItem(
            PROFILE_STORAGE_KEY
        );

        if (!storedValue) {
            return defaultProfile;
        }

        return {
            ...defaultProfile,
            ...JSON.parse(storedValue),
        };
    } catch {
        return defaultProfile;
    }
}

function readStoredReadIds() {
    if (typeof window === "undefined") {
        return new Set();
    }

    try {
        const storedValue = localStorage.getItem(
            ALERT_READ_STORAGE_KEY
        );

        if (!storedValue) {
            return new Set();
        }

        const values = JSON.parse(storedValue);

        return new Set(
            Array.isArray(values) ? values : []
        );
    } catch {
        return new Set();
    }
}

function saveStoredReadIds(readIds) {
    if (typeof window === "undefined") {
        return;
    }

    try {
        localStorage.setItem(
            ALERT_READ_STORAGE_KEY,
            JSON.stringify([...readIds])
        );
    } catch {
        // The bell can still work during this session without storage.
    }
}

function readNotificationSettings() {
    const defaults = {
        cropAlerts: true,
        livestockAlerts: true,
        weatherAlerts: true,
        inventoryAlerts: true,
        systemAlerts: true,
        inAppNotifications: true,
        soundNotifications: true,
    };

    if (typeof window === "undefined") {
        return defaults;
    }

    try {
        const storedValue = localStorage.getItem(
            NOTIFICATION_SETTINGS_STORAGE_KEY
        );

        if (!storedValue) {
            return defaults;
        }

        return {
            ...defaults,
            ...JSON.parse(storedValue),
        };
    } catch {
        return defaults;
    }
}

function makeAlertNotificationId(alert) {
    if (!alert?.id || !alert?.lastTriggered) {
        return "";
    }

    return `alert-${alert.id}-${String(
        alert.lastTriggered
    )}`;
}

function getAlertIcon(alert) {
    const alertType = String(
        alert.alertType || ""
    ).toLowerCase();

    if (alertType.includes("vaccin")) {
        return "vaccines";
    }

    if (alertType.includes("health")) {
        return "health_and_safety";
    }

    if (alertType.includes("feed")) {
        return "restaurant";
    }

    if (alertType.includes("inventory")) {
        return "inventory_2";
    }

    if (alertType.includes("harvest")) {
        return "agriculture";
    }

    if (alertType.includes("pest")) {
        return "pest_control";
    }

    if (alertType.includes("temperature")) {
        return "device_thermostat";
    }

    if (alertType.includes("rain")) {
        return "rainy";
    }

    if (alertType.includes("wind")) {
        return "air";
    }

    if (alertType.includes("thunder")) {
        return "thunderstorm";
    }

    if (alertType.includes("backup")) {
        return "backup";
    }

    const categoryIcons = {
        Crop: "grass",
        Livestock: "pets",
        Weather: "partly_cloudy_day",
        System: "settings",
    };

    return (
        categoryIcons[alert.category] ||
        "notifications"
    );
}

function getAlertTone(priority) {
    const value = String(
        priority || ""
    ).toLowerCase();

    if (value === "high") {
        return "error";
    }

    if (value === "medium") {
        return "warning";
    }

    return "info";
}

function formatAlertTime(value) {
    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Recently";
    }

    const now = new Date();
    const differenceMs = now.getTime() - date.getTime();
    const differenceMinutes = Math.floor(
        differenceMs / 60000
    );

    if (differenceMinutes < 1) {
        return "Just now";
    }

    if (differenceMinutes < 60) {
        return `${differenceMinutes}m ago`;
    }

    const differenceHours = Math.floor(
        differenceMinutes / 60
    );

    if (differenceHours < 24) {
        return `${differenceHours}h ago`;
    }

    if (differenceHours < 48) {
        return "Yesterday";
    }

    return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
    });
}

function getConditionText(alert) {
    const condition = String(
        alert.condition || ""
    ).trim();
    const threshold = String(
        alert.threshold || ""
    ).trim();
    const unit = String(alert.unit || "").trim();

    if (!condition || !threshold) {
        return "";
    }

    return `${condition} ${threshold}${
        unit ? ` ${unit}` : ""
    }`;
}

function alertIsEnabledForBell(alert, settings) {
    if (!settings.inAppNotifications) {
        return false;
    }

    const category = String(
        alert.category || ""
    );
    const alertType = String(
        alert.alertType || ""
    ).toLowerCase();

    if (alertType.includes("inventory")) {
        return settings.inventoryAlerts !== false;
    }

    if (category === "Crop") {
        return settings.cropAlerts !== false;
    }

    if (category === "Livestock") {
        return settings.livestockAlerts !== false;
    }

    if (category === "Weather") {
        return settings.weatherAlerts !== false;
    }

    return settings.systemAlerts !== false;
}

function convertAlertToNotification(alert, readIds) {
    const notificationId =
        makeAlertNotificationId(alert);
    const conditionText =
        getConditionText(alert);

    const description = [
        alert.subject,
        conditionText,
    ]
        .filter(Boolean)
        .join(" • ");

    return {
        id: notificationId,
        module: alert.category || "System",
        title:
            alert.alertName ||
            alert.alertType ||
            "Farm Alert",
        description:
            description ||
            alert.description ||
            "A farm alert was triggered.",
        time: formatAlertTime(
            alert.lastTriggered
        ),
        icon: getAlertIcon(alert),
        tone: getAlertTone(alert.priority),
        route: "/alerts",
        entityId: alert.id,
        alertId: alert.id,
        priority: alert.priority,
        lastTriggered: alert.lastTriggered,
        unread: !readIds.has(notificationId),
    };
}

// The sound is generated in the browser, so no MP3 asset is needed.
function playNotificationSound() {
    if (typeof window === "undefined") {
        return;
    }

    const settings = readNotificationSettings();

    if (settings.soundNotifications === false) {
        return;
    }

    try {
        const AudioContextClass =
            window.AudioContext ||
            window.webkitAudioContext;

        if (!AudioContextClass) {
            return;
        }

        if (!notificationAudioContext) {
            notificationAudioContext =
                new AudioContextClass();
        }

        const context = notificationAudioContext;

        const playChime = () => {
            const now = context.currentTime;
            const masterGain =
                context.createGain();

            masterGain.gain.setValueAtTime(
                0.0001,
                now
            );
            masterGain.gain.exponentialRampToValueAtTime(
                0.12,
                now + 0.015
            );
            masterGain.gain.exponentialRampToValueAtTime(
                0.0001,
                now + 0.34
            );
            masterGain.connect(
                context.destination
            );

            [740, 980].forEach(
                (frequency, index) => {
                    const oscillator =
                        context.createOscillator();
                    const toneGain =
                        context.createGain();
                    const startTime =
                        now + index * 0.09;

                    oscillator.type = "sine";
                    oscillator.frequency.setValueAtTime(
                        frequency,
                        startTime
                    );

                    toneGain.gain.setValueAtTime(
                        index === 0 ? 0.65 : 0.5,
                        startTime
                    );
                    toneGain.gain.exponentialRampToValueAtTime(
                        0.0001,
                        startTime + 0.18
                    );

                    oscillator.connect(toneGain);
                    toneGain.connect(masterGain);
                    oscillator.start(startTime);
                    oscillator.stop(
                        startTime + 0.2
                    );
                }
            );
        };

        if (context.state === "suspended") {
            context
                .resume()
                .then(playChime)
                .catch(() => {});
        } else {
            playChime();
        }
    } catch {
        // Browsers may block sound until the user interacts with the page.
    }
}

export function AppHeaderProvider({ children }) {
    const pathname = usePathname();
    const {
        user,
        isAuthenticated,
        isLoading: isAuthLoading,
        hasPermission,
    } = useAuth();
    const isPublicAuthRoute =
        pathname === "/" ||
        pathname === "/login" ||
        pathname === "/verify-2fa";

    const [profile, setProfile] = useState(
        readStoredProfile
    );
    const [notifications, setNotifications] =
        useState([]);

    useEffect(() => {
        if (user) {
            setProfile(user);
        } else if (!isAuthenticated && !isAuthLoading) {
            setProfile(defaultProfile);
        }
    }, [user, isAuthenticated, isAuthLoading]);

    const readIdsRef = useRef(
        readStoredReadIds()
    );
    const knownTriggerIdsRef = useRef(
        new Set()
    );
    const dismissedIdsRef = useRef(
        new Set()
    );
    const firstAlertLoadRef = useRef(true);
    const alertLoadRunningRef = useRef(false);

    // Pull triggered alerts from the same API used by the Alerts page.
    const refreshAlertNotifications = useCallback(
        async ({ allowSound = true } = {}) => {
            if (
                isPublicAuthRoute ||
                isAuthLoading ||
                !isAuthenticated ||
                !hasPermission("alerts:view")
            ) {
                setNotifications([]);
                knownTriggerIdsRef.current = new Set();
                firstAlertLoadRef.current = true;
                return;
            }

            if (alertLoadRunningRef.current) {
                return;
            }

            alertLoadRunningRef.current = true;

            try {
                const alerts =
                    await alertService.getNotificationPreview();
                const settings =
                    readNotificationSettings();

                const triggeredAlerts = alerts
                    .filter(
                        (alert) =>
                            Boolean(
                                alert.lastTriggered
                            )
                    )
                    .sort(
                        (a, b) =>
                            new Date(
                                b.lastTriggered
                            ).getTime() -
                            new Date(
                                a.lastTriggered
                            ).getTime()
                    );

                // Track every trigger, even when its category is hidden in Settings.
                const allTriggerIds = new Set(
                    triggeredAlerts
                        .map(
                            makeAlertNotificationId
                        )
                        .filter(Boolean)
                );

                if (firstAlertLoadRef.current) {
                    knownTriggerIdsRef.current =
                        allTriggerIds;
                    firstAlertLoadRef.current =
                        false;
                } else {
                    const newVisibleTrigger =
                        triggeredAlerts.some(
                            (alert) => {
                                const id =
                                    makeAlertNotificationId(
                                        alert
                                    );

                                return (
                                    id &&
                                    !knownTriggerIdsRef.current.has(
                                        id
                                    ) &&
                                    alertIsEnabledForBell(
                                        alert,
                                        settings
                                    )
                                );
                            }
                        );

                    if (
                        allowSound &&
                        newVisibleTrigger
                    ) {
                        playNotificationSound();
                    }

                    knownTriggerIdsRef.current =
                        allTriggerIds;
                }

                const nextNotifications =
                    triggeredAlerts
                        .filter((alert) =>
                            alertIsEnabledForBell(
                                alert,
                                settings
                            )
                        )
                        .map((alert) =>
                            convertAlertToNotification(
                                alert,
                                readIdsRef.current
                            )
                        )
                        .filter(
                            (notification) =>
                                !dismissedIdsRef.current.has(
                                    notification.id
                                )
                        )
                        .slice(0, 30);

                setNotifications(
                    nextNotifications
                );
            } catch (error) {
                if (error?.status === 401) {
                    setNotifications([]);
                    knownTriggerIdsRef.current = new Set();
                    firstAlertLoadRef.current = true;
                    return;
                }

                console.error(
                    "Failed to load alert notifications:",
                    error
                );
            } finally {
                alertLoadRunningRef.current = false;
            }
        },
        [
            isAuthenticated,
            isAuthLoading,
            isPublicAuthRoute,
            hasPermission,
        ]
    );

    useEffect(() => {
        const refreshProfile = (event) => {
            if (
                event?.detail &&
                typeof event.detail === "object"
            ) {
                setProfile((currentProfile) => ({
                    ...currentProfile,
                    ...event.detail,
                }));
                return;
            }

            setProfile(readStoredProfile());
        };

        const refreshAlerts = () => {
            refreshAlertNotifications({
                allowSound: true,
            });
        };

        const handleStorage = (event) => {
            if (event.key === PROFILE_STORAGE_KEY) {
                refreshProfile();
            }

            if (
                event.key ===
                ALERT_READ_STORAGE_KEY
            ) {
                readIdsRef.current =
                    readStoredReadIds();

                setNotifications(
                    (currentItems) =>
                        currentItems.map(
                            (item) => ({
                                ...item,
                                unread:
                                    !readIdsRef.current.has(
                                        item.id
                                    ),
                            })
                        )
                );
            }

            if (
                event.key ===
                NOTIFICATION_SETTINGS_STORAGE_KEY
            ) {
                refreshAlertNotifications({
                    allowSound: false,
                });
            }
        };

        const handleVisibilityChange = () => {
            if (
                document.visibilityState ===
                "visible"
            ) {
                refreshAlertNotifications({
                    allowSound: true,
                });
            }
        };

        // Initial load does not play sound for old alert records.
        refreshAlertNotifications({
            allowSound: false,
        });

        let realtimeConnected = false;
        const onRealtimeConnection = (event) => { realtimeConnected = Boolean(event.detail?.connected); };
        window.addEventListener("joross:realtime-connection", onRealtimeConnection);
        const refreshTimer = window.setInterval(
            () => { if (!realtimeConnected) refreshAlerts(); },
            ALERT_REFRESH_INTERVAL
        );

        window.addEventListener(
            "joross-profile-updated",
            refreshProfile
        );
        window.addEventListener(
            "joross:alerts-updated",
            refreshAlerts
        );
        window.addEventListener(
            "storage",
            handleStorage
        );
        document.addEventListener(
            "visibilitychange",
            handleVisibilityChange
        );

        return () => {
            window.clearInterval(refreshTimer);
            window.removeEventListener("joross:realtime-connection", onRealtimeConnection);
            window.removeEventListener(
                "joross-profile-updated",
                refreshProfile
            );
            window.removeEventListener(
                "joross:alerts-updated",
                refreshAlerts
            );
            window.removeEventListener(
                "storage",
                handleStorage
            );
            document.removeEventListener(
                "visibilitychange",
                handleVisibilityChange
            );
        };
    }, [refreshAlertNotifications]);

    const markAsRead = useCallback(
        (notificationId) => {
            readIdsRef.current.add(
                notificationId
            );
            saveStoredReadIds(
                readIdsRef.current
            );

            setNotifications((currentItems) =>
                currentItems.map((item) =>
                    item.id === notificationId
                        ? {
                              ...item,
                              unread: false,
                          }
                        : item
                )
            );
        },
        []
    );

    const markAllAsRead = useCallback(() => {
        setNotifications((currentItems) => {
            currentItems.forEach((item) => {
                readIdsRef.current.add(item.id);
            });

            saveStoredReadIds(
                readIdsRef.current
            );

            return currentItems.map((item) => ({
                ...item,
                unread: false,
            }));
        });
    }, []);

    // Close removes it for this session without deleting the real farm alert.
    const removeNotification = useCallback(
        (notificationId) => {
            readIdsRef.current.add(
                notificationId
            );
            dismissedIdsRef.current.add(
                notificationId
            );
            saveStoredReadIds(
                readIdsRef.current
            );

            setNotifications((currentItems) =>
                currentItems.filter(
                    (item) =>
                        item.id !== notificationId
                )
            );
        },
        []
    );

    // Kept for older components, but real bell data comes from alertService.
    const addNotification = useCallback(
        () => {
            refreshAlertNotifications({
                allowSound: true,
            });
            return null;
        },
        [refreshAlertNotifications]
    );

    const resetNotifications = useCallback(() => {
        readIdsRef.current = new Set();
        dismissedIdsRef.current = new Set();
        saveStoredReadIds(
            readIdsRef.current
        );

        refreshAlertNotifications({
            allowSound: false,
        });
    }, [refreshAlertNotifications]);

    const unreadCount = useMemo(
        () =>
            notifications.filter(
                (item) => item.unread
            ).length,
        [notifications]
    );

    const contextValue = useMemo(
        () => ({
            profile,
            notifications,
            unreadCount,
            moduleRoutes,
            markAsRead,
            markAllAsRead,
            removeNotification,
            addNotification,
            resetNotifications,
            refreshNotifications:
                refreshAlertNotifications,
        }),
        [
            profile,
            notifications,
            unreadCount,
            markAsRead,
            markAllAsRead,
            removeNotification,
            addNotification,
            resetNotifications,
            refreshAlertNotifications,
        ]
    );

    return (
        <AppHeaderContext.Provider
            value={contextValue}
        >
            {children}
        </AppHeaderContext.Provider>
    );
}

export function useAppHeader() {
    const context = useContext(
        AppHeaderContext
    );

    if (!context) {
        throw new Error(
            "useAppHeader must be used inside AppHeaderProvider."
        );
    }

    return context;
}
