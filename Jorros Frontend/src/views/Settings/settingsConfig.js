// Default notification choices
export const initialNotificationSettings = {
    cropAlerts: true,
    livestockAlerts: true,
    weatherAlerts: true,
    inventoryAlerts: true,
    systemAlerts: true,
    emailNotifications: true,
    inAppNotifications: true,
    soundNotifications: true,
    notificationFrequency: "Immediate",
};

// Settings menu sections
export const settingSections = [
    {
        id: "account",
        label: "Account",
        icon: "person",
        description: "Profile, password, and account information",
    },
    {
        id: "users",
        label: "User Management",
        icon: "manage_accounts",
        description: "Create and manage user accounts",
        administratorOnly: true,
    },
    {
        id: "security",
        label: "Security and Access",
        icon: "security",
        description: "Roles and module permissions",
        administratorOnly: true,
    },
    {
        id: "data",
        label: "System Data",
        icon: "database",
        description: "Export, import, backup, and reset",
        administratorOnly: true,
    },
    {
        id: "notifications",
        label: "Notifications",
        icon: "notifications",
        description: "Alert and notification preferences",
    },
    {
        id: "archive",
        label: "Archived Records",
        icon: "archive",
        description: "Restore or remove archived records",
    },
];
