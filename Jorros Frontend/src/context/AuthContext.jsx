"use client";

import {
    createContext,
    useCallback,
    useContext,
    useEffect,
    useMemo,
    useState,
} from "react";

import { appConfig, storageKeys } from "../config/appConfig.js";
import { authService } from "../services/authService.js";
import { userService } from "../services/userService.js";
import { explicitUserHasPermission } from "../utils/accessControl.js";

const AuthContext = createContext(null);

export const ROLE_PERMISSIONS = Object.freeze({
    "System Administrator": ["*"],
    Administrator: ["*"],
    Admin: ["*"],
    Owner: ["*"],
    Manager: [
        "dashboard:view",
        "crops:view", "crops:create", "crops:update", "crops:archive", "crops:export",
        "livestock:view", "livestock:create", "livestock:update", "livestock:archive", "livestock:export",
        "production_sales:view", "production_sales:update",
        "inventory:view", "inventory:create", "inventory:update", "inventory:adjust", "inventory:archive", "inventory:export",
        "alerts:view", "alerts:create", "alerts:update", "alerts:test",
        "reports:view", "reports:create", "reports:update", "reports:export",
        "intelligence:view", "intelligence:update",
        "activities:view", "activities:create", "activities:update",
        "workforce:view", "workforce:manage", "workforce:review", "workforce:attendance",
        "imports:preview", "imports:commit", "weather:view", "settings:view", "settings:profile", "notifications:view",
    ],
    Employee: ["workforce:submit"],
    "Farm Staff": ["workforce:submit"],
    Viewer: [
        "dashboard:view", "crops:view", "crops:export", "livestock:view", "livestock:export",
        "production_sales:view", "inventory:view", "inventory:export", "alerts:view", "reports:view",
        "reports:export", "intelligence:view", "activities:view", "weather:view", "settings:view", "settings:profile", "notifications:view",
    ],
});

const DEFAULT_USER = Object.freeze({
    id: "user-admin-1",
    userCode: "USR-1001",
    fullName: "Admin",
    username: "admin",
    email: "admin@example.com",
    contactNumber: "09123456789",
    position: "Farm Administrator",
    role: "System Administrator",
    status: "Active",
});

function safelyParse(value, fallback = null) {
    try {
        return JSON.parse(value);
    } catch {
        return fallback;
    }
}

function isPrimaryMockAdministrator(user = {}) {
    if (!appConfig.useMockApi) {
        return false;
    }

    const id = String(user.id || "").trim().toLowerCase();
    const userCode = String(user.userCode || "")
        .trim()
        .toUpperCase();
    const username = String(user.username || "")
        .trim()
        .toLowerCase();

    return (
        id === "user-admin-1" ||
        userCode === "USR-1001" ||
        username === "admin"
    );
}

function protectPrimaryAdministrator(user = {}) {
    if (!isPrimaryMockAdministrator(user)) {
        return user;
    }

    return {
        ...user,
        id: user.id || DEFAULT_USER.id,
        userCode: user.userCode || DEFAULT_USER.userCode,
        username: user.username || DEFAULT_USER.username,
        role: "System Administrator",
        status: "Active",
    };
}

function normalizeUser(user) {
    // Real API mode must never invent identity/role data from a mock admin
    // profile or stale localStorage. The backend response is authoritative.
    if (!appConfig.useMockApi) {
        return {
            ...(user || {}),
            permissions: Array.isArray(user?.permissions)
                ? user.permissions
                : [],
        };
    }

    if (typeof window === "undefined") {
        return protectPrimaryAdministrator({
            ...DEFAULT_USER,
            ...(user || {}),
        });
    }

    const profile = safelyParse(
        safeStorageGet("localStorage", storageKeys.profile),
        {}
    );

    const normalizedUser = protectPrimaryAdministrator({
        ...DEFAULT_USER,
        ...profile,
        ...(user || {}),
    });

    if (
        isPrimaryMockAdministrator(normalizedUser) &&
        profile.role !== "System Administrator"
    ) {
        safeStorageSet(
            "localStorage",
            storageKeys.profile,
            JSON.stringify(normalizedUser)
        );
    }

    return normalizedUser;
}


function safeStorageGet(storageName, key) {
    if (typeof window === "undefined") return null;
    try {
        return window[storageName]?.getItem(key) ?? null;
    } catch {
        return null;
    }
}

function safeStorageSet(storageName, key, value) {
    if (typeof window === "undefined") return false;
    try {
        window[storageName]?.setItem(key, value);
        return true;
    } catch {
        return false;
    }
}

function safeStorageRemove(storageName, key) {
    if (typeof window === "undefined") return;
    try {
        window[storageName]?.removeItem(key);
    } catch {
        // Shared/mobile browsers may restrict storage; auth must still recover.
    }
}

function isTruthyStorageValue(value) {
    return value === "true" || value === "1";
}

function readStoredSession() {
    if (typeof window === "undefined") {
        return null;
    }

    // Shared-device authentication is intentionally session-scoped so a
    // kiosk browser does not keep an employee token after the tab/browser
    // session ends. Normal desktop sessions keep the existing localStorage
    // behavior for backwards compatibility.
    const sessionOnlyStored = safelyParse(
        safeStorageGet("sessionStorage", storageKeys.authSession),
        null
    );
    const persistentStored = safelyParse(
        safeStorageGet("localStorage", storageKeys.authSession),
        null
    );
    const storedSession = sessionOnlyStored || persistentStored;
    const storedInSession = Boolean(sessionOnlyStored);

    if (storedSession?.expiresAt) {
        const expiresAt = Number(storedSession.expiresAt);

        if (
            Number.isFinite(expiresAt) &&
            expiresAt <= Date.now()
        ) {
            const storageName = storedInSession ? "sessionStorage" : "localStorage";
            safeStorageRemove(storageName, storageKeys.authSession);
            safeStorageRemove(storageName, storageKeys.legacyAuthenticated);
            return null;
        }
    }

    if (storedSession?.user) {
        return {
            ...storedSession,
            user: normalizeUser(storedSession.user),
        };
    }

    if (!appConfig.useMockApi) {
        return null;
    }
    const legacyAuthenticated = isTruthyStorageValue(
        safeStorageGet("localStorage", storageKeys.legacyAuthenticated)
    );

    if (!legacyAuthenticated) {
        return null;
    }

    return {
        accessToken: "legacy-frontend-session",
        refreshToken: "",
        tokenType: "bearer",
        expiresAt: null,
        user: normalizeUser(),
        legacy: true,
    };
}

function saveSession(session, { sessionOnly = false } = {}) {
    if (typeof window === "undefined") {
        return session;
    }

    const normalizedSession = {
        ...session,
        sessionOnly: Boolean(sessionOnly),
        user: normalizeUser(session?.user),
    };
    const targetStorageName = sessionOnly ? "sessionStorage" : "localStorage";
    const otherStorageName = sessionOnly ? "localStorage" : "sessionStorage";

    // Never leave a previous employee/admin token behind in the alternate
    // storage location. This is especially important when a normal browser
    // session is converted into a shared farm device.
    safeStorageRemove(otherStorageName, storageKeys.authSession);
    safeStorageRemove(otherStorageName, storageKeys.profile);
    safeStorageRemove(otherStorageName, storageKeys.legacyAuthenticated);

    safeStorageSet(
        targetStorageName,
        storageKeys.authSession,
        JSON.stringify(normalizedSession)
    );
    safeStorageSet(
        targetStorageName,
        storageKeys.profile,
        JSON.stringify(normalizedSession.user)
    );

    if (appConfig.useMockApi) {
        safeStorageSet(targetStorageName, storageKeys.legacyAuthenticated, "true");
    } else {
        safeStorageRemove("localStorage", storageKeys.legacyAuthenticated);
        safeStorageRemove("sessionStorage", storageKeys.legacyAuthenticated);
    }

    window.dispatchEvent(
        new CustomEvent("joross:auth-changed", {
            detail: normalizedSession,
        })
    );

    window.dispatchEvent(
        new CustomEvent("joross-profile-updated", {
            detail: normalizedSession.user,
        })
    );

    return normalizedSession;
}

function clearSession() {
    if (typeof window === "undefined") {
        return;
    }

    safeStorageRemove("localStorage", storageKeys.authSession);
    safeStorageRemove("localStorage", storageKeys.legacyAuthenticated);
    safeStorageRemove("localStorage", storageKeys.profile);
    safeStorageRemove("sessionStorage", storageKeys.authSession);
    safeStorageRemove("sessionStorage", storageKeys.profile);
    safeStorageRemove("sessionStorage", storageKeys.legacyAuthenticated);

    window.dispatchEvent(
        new CustomEvent("joross:auth-changed", {
            detail: null,
        })
    );
}

export function isAdministratorRole(role) {
    const normalizedRole = String(role || "")
        .trim()
        .toLowerCase();

    return [
        "system administrator",
        "administrator",
        "admin",
        "owner",
    ].includes(normalizedRole);
}

export function AuthProvider({ children }) {
    const [session, setSession] = useState(null);
    const [isLoading, setIsLoading] = useState(true);
    const [authError, setAuthError] = useState(null);

    const syncSession = useCallback(() => {
        setSession(readStoredSession());
    }, []);

    useEffect(() => {
        // Never leave the application on the boot screen if a shared/mobile
        // browser blocks Web Storage or contains a malformed session.
        try {
            syncSession();
        } catch {
            setSession(null);
        } finally {
            setIsLoading(false);
        }

        const handleStorage = (event) => {
            if (
                [
                    storageKeys.authSession,
                    storageKeys.legacyAuthenticated,
                    storageKeys.profile,
                ].includes(event.key)
            ) {
                syncSession();
            }
        };

        const handleAuthChanged = (event) => {
            if (event.detail) {
                setSession({
                    ...event.detail,
                    user: normalizeUser(event.detail.user),
                });
            } else {
                setSession(null);
            }
        };

        window.addEventListener("storage", handleStorage);
        window.addEventListener(
            "joross:auth-changed",
            handleAuthChanged
        );
        window.addEventListener(
            "joross-profile-updated",
            syncSession
        );

        // Only mock mode needs the legacy polling bridge. Real API sessions
        // update through storage/custom events and backend /auth/me calls.
        const legacySyncTimer = appConfig.useMockApi
            ? window.setInterval(() => {
                  const stored = readStoredSession();
                  setSession(stored);
              }, 400)
            : null;

        return () => {
            window.removeEventListener(
                "storage",
                handleStorage
            );
            window.removeEventListener(
                "joross:auth-changed",
                handleAuthChanged
            );
            window.removeEventListener(
                "joross-profile-updated",
                syncSession
            );
            if (legacySyncTimer !== null) {
                window.clearInterval(legacySyncTimer);
            }
        };
    }, [syncSession]);

    const login = useCallback(async (credentials) => {
        setAuthError(null);
        setIsLoading(true);

        try {
            const result = await authService.login(
                credentials
            );

            if (result?.requiresTwoFactor) {
                return result;
            }

            const savedSession = saveSession(result, {
                sessionOnly: Boolean(credentials?.sharedDevice),
            });
            setSession(savedSession);
            return savedSession;
        } catch (error) {
            setAuthError(
                error?.message || "Sign in failed."
            );
            throw error;
        } finally {
            setIsLoading(false);
        }
    }, []);

    const verifyTwoFactorLogin = useCallback(
        async ({ challengeToken, otpCode, sharedDevice = false }) => {
            setAuthError(null);
            setIsLoading(true);

            try {
                const nextSession =
                    await authService.verifyTwoFactorLogin({
                        challengeToken,
                        otpCode,
                    });
                const savedSession = saveSession(nextSession, {
                    sessionOnly: Boolean(sharedDevice),
                });
                setSession(savedSession);
                return savedSession;
            } catch (error) {
                setAuthError(
                    error?.message ||
                        "Two-factor verification failed."
                );
                throw error;
            } finally {
                setIsLoading(false);
            }
        },
        []
    );


    const logout = useCallback(async ({ forceLocal = false } = {}) => {
        let serverReleased = true;
        try {
            await authService.logout();
        } catch (error) {
            // An already-expired token needs no additional server revocation.
            if (error?.status !== 401) {
                serverReleased = false;
                if (!forceLocal) {
                    throw new Error(
                        "The server could not confirm logout. Your account is still signed in here. Please retry when the connection returns."
                    );
                }
            }
        }
        safeStorageSet(
            "localStorage",
            storageKeys.lastLogout,
            new Date().toISOString()
        );
        clearSession();
        setSession(null);
        return { serverReleased };
    }, []);

    const refreshCurrentUser = useCallback(async () => {
        if (!session) {
            return null;
        }

        const currentUser = await authService.getCurrentUser();
        const updatedSession = saveSession(
            {
                ...session,
                user: currentUser,
            },
            { sessionOnly: Boolean(session?.sessionOnly) }
        );

        setSession(updatedSession);
        return updatedSession.user;
    }, [session]);

    const updateCurrentUser = useCallback(
        async (changes) => {
            const currentUser =
                session?.user || (appConfig.useMockApi ? DEFAULT_USER : {});

            let updatedUser;

            if (appConfig.useMockApi) {
                const requestedUser = {
                    ...currentUser,
                    ...changes,
                };

                updatedUser =
                    isPrimaryMockAdministrator(currentUser)
                        ? {
                              ...requestedUser,
                              role: "System Administrator",
                              status: "Active",
                          }
                        : requestedUser;
            } else {
                updatedUser = await userService.updateMyProfile(
                    changes
                );
            }

            const updatedSession = saveSession(
                {
                    ...(session || {}),
                    accessToken:
                        session?.accessToken ||
                        (appConfig.useMockApi ? "legacy-frontend-session" : ""),
                    user: {
                        ...currentUser,
                        ...updatedUser,
                    },
                },
                { sessionOnly: Boolean(session?.sessionOnly) }
            );

            setSession(updatedSession);
            return updatedSession.user;
        },
        [session]
    );

    const hasPermission = useCallback(
        (permission) => {
            if (!permission) return true;

            const currentUser = session?.user;
            const explicitPermissions = currentUser?.permissions;
            if (Array.isArray(explicitPermissions)) {
                return explicitUserHasPermission(currentUser, permission);
            }

            // Mock-mode fallback only. Real API sessions always carry the
            // backend-provided permission list.
            const rolePermissions = ROLE_PERMISSIONS[currentUser?.role] || [];
            return rolePermissions.includes("*") || rolePermissions.includes(permission);
        },
        [session]
    );

    const value = useMemo(
        () => ({
            session,
            user: session?.user || null,
            isAuthenticated: Boolean(session),
            isAdministrator: hasPermission("*"),
            isLoading,
            authError,
            login,
            verifyTwoFactorLogin,
            logout,
            syncSession,
            refreshCurrentUser,
            updateCurrentUser,
            hasPermission,
        }),
        [
            session,
            isLoading,
            authError,
            login,
            verifyTwoFactorLogin,
            logout,
            syncSession,
            refreshCurrentUser,
            updateCurrentUser,
            hasPermission,
        ]
    );

    return (
        <AuthContext.Provider value={value}>
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const context = useContext(AuthContext);

    if (!context) {
        throw new Error(
            "useAuth must be used inside AuthProvider."
        );
    }

    return context;
}
