import {
    appConfig,
    storageKeys,
} from "../config/appConfig.js";

import { httpClient } from "./httpClient.js";
import { normalizeAccountProfile } from "../utils/accountProfile.js";


const MOCK_ADMIN = Object.freeze({
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


function protectMockAdministrator(profile = {}) {
    const mergedProfile = {
        ...MOCK_ADMIN,
        ...profile,
    };

    const username = String(
        mergedProfile.username || ""
    )
        .trim()
        .toLowerCase();

    const isPrimaryAdministrator =
        mergedProfile.id === MOCK_ADMIN.id ||
        mergedProfile.userCode === MOCK_ADMIN.userCode ||
        username === MOCK_ADMIN.username;

    if (!isPrimaryAdministrator) {
        return mergedProfile;
    }

    return {
        ...mergedProfile,
        id: MOCK_ADMIN.id,
        userCode: MOCK_ADMIN.userCode,
        username: MOCK_ADMIN.username,
        role: "System Administrator",
        status: "Active",
    };
}


function readProfile() {
    try {
        const protectedProfile =
            protectMockAdministrator(
                JSON.parse(
                    localStorage.getItem(
                        storageKeys.profile
                    ) || "{}"
                )
            );

        localStorage.setItem(
            storageKeys.profile,
            JSON.stringify(protectedProfile)
        );

        return protectedProfile;
    } catch {
        return MOCK_ADMIN;
    }
}


function createMockSession(user) {
    return {
        accessToken: `mock-token-${Date.now()}`,
        refreshToken: "mock-refresh-token",
        tokenType: "bearer",
        expiresAt:
            Date.now() +
            8 * 60 * 60 * 1000,
        user,
    };
}


async function mockLogin({
    username,
    password,
}) {
    await new Promise((resolve) =>
        window.setTimeout(resolve, 450)
    );

    const normalizedUsername =
        String(username || "")
            .trim()
            .toLowerCase();

    if (
        normalizedUsername !== "admin" ||
        String(password) !== "1234"
    ) {
        throw new Error(
            "Invalid username or password."
        );
    }

    return createMockSession(
        readProfile()
    );
}


function normalizeLoginResponse(
    response
) {
    const expiresIn = Number(
        response?.expires_in ??
            response?.expiresIn ??
            3600
    );

    return {
        accessToken:
            response?.access_token ??
            response?.accessToken ??
            "",

        refreshToken:
            response?.refresh_token ??
            response?.refreshToken ??
            "",

        tokenType:
            response?.token_type ??
            response?.tokenType ??
            "bearer",

        expiresAt:
            response?.expires_at ??
            response?.expiresAt ??
            Date.now() +
                expiresIn * 1000,

        user: normalizeAccountProfile(
            response?.user
        ),
    };
}


export const authService =
    Object.freeze({
        async login(credentials) {
            if (
                appConfig.useMockApi
            ) {
                return mockLogin(
                    credentials
                );
            }

            const response =
                await httpClient.post(
                    "/auth/login",
                    {
                        username:
                            credentials.username,
                        password:
                            credentials.password,
                    },
                    {
                        includeAuth: false,
                    }
                );

            if (response?.requires_two_factor) {
                return {
                    requiresTwoFactor: true,
                    challengeToken:
                        response.challenge_token,
                    challengeExpiresIn:
                        response.challenge_expires_in ?? 300,
                    username:
                        response.username ?? credentials.username,
                };
            }

            return normalizeLoginResponse(
                response
            );
        },


        async verifyTwoFactorLogin({ challengeToken, otpCode }) {
            if (appConfig.useMockApi) {
                throw new Error(
                    "Two-factor verification is not available in mock mode."
                );
            }

            const response = await httpClient.post(
                "/auth/login/2fa",
                {
                    challenge_token: challengeToken,
                    otp_code: otpCode,
                },
                {
                    includeAuth: false,
                }
            );

            return normalizeLoginResponse(response);
        },


        async getSessionPolicy() { return httpClient.get("/auth/session", { cache: "no-store" }); },
        async reportActivity() { return httpClient.post("/auth/session/activity", {}); },

        async logout(accessToken) {
            if (
                appConfig.useMockApi
            ) {
                return {
                    success: true,
                };
            }

            return httpClient.post(
                "/auth/logout",
                {},
                accessToken ? { includeAuth: false, headers: { Authorization: `Bearer ${accessToken}` } } : {}
            );
        },


        async getCurrentUser() {
            if (
                appConfig.useMockApi
            ) {
                return readProfile();
            }

            const response =
                await httpClient.get(
                    "/auth/me"
                );

            return normalizeAccountProfile(
                response
            );
        },


        async getLoginHistory(limit = 5) {
            if (appConfig.useMockApi) {
                return [];
            }

            const response = await httpClient.get(
                `/auth/me/login-history?limit=${encodeURIComponent(limit)}`
            );
            return Array.isArray(response) ? response : response?.data ?? [];
        },


        async changePassword(payload) {
            if (appConfig.useMockApi) {
                return { success: true };
            }

            return httpClient.post(
                "/auth/change-password",
                {
                    current_password:
                        payload.currentPassword ?? payload.current_password,
                    new_password:
                        payload.newPassword ?? payload.new_password,
                }
            );
        },

        async setupTwoFactor() {
            return httpClient.post(
                "/auth/2fa/setup",
                {}
            );
        },

        async enableTwoFactor(otpCode) {
            return httpClient.post(
                "/auth/2fa/enable",
                { otp_code: otpCode }
            );
        },

        async disableTwoFactor({ currentPassword, otpCode }) {
            return httpClient.post(
                "/auth/2fa/disable",
                {
                    current_password: currentPassword,
                    otp_code: otpCode,
                }
            );
        },
    });
