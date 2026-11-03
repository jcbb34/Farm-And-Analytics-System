function readBoolean(value, fallback = false) {
    if (value === undefined || value === null || value === "") {
        return fallback;
    }

    return String(value).toLowerCase() === "true";
}

function readNumber(value, fallback) {
    const parsedValue = Number(value);

    return Number.isFinite(parsedValue)
        ? parsedValue
        : fallback;
}

export const appConfig = Object.freeze({
    appName:
        process.env.NEXT_PUBLIC_APP_NAME ||
        "Joross Farm",

    // All browser traffic goes through the Next.js proxy. In particular, an
    // old .env.local must never pin a phone to a previous Wi-Fi address.
    apiBaseUrl: "/api/v1",

    useMockApi: readBoolean(
        process.env.NEXT_PUBLIC_USE_MOCK_API,
        false
    ),

    requestTimeoutMs: readNumber(
        process.env.NEXT_PUBLIC_REQUEST_TIMEOUT_MS,
        15000
    ),
});

export const storageKeys = Object.freeze({
    authSession: "joross-auth-session-v1",
    legacyAuthenticated: "isAuthenticated",
    profile: "joross-profile",
    users: "joross-users-v1",
    roles: "joross-roles-v1",
    notifications: "joross-app-notifications-v1",
    lastLogout: "joross-last-logout",
    twoFactorChallenge: "joross-two-factor-login-v1",
});
