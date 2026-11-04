import { httpClient } from "./httpClient.js";
import { normalizeAccountProfile as normalizeUser } from "../utils/accountProfile.js";
import { personalDetailsPayload } from "../components/PersonalDetails/personalDetails.js";


function normalizeRole(role = {}) {
    return {
        id: role.id,
        roleName:
            role.roleName ??
            role.name ??
            "",
        description:
            role.description ??
            "",
        permissions:
            Array.isArray(role.permissions)
                ? role.permissions
                : [],
        isActive:
            role.isActive ??
            role.is_active ??
            true,
    };
}


function createUserPayload(user = {}) {
    return {
        personal_details: personalDetailsPayload(user.personalDetails),
        full_name:
            user.fullName?.trim() ?? "",

        username:
            user.username?.trim() ?? "",

        email:
            user.email?.trim() || null,

        contact_number:
            user.contactNumber?.trim() || null,

        position:
            user.position?.trim() || null,

        password:
            user.password ?? "",

        role_name:
            user.role ?? "Farm Staff",
    };
}


function createUpdatePayload(user = {}) {
    const payload = {};
    if (user.personalDetails !== undefined) payload.personal_details = personalDetailsPayload(user.personalDetails);

    if (user.fullName !== undefined) {
        payload.full_name =
            user.fullName.trim();
    }

    if (user.username !== undefined) {
        payload.username =
            user.username.trim();
    }

    if (user.email !== undefined) {
        payload.email = user.email?.trim() || null;
    }

    if (user.contactNumber !== undefined) {
        payload.contact_number =
            user.contactNumber.trim() || null;
    }

    if (user.position !== undefined) {
        payload.position =
            user.position.trim() || null;
    }

    if (user.role !== undefined) {
        payload.role_name =
            user.role;
    }

    if (user.status !== undefined) {
        payload.status =
            user.status;
    }

    if (
        user.password !== undefined &&
        String(user.password).trim() !== ""
    ) {
        payload.password =
            user.password;
    }

    return payload;
}


export const userService = Object.freeze({
    async getUsers() {
        const response =
            await httpClient.get(
                "/users"
            );

        const users =
            Array.isArray(response)
                ? response
                : response?.data ?? [];

        return users.map(
            normalizeUser
        );
    },


    async getUser(userId) {
        const response =
            await httpClient.get(
                `/users/${userId}`
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async getRoles() {
        const response =
            await httpClient.get(
                "/roles"
            );

        const roles =
            Array.isArray(response)
                ? response
                : response?.data ?? [];

        return roles.map(
            normalizeRole
        );
    },


    async createUser(user) {
        const response =
            await httpClient.post(
                "/users",
                createUserPayload(user)
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async updateUser(
        userId,
        user
    ) {
        const response =
            await httpClient.put(
                `/users/${userId}`,
                createUpdatePayload(user)
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async updateMyProfile(user) {
        const response = await httpClient.put(
            "/users/me",
            createUpdatePayload(user)
        );
        return normalizeUser(response?.data ?? response);
    },

    async createRole(role) {
        const response = await httpClient.post(
            "/roles",
            {
                name: role.roleName ?? role.name,
                description: role.description || null,
                permissions: role.permissions || [],
            }
        );
        return normalizeRole(response?.data ?? response);
    },

    async updateRole(roleId, role) {
        const response = await httpClient.put(
            `/roles/${roleId}`,
            {
                ...(role.roleName !== undefined
                    ? { name: role.roleName }
                    : {}),
                ...(role.description !== undefined
                    ? { description: role.description }
                    : {}),
                ...(role.permissions !== undefined
                    ? { permissions: role.permissions }
                    : {}),
            }
        );
        return normalizeRole(response?.data ?? response);
    },

    async deleteRole(roleId) {
        return httpClient.delete(`/roles/${roleId}`);
    },

    async archiveUser(userId) {
        const response =
            await httpClient.post(
                `/users/${userId}/archive`,
                {}
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async restoreUser(userId) {
        const response =
            await httpClient.post(
                `/users/${userId}/restore`,
                {}
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async disableUser(userId) {
        const response =
            await httpClient.post(
                `/users/${userId}/disable`,
                {}
            );

        return normalizeUser(
            response?.data ?? response
        );
    },


    async activateUser(userId) {
        const response =
            await httpClient.post(
                `/users/${userId}/activate`,
                {}
            );

        return normalizeUser(
            response?.data ?? response
        );
    },
});