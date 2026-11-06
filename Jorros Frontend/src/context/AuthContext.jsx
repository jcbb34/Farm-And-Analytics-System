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

import { appConfig, storageKeys } from "../config/appConfig.js";
import { authService } from "../services/authService.js";
import { userService } from "../services/userService.js";
import { explicitUserHasPermission } from "../utils/accessControl.js";

import useSessionPolicy from "../hooks/useSessionPolicy.js";
import SessionTimeoutWarning from "../components/Auth/SessionTimeoutWarning.jsx";
import { connectSessionTabs, initialSessionPolicy, SESSION_SIGNAL_KEY, sessionIdentity, publishSessionSignal } from "../services/sessionPolicy.js";

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

    // All accounts are temporary. Old persistent credentials are never resumed.
    safeStorageRemove("localStorage", storageKeys.authSession);
    safeStorageRemove("localStorage", storageKeys.legacyAuthenticated);
    const storedSession = safelyParse(safeStorageGet("sessionStorage", storageKeys.authSession), null);

    if (typeof storedSession?.accessToken !== "string" || !storedSession.accessToken.trim()
        || !storedSession.user || typeof storedSession.user !== "object" || Array.isArray(storedSession.user)) {
        safeStorageRemove("sessionStorage", storageKeys.authSession);
        return null;
    }

    if (storedSession?.expiresAt) {
        const expiresAt = Number(storedSession.expiresAt);

        if (
            Number.isFinite(expiresAt) &&
            expiresAt <= Date.now()
        ) {
            const storageName = "sessionStorage";
            safeStorageRemove(storageName, storageKeys.authSession);
            safeStorageRemove(storageName, storageKeys.legacyAuthenticated);
            return null;
        }
    }

    if (storedSession?.user) {
        return {
            ...storedSession,
            sessionOnly: true,
            user: normalizeUser(storedSession.user),
        };
    }

    return null;
}

function sessionWasNotReplaced(token) {
    const stored = safelyParse(safeStorageGet("sessionStorage", storageKeys.authSession), null);
    return !stored?.accessToken || stored.accessToken === token;
}

function persistSessionPolicy(policy, token) {
    const stored = safelyParse(safeStorageGet("sessionStorage", storageKeys.authSession), null);
    if (!token || stored?.accessToken !== token) return false;
    // Timing updates are not profile changes. Preserve identity and unsaved
    // forms instead of notifying every module when the status poll completes.
    safeStorageSet("sessionStorage", storageKeys.authSession, JSON.stringify({
        ...stored, sessionOnly: true, sessionPolicy: policy,
    }));
    return true;
}

function saveSession(session, { sessionOnly = true } = {}) {
    if (typeof window === "undefined") {
        return session;
    }

    const normalizedSession = {
        ...session,
        sessionOnly: true,
        sessionPolicy: initialSessionPolicy(session),
        user: normalizeUser(session?.user),
    };
    const targetStorageName = "sessionStorage";
    const otherStorageName = "localStorage";

    // Never leave a previous employee/admin token behind in the alternate
    // storage location. This is especially important when a normal browser
    // session is converted into a shared farm device.
    safeStorageRemove(otherStorageName, storageKeys.authSession);
    safeStorageRemove(otherStorageName, storageKeys.profile);
    safeStorageRemove(otherStorageName, storageKeys.legacyAuthenticated);

    if (!safeStorageSet(targetStorageName, storageKeys.authSession, JSON.stringify(normalizedSession))) {
        authService.logout(normalizedSession.accessToken).catch(() => {});
        throw new Error("Temporary browser storage is unavailable. Enable it before signing in.");
    }
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

    const previous = safelyParse(safeStorageGet("sessionStorage", storageKeys.authSession), null);
    publishSessionSignal("logout", sessionIdentity(previous));
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
    const sessionRef = useRef(session);
    sessionRef.current = session;

    const syncSession = useCallback(() => {
        setSession(readStoredSession());
    }, []);

    const updateSessionPolicy = useCallback((policy, token) => {
        if (!persistSessionPolicy(policy, token)) return;
        setSession((current) => current?.accessToken === token
            ? { ...current, sessionPolicy: policy }
            : current);
    }, []);

    useEffect(() => {
        // Never leave the application on the boot screen if a shared/mobile
        // browser blocks Web Storage or contains a malformed session.
        try {
            syncSession();
        } catch {
            setSession(null);
        }

        const handleSignal = (signal) => {
            const current = readStoredSession();
            if (!current || signal?.sessionId !== sessionIdentity(current)) return;
            if (signal.kind === "logout") { clearSession(); setSession(null); }
            if (signal.kind === "activity" && Number.isFinite(signal.policy?.idleDeadline)) {
                const currentPolicy = initialSessionPolicy(current);
                const policy = { ...currentPolicy,
                    idleDeadline: Math.min(Math.max(signal.policy.idleDeadline, currentPolicy.idleDeadline), currentPolicy.absoluteDeadline) };
                updateSessionPolicy(policy, current.accessToken);
            }
        };
        const stopSessionTabs = connectSessionTabs({ read: readStoredSession,
            adopt: (shared) => { if (!readStoredSession()) setSession(saveSession(shared)); },
            ready: () => setIsLoading(false), signal: handleSignal });
        const handleStorage = (event) => {
            if (event.key === SESSION_SIGNAL_KEY && event.newValue) {
                handleSignal(safelyParse(event.newValue, null)); return;
            }
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
            stopSessionTabs();
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
    }, [syncSession, updateSessionPolicy]);

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
                sessionOnly: true,
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
                    sessionOnly: true,
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
        const currentToken = sessionRef.current?.accessToken;
        const revocation = authService.logout(currentToken);
        if (forceLocal && sessionWasNotReplaced(currentToken)) { clearSession(); setSession(null); }
        else setAuthError(null);
        try {
            await revocation;
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
        if (sessionRef.current?.accessToken === currentToken && sessionWasNotReplaced(currentToken)) { clearSession(); setSession(null); }
        return { serverReleased };
    }, []);

    const refreshCurrentUser = useCallback(async () => {
        if (!session) {
            return null;
        }

        const currentUser = await authService.getCurrentUser();
        const latestSession = readStoredSession();
        if (
            latestSession?.accessToken !== session.accessToken ||
            String(latestSession?.user?.id) !== String(session.user?.id) ||
            String(currentUser.id) !== String(session.user?.id)
        ) {
            return null;
        }
        const updatedSession = saveSession(
            {
                ...latestSession,
                user: currentUser,
            },
            { sessionOnly: Boolean(latestSession?.sessionOnly) }
        );

        setSession(updatedSession);
        return updatedSession.user;
    }, [session?.accessToken, session?.user?.id]);

    const updateCurrentUser = useCallback(
        async (changes) => {
            const currentSession = readStoredSession();
            if (!session?.accessToken || currentSession?.accessToken !== session.accessToken) {
                throw new Error("Your session ended. Please sign in again.");
            }
            const currentUser = currentSession.user;

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

            const latestSession = readStoredSession();
            if (latestSession?.accessToken !== currentSession.accessToken
                || String(latestSession?.user?.id) !== String(currentUser.id)) {
                throw new Error("Your session changed. Sign in again before updating your profile.");
            }
            const updatedSession = saveSession(
                {
                    ...latestSession,
                    user: {
                        ...latestSession.user,
                        ...updatedUser,
                    },
                },
                { sessionOnly: true }
            );

            setSession(updatedSession);
            return updatedSession.user;
        },
        [session?.accessToken, session?.user]
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
        [session?.user]
    );

    const expireSession = useCallback((reason, token) => {
        if (sessionRef.current?.accessToken !== token || !sessionWasNotReplaced(token)) return;
        logout({ forceLocal: true }).catch(() => {});
        setAuthError(reason === "idle" ? "You were signed out after 15 minutes of inactivity. Please sign in again." : "Your session ended. Please sign in again.");
    }, [logout]);
    const sessionPolicy = useSessionPolicy({ session, onPolicy: updateSessionPolicy, onExpire: expireSession });

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
            <SessionTimeoutWarning open={sessionPolicy.warning} seconds={sessionPolicy.seconds} reason={sessionPolicy.reason}
                busy={sessionPolicy.busy} error={sessionPolicy.error} onStay={sessionPolicy.staySignedIn}
                onKeepWorking={sessionPolicy.keepWorking} onLogout={() => logout({ forceLocal: true }).catch(() => {})}/>
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
