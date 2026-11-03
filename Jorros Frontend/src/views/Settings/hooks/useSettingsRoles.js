"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useState } from "react";

import { userService } from "../../../services/userService.js";
import {
    confirmAction,
    promptAction,
} from "../../../context/NotificationContext.jsx";

// Labels shown in Security & Access.
export const permissionLabels = {
    dashboard: "Dashboard",
    crops: "Crops",
    livestock: "Livestock",
    production_sales: "Production & Sales",
    alerts: "Alerts",
    reports: "Reports",
    intelligence: "Farm Intelligence",
    inventory: "Inventory",
    activities: "Activities & Tasks",
    imports: "Smart Import",
    weather: "Weather",
    settings: "System Settings",
};

const defaultRoles = [
    {
        id: 1,
        roleName: "System Administrator",
        description:
            "Has complete access to all farm management modules and settings.",
        permissions: {
            dashboard: true,
            crops: true,
            livestock: true,
            production_sales: true,
            alerts: true,
            reports: true,
            intelligence: true,
            inventory: true,
            activities: true,
            imports: true,
            weather: true,
            settings: true,
        },
    },
    {
        id: 2,
        roleName: "Farm Staff",
        description:
            "Can manage farm records but cannot change system settings.",
        permissions: {
            dashboard: true,
            crops: true,
            livestock: true,
            production_sales: true,
            alerts: true,
            reports: true,
            intelligence: true,
            inventory: true,
            activities: true,
            imports: true,
            weather: true,
            settings: true,
        },
    },
    {
        id: 3,
        roleName: "Viewer",
        description:
            "Can view farm records and reports but cannot modify information.",
        permissions: {
            dashboard: true,
            crops: true,
            livestock: true,
            production_sales: true,
            alerts: true,
            reports: true,
            intelligence: true,
            inventory: true,
            activities: true,
            imports: false,
            weather: true,
            settings: true,
        },
    },
];

const modulePermissionMap = {
    dashboard: ["dashboard:view"],
    crops: [
        "crops:view",
        "crops:create",
        "crops:update",
        "crops:archive",
        "crops:export",
    ],
    livestock: [
        "livestock:view",
        "livestock:create",
        "livestock:update",
        "livestock:archive",
        "livestock:export",
    ],
    production_sales: [
        "production_sales:view",
        "production_sales:update",
    ],
    alerts: [
        "alerts:view",
        "alerts:create",
        "alerts:update",
        "alerts:test",
    ],
    reports: [
        "reports:view",
        "reports:create",
        "reports:update",
        "reports:export",
    ],
    intelligence: [
        "intelligence:view",
        "intelligence:update",
    ],
    inventory: [
        "inventory:view",
        "inventory:create",
        "inventory:update",
        "inventory:adjust",
        "inventory:archive",
        "inventory:export",
    ],
    activities: [
        "activities:view",
        "activities:create",
        "activities:update",
    ],
    imports: [
        "imports:preview",
        "imports:commit",
    ],
    weather: ["weather:view"],
    settings: [
        "settings:view",
        "settings:profile",
    ],
};

function permissionListToFlags(permissions = []) {
    const permissionSet = new Set(permissions);
    const fullAccess = permissionSet.has("*");

    return Object.fromEntries(
        Object.entries(modulePermissionMap).map(
            ([moduleName, modulePermissions]) => [
                moduleName,
                fullAccess ||
                    modulePermissions.some((permission) =>
                        permissionSet.has(permission)
                    ),
            ]
        )
    );
}

function permissionFlagsToList(flags = {}) {
    return Object.entries(modulePermissionMap).flatMap(
        ([moduleName, modulePermissions]) =>
            flags[moduleName] ? modulePermissions : []
    );
}

function normalizeRole(role = {}) {
    return {
        id: role.id,
        roleName: role.roleName || role.name || "Role",
        description: role.description || "",
        permissions: permissionListToFlags(
            role.permissions || []
        ),
    };
}

// Loads and manages roles used by the Settings page.
export function useSettingsRoles({ enabled = false } = {}) {
    const [roles, setRoles] = useState(defaultRoles);

    useEffect(() => {
        if (!enabled) {
            return undefined;
        }

        let active = true;

        userService
            .getRoles()
            .then((records) => {
                if (active) {
                    setRoles(records.map(normalizeRole));
                }
            })
            .catch((error) => {
                console.error("Failed to load roles:", error);
            });

        return () => {
            active = false;
        };
    }, [enabled]);

    const togglePermission = async (
        roleId,
        permission
    ) => {
        const role = roles.find(
            (item) => item.id === roleId
        );

        if (
            !role ||
            role.roleName === "System Administrator"
        ) {
            return;
        }

        const updatedFlags = {
            ...role.permissions,
            [permission]: !role.permissions[permission],
        };

        setRoles((currentRoles) =>
            currentRoles.map((item) =>
                item.id === roleId
                    ? {
                          ...item,
                          permissions: updatedFlags,
                      }
                    : item
            )
        );

        try {
            const updatedRole =
                await userService.updateRole(roleId, {
                    permissions:
                        permissionFlagsToList(updatedFlags),
                });

            setRoles((currentRoles) =>
                currentRoles.map((item) =>
                    item.id === roleId
                        ? normalizeRole(updatedRole)
                        : item
                )
            );
        } catch (error) {
            setRoles((currentRoles) =>
                currentRoles.map((item) =>
                    item.id === roleId ? role : item
                )
            );

            notify(
                error?.message ||
                    "Unable to update role permissions."
            );
        }
    };

    const addRole = async () => {
        const roleName = await promptAction({
            title: "Add User Role",
            message:
                "Create a new access role for the farm system.",
            label: "Role Name",
            placeholder: "Example: Farm Supervisor",
            confirmText: "Continue",
            cancelText: "Cancel",
            required: true,
        });

        if (!roleName || !roleName.trim()) {
            return;
        }

        const cleanName = roleName.trim();
        const alreadyExists = roles.some(
            (role) =>
                role.roleName.toLowerCase() ===
                cleanName.toLowerCase()
        );

        if (alreadyExists) {
            notify(
                "A role with that name already exists."
            );
            return;
        }

        const description = await promptAction({
            title: "Role Description",
            message: `Describe what ${cleanName} can do in the system.`,
            label: "Description",
            placeholder: "Enter a short role description",
            initialValue: "Custom system access role.",
            confirmText: "Add Role",
            cancelText: "Cancel",
            required: true,
        });

        if (description === null) {
            return;
        }

        const defaultFlags = {
            dashboard: true,
            crops: false,
            livestock: false,
            production_sales: false,
            alerts: false,
            reports: false,
            intelligence: false,
            inventory: false,
            activities: false,
            imports: false,
            weather: false,
            settings: false,
        };

        try {
            const createdRole =
                await userService.createRole({
                    roleName: cleanName,
                    description:
                        description.trim() ||
                        "Custom system access role.",
                    permissions:
                        permissionFlagsToList(defaultFlags),
                });

            setRoles((currentRoles) => [
                ...currentRoles,
                normalizeRole(createdRole),
            ]);

            notify(
                `${cleanName} role added successfully.`
            );
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to add the role."
            );
        }
    };

    const deleteRole = async (role) => {
        if (
            [
                "System Administrator",
                "Farm Staff",
                "Viewer",
            ].includes(role.roleName)
        ) {
            notify(
                "Built-in roles cannot be deleted."
            );
            return;
        }

        const confirmed = await confirmAction({
            title: "Delete User Role",
            message: `Delete the "${role.roleName}" role?`,
            type: "error",
            confirmText: "Delete",
            cancelText: "Cancel",
        });

        if (!confirmed) {
            return;
        }

        try {
            await userService.deleteRole(role.id);

            setRoles((currentRoles) =>
                currentRoles.filter(
                    (item) => item.id !== role.id
                )
            );

            notify(
                `${role.roleName} role deleted successfully.`
            );
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to delete the role."
            );
        }
    };

    return {
        roles,
        addRole,
        deleteRole,
        togglePermission,
    };
}
