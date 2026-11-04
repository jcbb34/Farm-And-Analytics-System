// Authentication and User Management must expose the same account record.
export function normalizeAccountProfile(user = {}) {
    return {
        id: user.id,
        personalDetails: user.personalDetails ?? user.personal_details ?? null,
        userCode: user.userCode ?? user.user_code ?? "",
        fullName: user.fullName ?? user.full_name ?? "",
        username: user.username ?? "",
        email: user.email ?? "",
        contactNumber: user.contactNumber ?? user.contact_number ?? "",
        position: user.position ?? "",
        status: user.status ?? "Active",
        role: typeof user.role === "string" ? user.role : user.role?.name ?? "",
        lastLogin: user.lastLogin ?? user.last_login ?? null,
        twoFactorEnabled: Boolean(user.twoFactorEnabled ?? user.two_factor_enabled ?? false),
        permissions: Array.isArray(user.permissions) ? user.permissions : [],
    };
}
