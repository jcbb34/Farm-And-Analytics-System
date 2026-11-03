"use client";
import { ArchiveRecords } from "../../components/Archives/Archives.jsx";
import { archiveService } from "../../services/archiveService.js";
import useFarmModuleUpdates from "../../hooks/useFarmModuleUpdates.js";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import { useSearchParams } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";
import UserManagement from "../../components/UserManagement/UserManagement.jsx";
import { SmartImportModal } from "../../components/SmartImport/SmartImport.jsx";
import { cropService } from "../../services/cropService.js";
import { livestockService } from "../../services/livestockService.js";
import { inventoryService } from "../../services/inventoryService.js";
import { reportService } from "../../services/reportService.js";
import { backupService } from "../../services/backupService.js";
import { authService } from "../../services/authService.js";
import TwoFactorSetupModal from "./components/TwoFactorSetupModal.jsx";
import { useSettingsRoles } from "./hooks/useSettingsRoles.js";

import {
    confirmAction,
    notifyWarning,
    promptAction,
} from "../../context/NotificationContext.jsx";

import "./Settings.css";

const permissionLabels = {
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

const initialProfile = {
    fullName: "",
    username: "",
    email: "",
    contactNumber: "",
    position: "",
    role: "",
};


function getStoredProfile() {
    try {
        const storedProfile =
            localStorage.getItem(
                "joross-profile"
            );

        if (!storedProfile) {
            return initialProfile;
        }

        return {
            ...initialProfile,
            ...JSON.parse(
                storedProfile
            ),
        };
    } catch {
        return initialProfile;
    }
}

const initialNotificationSettings = {
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

const NOTIFICATION_SETTINGS_STORAGE_KEY =
    "joross-notification-settings-v1";

function getStoredNotificationSettings() {
    try {
        const storedValue = localStorage.getItem(
            NOTIFICATION_SETTINGS_STORAGE_KEY
        );

        if (!storedValue) {
            return initialNotificationSettings;
        }

        return {
            ...initialNotificationSettings,
            ...JSON.parse(storedValue),
        };
    } catch {
        return initialNotificationSettings;
    }
}

const initialLocalArchivedRecords = [];


const settingSections = [
    {
        id: "account",
        label: "Account",
        icon: "person",
        description:
            "Profile, password, and account information",
    },
    {
        id: "users",
        label: "User Management",
        icon: "manage_accounts",
        description:
            "Create and manage user accounts",
        administratorOnly: true,
    },
    {
        id: "security",
        label: "Security and Access",
        icon: "security",
        description:
            "Roles and module permissions",
        administratorOnly: true,
    },
    {
        id: "data",
        label: "System Data",
        icon: "database",
        description:
            "Export, import, backup, and reset",
    },
    {
        id: "notifications",
        label: "Notifications",
        icon: "notifications",
        description:
            "Alert and notification preferences",
    },
    {
        id: "archive",
        label: "Archived Records",
        icon: "archive",
        description:
            "Restore or remove archived records",
    },
];

function formatDateTime(value) {
    if (!value) {
        return "Not specified";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "Not specified";
    }

    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

function getClassName(value = "") {
    return String(value)
        .toLowerCase()
        .replaceAll(" ", "-")
        .replaceAll("/", "-");
}

function formatFileSize(value) {
    const bytes = Number(value || 0);

    if (bytes < 1024) {
        return `${bytes} B`;
    }

    if (bytes < 1024 * 1024) {
        return `${(bytes / 1024).toFixed(1)} KB`;
    }

    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}


function getInitials(name = "") {
    return name
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toUpperCase();
}

function getFileDate() {
    const date = new Date();

    const year = date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        date.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function downloadFile(
    content,
    filename,
    type
) {
    const blob = new Blob(
        [content],
        {
            type,
        }
    );

    const url =
        URL.createObjectURL(blob);

    const link =
        document.createElement("a");

    link.href = url;
    link.download = filename;

    document.body.appendChild(link);

    link.click();
    link.remove();

    URL.revokeObjectURL(url);
}

function SettingsToggle({
    icon,
    title,
    description,
    checked,
    onChange,
}) {
    return (
        <article className="settings-page-toggle-card">
            <span className="settings-page-toggle-icon">
                <span className="material-symbols-outlined">
                    {icon}
                </span>
            </span>

            <div className="settings-page-toggle-content">
                <strong>
                    {title}
                </strong>

                <p>
                    {description}
                </p>
            </div>

            <button
                type="button"
                role="switch"
                aria-checked={checked}
                className={`settings-page-switch ${
                    checked
                        ? "enabled"
                        : ""
                }`}
                onClick={onChange}
            >
                <span />
            </button>
        </article>
    );
}

function ChangePasswordModal({
    open,
    onClose,
    onPasswordChanged,
}) {
    const [
        form,
        setForm,
    ] = useState({
        currentPassword: "",
        newPassword: "",
        confirmPassword: "",
    });

    const [
        showCurrentPassword,
        setShowCurrentPassword,
    ] = useState(false);

    const [
        showNewPassword,
        setShowNewPassword,
    ] = useState(false);

    const [
        submitting,
        setSubmitting,
    ] = useState(false);

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        setForm({
            currentPassword: "",
            newPassword: "",
            confirmPassword: "",
        });

        setShowCurrentPassword(false);
        setShowNewPassword(false);
        setSubmitting(false);

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open]);

    if (!open) {
        return null;
    }

    const handleChange = (
        event
    ) => {
        const {
            name,
            value,
        } = event.target;

        setForm(
            (currentForm) => ({
                ...currentForm,
                [name]: value,
            })
        );
    };

    const handleSubmit = async (
        event
    ) => {
        event.preventDefault();

        if (
            !form.currentPassword ||
            !form.newPassword ||
            !form.confirmPassword
        ) {
            notify(
                "Please complete all password fields."
            );

            return;
        }

        if (
            form.newPassword.length <
            8
        ) {
            notify(
                "The new password must contain at least eight characters."
            );

            return;
        }

        if (
            form.newPassword !==
            form.confirmPassword
        ) {
            notify(
                "The new passwords do not match."
            );

            return;
        }

        if (
            form.currentPassword ===
            form.newPassword
        ) {
            notify(
                "The new password must be different from the current password."
            );

            return;
        }

        if (submitting) {
            return;
        }

        setSubmitting(true);

        try {
            const result = await authService.changePassword({
                currentPassword: form.currentPassword,
                newPassword: form.newPassword,
            });

            notify(
                result?.message ||
                    "Password changed successfully. Sign in again with your new password."
            );
            onClose();
            await onPasswordChanged?.();
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to change the password."
            );
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <div
            className="settings-page-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="settings-page-password-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="settings-page-modal-header">
                    <div>
                        <h2>
                            Change Password
                        </h2>

                        <p>
                            Enter your current
                            password and create a
                            new secure password.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close password form"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="settings-page-password-form"
                    onSubmit={
                        handleSubmit
                    }
                >
                    <div className="settings-page-form-group">
                        <label htmlFor="currentPassword">
                            Current Password
                            <span>*</span>
                        </label>

                        <div className="settings-page-password-input">
                            <input
                                id="currentPassword"
                                name="currentPassword"
                                type={
                                    showCurrentPassword
                                        ? "text"
                                        : "password"
                                }
                                value={
                                    form.currentPassword
                                }
                                onChange={
                                    handleChange
                                }
                                required
                            />

                            <button
                                type="button"
                                onClick={() =>
                                    setShowCurrentPassword(
                                        (current) =>
                                            !current
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    {showCurrentPassword
                                        ? "visibility_off"
                                        : "visibility"}
                                </span>
                            </button>
                        </div>
                    </div>

                    <div className="settings-page-form-group">
                        <label htmlFor="newPassword">
                            New Password
                            <span>*</span>
                        </label>

                        <div className="settings-page-password-input">
                            <input
                                id="newPassword"
                                name="newPassword"
                                type={
                                    showNewPassword
                                        ? "text"
                                        : "password"
                                }
                                value={
                                    form.newPassword
                                }
                                onChange={
                                    handleChange
                                }
                                required
                            />

                            <button
                                type="button"
                                onClick={() =>
                                    setShowNewPassword(
                                        (current) =>
                                            !current
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    {showNewPassword
                                        ? "visibility_off"
                                        : "visibility"}
                                </span>
                            </button>
                        </div>

                        <small>
                            Use at least eight
                            characters.
                        </small>
                    </div>

                    <div className="settings-page-form-group">
                        <label htmlFor="confirmPassword">
                            Confirm New Password
                            <span>*</span>
                        </label>

                        <input
                            id="confirmPassword"
                            name="confirmPassword"
                            type="password"
                            value={
                                form.confirmPassword
                            }
                            onChange={
                                handleChange
                            }
                            required
                        />
                    </div>

                    <footer className="settings-page-modal-footer">
                        <button
                            type="button"
                            className="settings-page-cancel-button"
                            onClick={onClose}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="settings-page-save-button"
                            disabled={submitting}
                        >
                            <span className="material-symbols-outlined">
                                lock_reset
                            </span>

                            {submitting
                                ? "Changing..."
                                : "Change Password"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}


function ImportHistoryModal({
    open,
    batch,
    details,
    loading,
    error,
    resultFilter = "all",
    onFilterChange,
    onClose,
}) {
    if (!open || !batch) {
        return null;
    }

    const detailBatch =
        details?.batch || batch;

    const rows =
        Array.isArray(details?.rows)
            ? details.rows
            : [];

    const activeFilter =
        details?.resultFilter ||
        resultFilter ||
        "all";

    const filteredRowCount = Number(
        details?.filteredRowCount ??
            rows.length
    );

    const filterOptions = [
        { key: "failed", label: "Failed", count: Number(detailBatch.failedRows || 0) },
        { key: "skipped", label: "Skipped", count: Number(detailBatch.skippedRows || 0) },
        { key: "imported", label: "Imported", count: Number(detailBatch.successRows || 0) },
        { key: "all", label: "All", count: Number(detailBatch.totalRows || 0) },
    ];

    return (
        <div
            className="settings-page-modal-overlay settings-page-import-history-overlay"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settingsImportHistoryTitle"
        >
            <div className="settings-page-import-history-modal">
                <header className="settings-page-import-history-header">
                    <div>
                        <span className="settings-page-eyebrow">
                            SMART IMPORT RECORD
                        </span>

                        <h2 id="settingsImportHistoryTitle">
                            {detailBatch.fileName || "Import Details"}
                        </h2>

                        <p>
                            Review the stored batch summary and row-level results
                            recorded by Smart Import.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="settings-page-import-history-close"
                        onClick={onClose}
                        aria-label="Close import details"
                        title="Close"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="settings-page-import-history-body">
                    <section className="settings-page-import-summary-grid">
                        <article>
                            <span>Module</span>
                            <strong>{detailBatch.module || "General"}</strong>
                        </article>

                        <article>
                            <span>Status</span>
                            <strong>{detailBatch.status || "Unknown"}</strong>
                        </article>

                        <article>
                            <span>Total Rows</span>
                            <strong>{Number(detailBatch.totalRows || 0)}</strong>
                        </article>

                        <article>
                            <span>Successful</span>
                            <strong>{Number(detailBatch.successRows || 0)}</strong>
                        </article>

                        <article>
                            <span>Skipped</span>
                            <strong>{Number(detailBatch.skippedRows || 0)}</strong>
                        </article>

                        <article>
                            <span>Failed</span>
                            <strong>{Number(detailBatch.failedRows || 0)}</strong>
                        </article>
                    </section>

                    {Number(detailBatch.failedRows || 0) > 0 ? (
                        <div className="settings-page-import-issue-banner" role="status">
                            <span className="material-symbols-outlined">error</span>
                            <div>
                                <strong>
                                    {Number(detailBatch.failedRows || 0)} import error(s) need attention
                                </strong>
                                <p>
                                    Failed rows are opened first so problems are never hidden behind successful records.
                                </p>
                            </div>
                        </div>
                    ) : null}

                    <div className="settings-page-import-detail-meta">
                        <div>
                            <span>Imported / Updated</span>
                            <strong>
                                {formatDateTime(
                                    detailBatch.completedAt ||
                                        detailBatch.createdAt
                                )}
                            </strong>
                        </div>

                        {detailBatch.checksum ? (
                            <div>
                                <span>File Fingerprint</span>
                                <strong className="settings-page-import-hash">
                                    {detailBatch.checksum}
                                </strong>
                            </div>
                        ) : null}
                    </div>

                    <section className="settings-page-import-row-section">
                        <div className="settings-page-data-history-heading compact">
                            <div>
                                <h3>Row Results</h3>
                                <p>
                                    Validation and commit results stored for this
                                    import batch.
                                </p>
                            </div>

                            <span className="settings-page-history-count">
                                {loading
                                    ? "Loading..."
                                    : `${rows.length} of ${filteredRowCount} ${
                                          activeFilter === "all" ? "record(s)" : `${activeFilter} record(s)`
                                      }`}
                            </span>
                        </div>

                        <div className="settings-page-import-result-toolbar">
                            <div className="settings-page-import-result-filters" role="group" aria-label="Filter import results">
                                {filterOptions.map((option) => (
                                    <button
                                        key={option.key}
                                        type="button"
                                        className={`${
                                            activeFilter === option.key ? "active" : ""
                                        } ${option.key}`}
                                        disabled={loading}
                                        onClick={() => onFilterChange?.(option.key)}
                                    >
                                        <span>{option.label}</span>
                                        <strong>{option.count}</strong>
                                    </button>
                                ))}
                            </div>

                            {details?.rowsTruncated ? (
                                <span className="settings-page-import-truncated-note">
                                    Showing the first {rows.length} matching rows.
                                </span>
                            ) : null}
                        </div>

                        <div className="settings-page-import-rows-wrap">
                            <table className="settings-page-import-rows-table">
                                <thead>
                                    <tr>
                                        <th>Row</th>
                                        <th>Status</th>
                                        <th>Target / Record</th>
                                        <th>Message</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {loading ? (
                                        <tr>
                                            <td colSpan="4" className="settings-page-empty-table">
                                                Loading Smart Import details...
                                            </td>
                                        </tr>
                                    ) : error ? (
                                        <tr>
                                            <td colSpan="4" className="settings-page-empty-table error">
                                                {error}
                                            </td>
                                        </tr>
                                    ) : rows.length > 0 ? (
                                        rows.map((row, index) => (
                                            <tr
                                                key={row.id ?? `${row.rowNumber}-${index}`}
                                                className={`settings-page-import-result-row ${getClassName(
                                                    row.status || "unknown"
                                                )}`}
                                            >
                                                <td>{row.rowNumber ?? index + 1}</td>
                                                <td>
                                                    <span
                                                        className={`settings-page-history-status ${getClassName(
                                                            row.status || "unknown"
                                                        )}`}
                                                    >
                                                        {row.status || "Unknown"}
                                                    </span>
                                                </td>
                                                <td>
                                                    <strong className="settings-page-import-row-record">
                                                        {row.recordName ||
                                                            row.targetType ||
                                                            "—"}
                                                    </strong>
                                                </td>
                                                <td className="settings-page-import-row-message">
                                                    {row.message || "—"}
                                                </td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td colSpan="4" className="settings-page-empty-table">
                                                No row-level records are stored for this batch.
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>

                        {details?.rowsTruncated ? (
                            <p className="settings-page-history-note">
                                Showing the first 250 stored row results for this batch.
                            </p>
                        ) : null}
                    </section>
                </div>

                <footer className="settings-page-import-history-footer">
                    <button
                        type="button"
                        className="settings-page-cancel-button"
                        onClick={onClose}
                    >
                        Close
                    </button>
                </footer>
            </div>
        </div>
    );
}

function Settings() {
    const searchParamsHook = useSearchParams();
    const locationSearch = searchParamsHook.toString();

    const {
        user,
        updateCurrentUser,
        logout,
        isAdministrator,
    } = useAuth();

    const [
        activeSection,
        setActiveSection,
    ] = useState("account");

    const [
        profile,
        setProfile,
    ] = useState(() => ({
        ...getStoredProfile(),
        ...(user || {}),
    }));

    const [
        profileForm,
        setProfileForm,
    ] = useState(() => ({
        ...getStoredProfile(),
        ...(user || {}),
    }));

    const isSystemAdministrator = Boolean(isAdministrator);

    const visibleSettingSections =
        useMemo(
            () =>
                settingSections.filter(
                    (section) =>
                        !section.administratorOnly ||
                        isSystemAdministrator
                ),
            [isSystemAdministrator]
        );

    const {
        roles,
        addRole,
        deleteRole,
        togglePermission,
    } = useSettingsRoles({
        enabled: isSystemAdministrator,
    });

    const [
        notificationSettings,
        setNotificationSettings,
    ] = useState(
        getStoredNotificationSettings
    );

    const [archiveTotal, setArchiveTotal] = useState(null);
    const updateArchiveCounts = (counts) => setArchiveTotal(Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0));

    const [
        archivedRecords,
        setArchivedRecords,
    ] = useState(
        initialLocalArchivedRecords
    );

    const [
        backups,
        setBackups,
    ] = useState([]);

    const [
        backupLoading,
        setBackupLoading,
    ] = useState(false);

    const [
        backupCreating,
        setBackupCreating,
    ] = useState(false);

    const [
        backupError,
        setBackupError,
    ] = useState("");

    const [
        smartImportOpen,
        setSmartImportOpen,
    ] = useState(false);

    const [
        smartImportRefreshKey,
        setSmartImportRefreshKey,
    ] = useState(0);

    const [
        importHistory,
        setImportHistory,
    ] = useState([]);

    const [
        importHistoryLoading,
        setImportHistoryLoading,
    ] = useState(false);

    const [
        importHistoryError,
        setImportHistoryError,
    ] = useState("");

    const [
        importHistoryOpen,
        setImportHistoryOpen,
    ] = useState(false);

    const [
        selectedImportBatch,
        setSelectedImportBatch,
    ] = useState(null);

    const [
        importHistoryDetails,
        setImportHistoryDetails,
    ] = useState(null);

    const [
        importDetailsLoading,
        setImportDetailsLoading,
    ] = useState(false);

    const [
        importDetailsError,
        setImportDetailsError,
    ] = useState("");

    const [
        importDetailsFilter,
        setImportDetailsFilter,
    ] = useState("all");

    const [
        archiveSearch,
        setArchiveSearch,
    ] = useState("");

    const [
        archiveModuleFilter,
        setArchiveModuleFilter,
    ] = useState("All");

    const [
        profileOpen,
        setProfileOpen,
    ] = useState(false);

    const [
        passwordModalOpen,
        setPasswordModalOpen,
    ] = useState(false);

    const [
        twoFactorEnabled,
        setTwoFactorEnabled,
    ] = useState(false);

    const [
        twoFactorSetup,
        setTwoFactorSetup,
    ] = useState(null);

    const [
        recentLoginActivity,
        setRecentLoginActivity,
    ] = useState([]);

    const importFileInput =
        useRef(null);

    const profileMenuRef =
        useRef(null);

    const profileDetailsRef =
        useRef(null);

    const accountSecurityRef =
        useRef(null);

    useEffect(() => {
        if (!user) {
            return;
        }

        const synchronizedProfile = {
            ...getStoredProfile(),
            ...user,
            role: user.role,
        };

        setProfile(synchronizedProfile);
        setProfileForm(synchronizedProfile);
        setTwoFactorEnabled(Boolean(user.twoFactorEnabled));

        localStorage.setItem(
            "joross-profile",
            JSON.stringify(synchronizedProfile)
        );
    }, [user]);

    useEffect(() => {
        if (!user) {
            setRecentLoginActivity([]);
            return undefined;
        }

        let active = true;
        authService
            .getLoginHistory(5)
            .then((records) => {
                if (active) {
                    setRecentLoginActivity(records);
                }
            })
            .catch(() => {
                if (active) {
                    setRecentLoginActivity([]);
                }
            });

        return () => {
            active = false;
        };
    }, [user]);

    useEffect(() => {
        const handleOutsideClick = (
            event
        ) => {
            if (
                profileMenuRef.current &&
                !profileMenuRef.current.contains(
                    event.target
                )
            ) {
                setProfileOpen(false);
            }
        };

        const handleEscapeKey = (
            event
        ) => {
            if (event.key === "Escape") {
                setProfileOpen(false);
            }
        };

        document.addEventListener(
            "mousedown",
            handleOutsideClick
        );

        document.addEventListener(
            "keydown",
            handleEscapeKey
        );

        return () => {
            document.removeEventListener(
                "mousedown",
                handleOutsideClick
            );

            document.removeEventListener(
                "keydown",
                handleEscapeKey
            );
        };
    }, []);

    useEffect(() => {
        const searchParams =
            new URLSearchParams(
                locationSearch
            );

        const requestedSection =
            searchParams.get(
                "section"
            );

        const requestedFocus =
            searchParams.get(
                "focus"
            );

        const validSections =
            visibleSettingSections.map(
                (section) =>
                    section.id
            );

        const requestedSectionConfig =
            settingSections.find(
                (section) =>
                    section.id === requestedSection
            );

        if (
            requestedSectionConfig?.administratorOnly &&
            !isSystemAdministrator
        ) {
            setActiveSection("account");

            notifyWarning(
                "Only a System Administrator can access this settings section."
            );
        } else if (
            requestedFocus ===
                "profile" ||
            requestedFocus ===
                "security"
        ) {
            setActiveSection(
                "account"
            );
        } else if (
            requestedSection &&
            validSections.includes(
                requestedSection
            )
        ) {
            setActiveSection(
                requestedSection
            );
        }

        if (!requestedFocus) {
            return undefined;
        }

        const scrollTimer =
            window.setTimeout(
                () => {
                    const target =
                        requestedFocus ===
                        "security"
                            ? accountSecurityRef.current
                            : profileDetailsRef.current;

                    target?.scrollIntoView({
                        behavior: "smooth",
                        block: "start",
                    });
                },
                120
            );

        return () =>
            window.clearTimeout(
                scrollTimer
            );
    }, [
        locationSearch,
        isSystemAdministrator,
        visibleSettingSections,
    ]);

    useEffect(() => {
        const activeSectionConfig =
            settingSections.find(
                (section) =>
                    section.id === activeSection
            );

        if (
            !isSystemAdministrator &&
            activeSectionConfig?.administratorOnly
        ) {
            setActiveSection("account");

            notifyWarning(
                "Only a System Administrator can access this settings section."
            );
        }
    }, [activeSection, isSystemAdministrator]);

    useEffect(() => {
        let cancelled = false;

        if (!isSystemAdministrator) {
            setBackups([]);
            setBackupError("");
            setImportHistory([]);
            setImportHistoryError("");
            return undefined;
        }

        const loadBackupHistory = async () => {
            try {
                setBackupLoading(true);
                setBackupError("");

                const records =
                    await backupService.getBackups(50);

                if (!cancelled) {
                    setBackups(records);
                }
            } catch (error) {
                if (!cancelled) {
                    console.error(
                        "Failed to load backup history:",
                        error
                    );

                    setBackupError(
                        error?.message ||
                            "Unable to load backup history."
                    );
                }
            } finally {
                if (!cancelled) {
                    setBackupLoading(false);
                }
            }
        };

        const loadSmartImportHistory = async () => {
            try {
                setImportHistoryLoading(true);
                setImportHistoryError("");

                const records =
                    await backupService.getImportHistory(50);

                if (!cancelled) {
                    setImportHistory(records);
                }
            } catch (error) {
                if (!cancelled) {
                    console.error(
                        "Failed to load Smart Import history:",
                        error
                    );

                    setImportHistoryError(
                        error?.message ||
                            "Unable to load Smart Import history."
                    );
                }
            } finally {
                if (!cancelled) {
                    setImportHistoryLoading(false);
                }
            }
        };

        loadBackupHistory();
        loadSmartImportHistory();

        return () => {
            cancelled = true;
        };
    }, [isSystemAdministrator, smartImportRefreshKey]);

    useEffect(() => {
        archiveService.list({ counts_only: true }).then((result) => updateArchiveCounts(result.counts || {})).catch(() => {});
    }, []);
    useFarmModuleUpdates(["archives"], async () => {
        const result = await archiveService.list({ counts_only: true }); updateArchiveCounts(result.counts || {});
    });

    const openAccountTarget = (
        targetName
    ) => {
        setActiveSection(
            "account"
        );

        setProfileOpen(false);

        window.setTimeout(
            () => {
                const target =
                    targetName ===
                    "security"
                        ? accountSecurityRef.current
                        : profileDetailsRef.current;

                target?.scrollIntoView({
                    behavior: "smooth",
                    block: "start",
                });
            },
            80
        );
    };

    const filteredArchivedRecords =
        useMemo(() => {
            const search =
                archiveSearch
                    .trim()
                    .toLowerCase();

            return archivedRecords.filter(
                (record) => {
                    const matchesSearch =
                        !search ||
                        record.recordName
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        record.reason
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        record.archivedBy
                            .toLowerCase()
                            .includes(
                                search
                            );

                    const matchesModule =
                        archiveModuleFilter ===
                            "All" ||
                        record.module ===
                            archiveModuleFilter;

                    return (
                        matchesSearch &&
                        matchesModule
                    );
                }
            );
        }, [
            archivedRecords,
            archiveSearch,
            archiveModuleFilter,
        ]);

    const handleProfileChange = (
        event
    ) => {
        const {
            name,
            value,
        } = event.target;

        setProfileForm(
            (currentProfile) => ({
                ...currentProfile,
                [name]: value,
            })
        );
    };

    const saveProfile = async (
        event
    ) => {
        event.preventDefault();

        const requiredFields = [
            "fullName",
            "username",
            "email",
            "contactNumber",
            "position",
            "role",
        ];

        const missingField =
            requiredFields.some(
                (fieldName) =>
                    !String(
                        profileForm[
                            fieldName
                        ] || ""
                    ).trim()
            );

        if (missingField) {
            notify(
                "Please complete all account information."
            );

            return;
        }

        if (
            !profileForm.email
                .toLowerCase()
                .endsWith(
                    "@gmail.com"
                )
        ) {
            notify(
                "Please enter a valid Gmail address."
            );

            return;
        }

        if (
            !/^09\d{9}$/.test(
                profileForm.contactNumber
            )
        ) {
            notify(
                "The contact number must contain 11 digits and begin with 09."
            );

            return;
        }

        const savedProfile = {
            ...profileForm,
            role: profile.role,
            status: profile.status || "Active",
        };

        try {
            const updatedUser = await updateCurrentUser(savedProfile);

            setProfile(updatedUser);
            setProfileForm(updatedUser);

            notify(
                "Account information saved successfully."
            );
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to save account information."
            );
        }
    };

    const endSecuritySession = async () => {
        // These settings revoke the access token in the backend before this runs.
        await logout({ forceLocal: true });
        if (typeof window !== "undefined") {
            window.location.assign("/login");
        }
    };

    const toggleTwoFactor = async () => {
        if (!twoFactorEnabled) {
            try {
                const setup = await authService.setupTwoFactor();
                setTwoFactorSetup(setup);
            } catch (error) {
                notify(
                    error?.message ||
                        "Unable to start two-factor authentication setup."
                );
            }
            return;
        }

        const currentPassword = await promptAction({
            title: "Disable Two-Factor Authentication",
            message: "Enter your current password to continue.",
            label: "Current Password",
            confirmText: "Continue",
            cancelText: "Cancel",
            required: true,
            inputType: "password",
        });

        if (!currentPassword) {
            return;
        }

        const otpCode = await promptAction({
            title: "Authenticator Verification",
            message: "Enter the current 6-digit code from your authenticator app.",
            label: "6-Digit Code",
            confirmText: "Disable 2FA",
            cancelText: "Cancel",
            required: true,
        });

        if (!otpCode) {
            return;
        }

        try {
            const result = await authService.disableTwoFactor({
                currentPassword,
                otpCode: otpCode.trim(),
            });
            setTwoFactorEnabled(false);
            notify(
                result?.message ||
                    "Two-factor authentication disabled. Sign in again to continue."
            );
            await endSecuritySession();
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to disable two-factor authentication."
            );
        }
    };

    const handleTwoFactorEnabled = async () => {
        setTwoFactorSetup(null);
        setTwoFactorEnabled(true);
        notify(
            "Two-factor authentication enabled. Sign in again to continue."
        );
        await endSecuritySession();
    };

    const toggleNotification = (
        fieldName
    ) => {
        setNotificationSettings(
            (currentSettings) => ({
                ...currentSettings,

                [fieldName]:
                    !currentSettings[
                        fieldName
                    ],
            })
        );
    };


    // Saves notification preferences so the header can use them too.
    const saveNotificationSettings = () => {
        try {
            localStorage.setItem(
                NOTIFICATION_SETTINGS_STORAGE_KEY,
                JSON.stringify(
                    notificationSettings
                )
            );

            window.dispatchEvent(
                new CustomEvent(
                    "joross:notification-settings-updated",
                    {
                        detail: notificationSettings,
                    }
                )
            );

            notify(
                "Notification settings saved successfully."
            );
        } catch {
            notify(
                "Unable to save notification settings in this browser."
            );
        }
    };

    const exportSystemData = () => {
        const exportData = {
            version: 2,
            exportedAt: new Date().toISOString(),
            notificationSettings,
        };

        downloadFile(
            JSON.stringify(exportData, null, 2),
            `joross-farm-preferences-${getFileDate()}.json`,
            "application/json"
        );

        notify(
            "Notification preferences exported successfully."
        );
    };

    const createBackup = async () => {
        if (!isSystemAdministrator) {
            notifyWarning(
                "Only a System Administrator can create database backups."
            );
            return;
        }

        const confirmed =
            await confirmAction({
                title: "Create Database Backup",
                message:
                    "Back up the current Joross Farm database together with task evidence photos and thumbnails?",
                type: "warning",
                confirmText: "Create Backup",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            setBackupCreating(true);
            setBackupError("");

            const backup =
                await backupService.createBackup();

            setBackups(
                (currentBackups) => [
                    backup,
                    ...currentBackups.filter(
                        (record) =>
                            record.id !== backup.id
                    ),
                ]
            );

            notify(
                `Database backup ${backup.backupCode} created successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to create database backup:",
                error
            );

            setBackupError(
                error?.message ||
                    "Unable to create database backup."
            );

            notify(
                error?.message ||
                    "Unable to create database backup."
            );
        } finally {
            setBackupCreating(false);
        }
    };

    const downloadBackup = async (
        backup
    ) => {
        try {
            if (backup.recoveryAvailable) {
                const content = await backupService.getRecoveryPackage(backup.id);
                downloadFile(content, `${backup.backupCode}.recovery.zip`, "application/zip");
                return;
            }
            const content =
                await backupService.getBackupContent(
                    backup.id
                );

            downloadFile(
                JSON.stringify(
                    content,
                    null,
                    2
                ),
                backup.filename ||
                    `${backup.backupCode}.json`,
                "application/json"
            );
        } catch (error) {
            console.error(
                "Failed to download backup:",
                error
            );

            notify(
                error?.message ||
                    "Unable to download the backup."
            );
        }
    };

    const loadImportHistoryDetails = async (
        batch,
        resultFilter
    ) => {
        if (!batch?.id) {
            return;
        }

        try {
            setImportDetailsLoading(true);
            setImportDetailsError("");

            const details =
                await backupService.getImportHistoryDetails(
                    batch.id,
                    {
                        resultFilter,
                        limit: 1000,
                        offset: 0,
                    }
                );

            setImportHistoryDetails(details);
        } catch (error) {
            console.error(
                "Failed to load Smart Import details:",
                error
            );

            setImportDetailsError(
                error?.message ||
                    "Unable to load Smart Import details."
            );
        } finally {
            setImportDetailsLoading(false);
        }
    };

    const openImportHistoryDetails = async (
        batch,
        preferredFilter = null
    ) => {
        const initialFilter =
            preferredFilter ||
            (Number(batch?.failedRows || 0) > 0
                ? "failed"
                : Number(batch?.skippedRows || 0) > 0
                ? "skipped"
                : "all");

        setSelectedImportBatch(batch);
        setImportHistoryOpen(true);
        setImportHistoryDetails(null);
        setImportDetailsFilter(initialFilter);
        setImportDetailsError("");

        await loadImportHistoryDetails(
            batch,
            initialFilter
        );
    };

    const changeImportDetailsFilter = async (nextFilter) => {
        if (!selectedImportBatch || nextFilter === importDetailsFilter) {
            return;
        }

        setImportDetailsFilter(nextFilter);
        await loadImportHistoryDetails(
            selectedImportBatch,
            nextFilter
        );
    };

    const closeImportHistoryDetails = () => {
        setImportHistoryOpen(false);
        setSelectedImportBatch(null);
        setImportHistoryDetails(null);
        setImportDetailsFilter("all");
        setImportDetailsError("");
    };

    const openSmartImport = () => {
        setSmartImportOpen(true);
    };

    const openImportFile = () => {
        importFileInput.current?.click();
    };

    const handleImportData = (event) => {
        const file = event.target.files?.[0];

        if (!file) {
            return;
        }

        const reader = new FileReader();

        reader.onload = () => {
            try {
                const importedData = JSON.parse(reader.result);
                const data = importedData.data || importedData;

                if (
                    !data.notificationSettings ||
                    typeof data.notificationSettings !== "object" ||
                    Array.isArray(data.notificationSettings)
                ) {
                    throw new Error("Missing notification settings.");
                }

                const importedNotificationSettings = {
                    ...initialNotificationSettings,
                    ...data.notificationSettings,
                };

                setNotificationSettings(importedNotificationSettings);
                localStorage.setItem(
                    NOTIFICATION_SETTINGS_STORAGE_KEY,
                    JSON.stringify(importedNotificationSettings)
                );

                window.dispatchEvent(
                    new CustomEvent(
                        "joross:notification-settings-updated",
                        { detail: importedNotificationSettings }
                    )
                );

                notify(
                    "Notification preferences restored successfully."
                );
            } catch {
                notify(
                    "The selected file does not contain valid Joross Farm preferences."
                );
            }

            event.target.value = "";
        };

        reader.readAsText(file);
    };

    const resetSystemData = async () => {
        const confirmed = await confirmAction({
            title: "Reset Local Preferences",
            message:
                "Restore browser notification preferences to their defaults? Database records, users, roles, profile information, backups, and two-factor authentication will not be changed.",
            type: "warning",
            confirmText: "Reset Preferences",
            cancelText: "Cancel",
        });

        if (!confirmed) {
            return;
        }

        setNotificationSettings(initialNotificationSettings);
        localStorage.setItem(
            NOTIFICATION_SETTINGS_STORAGE_KEY,
            JSON.stringify(initialNotificationSettings)
        );
        window.dispatchEvent(
            new CustomEvent(
                "joross:notification-settings-updated",
                { detail: initialNotificationSettings }
            )
        );

        notify(
            "Local notification preferences reset successfully."
        );
    };

    const restoreRecord = async (
        record
    ) => {
        const confirmed =
            await confirmAction({
                title: "Restore Archived Record",
                message:
                    `Restore "${record.recordName}"?`,
                type: "info",
                confirmText: "Restore",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            if (record.apiBacked) {
                if (
                    record.module ===
                    "Crop"
                ) {
                    await cropService.restoreCrop(
                        record.sourceId
                    );
                } else if (
                    record.module ===
                    "Livestock"
                ) {
                    await livestockService.restoreLivestock(
                        record.sourceId
                    );
                } else if (
                    record.module ===
                    "Inventory"
                ) {
                    await inventoryService.restoreInventory(
                        record.sourceId
                    );
                } else if (
                    record.module ===
                    "Report"
                ) {
                    await reportService.restoreReport(
                        record.sourceId
                    );
                }
            }

            setArchivedRecords(
                (currentRecords) =>
                    currentRecords.filter(
                        (item) =>
                            item.id !==
                            record.id
                    )
            );

            notify(
                `${record.recordName} was restored successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to restore archived record:",
                error
            );

            notify(
                error?.message ||
                    `Unable to restore ${record.recordName}.`
            );
        }
    };

    const deleteArchivedRecord = async (
        record
    ) => {
        const confirmed =
            await confirmAction({
                title:
                    "Permanently Delete Record",
                message:
                    `Permanently remove "${record.recordName}" from archived records? This cannot be undone.`,
                type: "error",
                confirmText:
                    "Delete Permanently",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        if (
            [
                "Crop",
                "Livestock",
                "Inventory",
                "Report",
            ].includes(record.module) &&
            record.apiBacked
        ) {
            notify(
                `Permanent deletion of archived ${record.module.toLowerCase()} records is not enabled in the backend yet. You can restore the record or keep it archived.`
            );
            return;
        }

        setArchivedRecords(
            (currentRecords) =>
                currentRecords.filter(
                    (item) =>
                        item.id !==
                        record.id
                )
        );

        notify(
            `${record.recordName} was permanently deleted.`
        );
    };

    const renderAccountSection =
        () => (
            <section className="settings-page-section">
                <div className="settings-page-section-heading">
                    <div>
                        <h2>
                            Account Settings
                        </h2>

                        <p>
                            Manage your profile
                            information, password,
                            and account security.
                        </p>
                    </div>
                </div>

                <article
                    ref={
                        profileDetailsRef
                    }
                    className="settings-page-account-card settings-page-scroll-target"
                >
                    <div className="settings-page-account-profile">
                        <span className="settings-page-large-avatar">
                            {getInitials(
                                profile.fullName
                            )}
                        </span>

                        <div>
                            <h3>
                                {
                                    profile.fullName
                                }
                            </h3>

                            <p>
                                {
                                    profile.role
                                }
                            </p>

                            <small>
                                {
                                    profile.email
                                }
                            </small>
                        </div>
                    </div>

                    <form
                        className="settings-page-account-form"
                        onSubmit={
                            saveProfile
                        }
                    >
                        <div className="settings-page-form-grid">
                            <div className="settings-page-form-group">
                                <label htmlFor="settingsFullName">
                                    Full Name
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsFullName"
                                    name="fullName"
                                    type="text"
                                    value={
                                        profileForm.fullName
                                    }
                                    onChange={
                                        handleProfileChange
                                    }
                                    required
                                />
                            </div>

                            <div className="settings-page-form-group">
                                <label htmlFor="settingsUsername">
                                    Username
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsUsername"
                                    name="username"
                                    type="text"
                                    value={
                                        profileForm.username
                                    }
                                    onChange={
                                        handleProfileChange
                                    }
                                    required
                                />
                            </div>

                            <div className="settings-page-form-group">
                                <label htmlFor="settingsEmail">
                                    Email Address
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsEmail"
                                    name="email"
                                    type="email"
                                    value={
                                        profileForm.email
                                    }
                                    onChange={
                                        handleProfileChange
                                    }
                                    required
                                />
                            </div>

                            <div className="settings-page-form-group">
                                <label htmlFor="settingsContact">
                                    Contact Number
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsContact"
                                    name="contactNumber"
                                    type="text"
                                    maxLength="11"
                                    value={
                                        profileForm.contactNumber
                                    }
                                    onChange={
                                        handleProfileChange
                                    }
                                    required
                                />
                            </div>

                            <div className="settings-page-form-group">
                                <label htmlFor="settingsPosition">
                                    Position
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsPosition"
                                    name="position"
                                    type="text"
                                    value={
                                        profileForm.position
                                    }
                                    onChange={
                                        handleProfileChange
                                    }
                                    required
                                />
                            </div>

                            <div className="settings-page-form-group">
                                <label htmlFor="settingsRole">
                                    Role
                                    <span>*</span>
                                </label>

                                <input
                                    id="settingsRole"
                                    name="role"
                                    type="text"
                                    value={
                                        profile.role
                                    }
                                    readOnly
                                    aria-readonly="true"
                                />

                                <small>
                                    Your own role cannot be changed here. Roles are assigned by a System Administrator through User Management.
                                </small>
                            </div>
                        </div>

                        <div className="settings-page-account-form-footer">
                            <button
                                type="submit"
                                className="settings-page-primary-button"
                            >
                                <span className="material-symbols-outlined">
                                    save
                                </span>

                                Save Account
                            </button>
                        </div>
                    </form>
                </article>

                <div
                    ref={
                        accountSecurityRef
                    }
                    className="settings-page-security-actions settings-page-scroll-target"
                >
                    <article className="settings-page-action-card">
                        <span className="settings-page-action-icon">
                            <span className="material-symbols-outlined">
                                password
                            </span>
                        </span>

                        <div>
                            <h3>
                                Password
                            </h3>

                            <p>
                                Change your
                                account password
                                regularly to keep
                                your account secure.
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={() =>
                                setPasswordModalOpen(
                                    true
                                )
                            }
                        >
                            Change Password
                        </button>
                    </article>

                    <article className="settings-page-action-card">
                        <span className="settings-page-action-icon">
                            <span className="material-symbols-outlined">
                                verified_user
                            </span>
                        </span>

                        <div>
                            <h3>
                                Two-Factor
                                Authentication
                            </h3>

                            <p>
                                Add another
                                verification step
                                when signing in.
                            </p>
                        </div>

                        <button
                            type="button"
                            className={
                                twoFactorEnabled
                                    ? "enabled"
                                    : ""
                            }
                            onClick={
                                toggleTwoFactor
                            }
                        >
                            {twoFactorEnabled
                                ? "Enabled"
                                : "Enable 2FA"}
                        </button>
                    </article>
                </div>

                <article className="settings-page-activity-card">
                    <div className="settings-page-card-heading">
                        <div>
                            <h3>
                                Recent Sign-in Activity
                            </h3>

                            <p>
                                Latest successful and failed sign-in attempts
                                recorded for this account.
                            </p>
                        </div>

                        <span className="material-symbols-outlined">
                            history
                        </span>
                    </div>

                    <div className="settings-page-activity-list">
                        {recentLoginActivity.length ? (
                            recentLoginActivity.map((activity) => (
                                <div key={activity.id}>
                                    <span>
                                        <span className="material-symbols-outlined">
                                            {activity.success ? "login" : "warning"}
                                        </span>
                                    </span>

                                    <div>
                                        <strong>
                                            {activity.success
                                                ? "Successful sign-in"
                                                : "Failed sign-in attempt"}
                                        </strong>
                                        <small>
                                            {formatDateTime(
                                                activity.created_at || activity.createdAt
                                            )}
                                            {activity.ip_address || activity.ipAddress
                                                ? ` • ${activity.ip_address || activity.ipAddress}`
                                                : ""}
                                        </small>
                                    </div>
                                </div>
                            ))
                        ) : (
                            <div>
                                <span>
                                    <span className="material-symbols-outlined">history</span>
                                </span>
                                <div>
                                    <strong>No sign-in history available</strong>
                                    <small>New sign-in attempts will appear here.</small>
                                </div>
                            </div>
                        )}
                    </div>
                </article>
            </section>
        );

    const renderSecuritySection =
        () => (
            <section className="settings-page-section">
                <div className="settings-page-section-heading with-button">
                    <div>
                        <h2>
                            Security and Access
                        </h2>

                        <p>
                            Manage user roles and
                            control which modules
                            each role can access.
                        </p>
                    </div>

                    <button
                        type="button"
                        className="settings-page-primary-button"
                        onClick={
                            addRole
                        }
                    >
                        <span className="material-symbols-outlined">
                            add
                        </span>

                        Add Role
                    </button>
                </div>

                <div className="settings-page-role-list">
                    {roles.map(
                        (role) => (
                            <article
                                className="settings-page-role-card"
                                key={
                                    role.id
                                }
                            >
                                <div className="settings-page-role-header">
                                    <div>
                                        <span className="material-symbols-outlined">
                                            admin_panel_settings
                                        </span>

                                        <div>
                                            <h3>
                                                {
                                                    role.roleName
                                                }
                                            </h3>

                                            <p>
                                                {
                                                    role.description
                                                }
                                            </p>
                                        </div>
                                    </div>

                                    <button
                                        type="button"
                                        disabled={
                                            role.roleName ===
                                            "System Administrator"
                                        }
                                        onClick={() =>
                                            deleteRole(
                                                role
                                            )
                                        }
                                    >
                                        <span className="material-symbols-outlined">
                                            delete
                                        </span>
                                    </button>
                                </div>

                                <div className="settings-page-permission-grid">
                                    {Object.entries(
                                        permissionLabels
                                    ).map(
                                        ([
                                            permission,
                                            label,
                                        ]) => (
                                            <label
                                                key={
                                                    permission
                                                }
                                                className="settings-page-permission-item"
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={
                                                        Boolean(
                                                            role.permissions[
                                                                permission
                                                            ]
                                                        )
                                                    }
                                                    disabled={
                                                        role.roleName ===
                                                            "System Administrator" &&
                                                        permission ===
                                                            "settings"
                                                    }
                                                    onChange={() =>
                                                        togglePermission(
                                                            role.id,
                                                            permission
                                                        )
                                                    }
                                                />

                                                <span>
                                                    {
                                                        label
                                                    }
                                                </span>
                                            </label>
                                        )
                                    )}
                                </div>
                            </article>
                        )
                    )}
                </div>
            </section>
        );

    const renderDataSection =
        () => (
            <section className="settings-page-section settings-page-data-section">
                <div className="settings-page-section-heading">
                    <div>
                        <h2>Data & Preferences</h2>

                        <p>
                            Manage local notification preferences, create database
                            backups, and review stored system history.
                        </p>
                    </div>
                </div>

                <div className="settings-page-data-grid">
                    <article className="settings-page-data-card export">
                        <span>
                            <span className="material-symbols-outlined">
                                file_download
                            </span>
                        </span>

                        <div>
                            <h3>Export Preferences</h3>
                            <p>
                                Download this browser's notification preferences
                                as a portable JSON file.
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={exportSystemData}
                        >
                            Export Preferences
                        </button>
                    </article>

                    <article className="settings-page-data-card import">
                        <span>
                            <span className="material-symbols-outlined">
                                upload_file
                            </span>
                        </span>

                        <div>
                            <h3>Import Farm Data</h3>
                            <p>
                                Import XLSX, CSV, or JSON farm records through Smart
                                Import. Livestock pens, crop, livestock, inventory, reproduction,
                                production, and sales rows are validated before saving.
                            </p>
                        </div>

                        <div className="settings-page-data-card-actions">
                            <button
                                type="button"
                                onClick={openSmartImport}
                            >
                                Smart Import
                            </button>

                            <button
                                type="button"
                                className="secondary"
                                onClick={openImportFile}
                            >
                                Restore Preferences JSON
                            </button>
                        </div>

                        <input
                            ref={importFileInput}
                            type="file"
                            accept=".json,application/json"
                            hidden
                            onChange={handleImportData}
                        />
                    </article>

                    <article className="settings-page-data-card backup">
                        <span>
                            <span className="material-symbols-outlined">
                                backup
                            </span>
                        </span>

                        <div>
                            <h3>Backup System</h3>
                            <p>
                                Back up the database together with task evidence
                                photos and thumbnails for recovery.
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={createBackup}
                            disabled={backupCreating}
                        >
                            {backupCreating
                                ? "Creating Backup..."
                                : "Create Backup"}
                        </button>
                    </article>

                    <article className="settings-page-data-card reset">
                        <span>
                            <span className="material-symbols-outlined">
                                restart_alt
                            </span>
                        </span>

                        <div>
                            <h3>Reset Preferences</h3>
                            <p>
                                Restore local notification preferences to defaults
                                without changing SQL Server records or account security.
                            </p>
                        </div>

                        <button
                            type="button"
                            onClick={resetSystemData}
                        >
                            Reset Preferences
                        </button>
                    </article>
                </div>

                <article className="settings-page-backup-info database-backed">
                    <span className="material-symbols-outlined">
                        verified
                    </span>

                    <div>
                        <strong>Database-backed history</strong>
                        <p>
                            Backup History and Smart Import History are loaded from
                            FastAPI and SQL Server. Preference export/import only affects
                            browser notification settings; spreadsheet imports are
                            recorded by Smart Import.
                        </p>
                    </div>
                </article>

                <div className="settings-page-data-history-stack">
                    <article className="settings-page-data-history-card">
                        <div className="settings-page-data-history-heading">
                            <div>
                                <span className="settings-page-history-icon">
                                    <span className="material-symbols-outlined">
                                        backup
                                    </span>
                                </span>

                                <div>
                                    <h3>Backup History</h3>
                                    <p>
                                        Database and task-photo recovery backups created
                                        from the live Joross Farm database.
                                    </p>
                                </div>
                            </div>

                            <span className="settings-page-history-count">
                                {backupLoading
                                    ? "Loading..."
                                    : `${backups.length} record(s)`}
                            </span>
                        </div>

                        <div className="settings-page-table-wrapper settings-page-history-table-wrapper">
                            <table className="settings-page-archive-table settings-page-data-history-table">
                                <thead>
                                    <tr>
                                        <th>Backup</th>
                                        <th>Created</th>
                                        <th>Status</th>
                                        <th>Tables</th>
                                        <th>Rows</th>
                                        <th>Size</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {backups.length > 0 ? (
                                        backups.map((backup) => (
                                            <tr key={backup.id}>
                                                <td>
                                                    <div className="settings-page-archive-name">
                                                        <span className="material-symbols-outlined">
                                                            database
                                                        </span>
                                                        <strong>{backup.backupCode}</strong>
                                                    </div>
                                                </td>

                                                <td>
                                                    {formatDateTime(
                                                        backup.completedAt ||
                                                            backup.createdAt
                                                    )}
                                                </td>

                                                <td>
                                                    <span
                                                        className={`settings-page-history-status ${getClassName(
                                                            backup.status
                                                        )}`}
                                                    >
                                                        {backup.status}
                                                    </span>
                                                </td>

                                                <td>{backup.tableCount}</td>
                                                <td>{backup.rowCount}</td>
                                                <td>
                                                    {formatFileSize(
                                                        backup.recoveryAvailable ? backup.recoverySizeBytes : backup.fileSizeBytes
                                                    )}
                                                </td>

                                                <td>
                                                    <div className="settings-page-archive-actions">
                                                        <button
                                                            type="button"
                                                            title="Download backup"
                                                            aria-label="Download backup"
                                                            disabled={
                                                                backup.status !==
                                                                "Completed"
                                                            }
                                                            onClick={() =>
                                                                downloadBackup(backup)
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                download
                                                            </span>
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td
                                                colSpan="7"
                                                className="settings-page-empty-table"
                                            >
                                                <span className="material-symbols-outlined">
                                                    backup
                                                </span>
                                                <p>
                                                    {backupLoading
                                                        ? "Loading backup history..."
                                                        : backupError ||
                                                          "No database backup has been created yet."}
                                                </p>
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <div className="settings-page-table-footer settings-page-history-footer-text">
                            {backupError
                                ? backupError
                                : `Showing ${backups.length} backup record(s)`}
                        </div>
                    </article>

                    <article className="settings-page-data-history-card">
                        <div className="settings-page-data-history-heading">
                            <div>
                                <span className="settings-page-history-icon import">
                                    <span className="material-symbols-outlined">
                                        upload_file
                                    </span>
                                </span>

                                <div>
                                    <h3>Smart Import History</h3>
                                    <p>
                                        Spreadsheet import batches and validation
                                        results stored by the Smart Import workflow.
                                    </p>
                                </div>
                            </div>

                            <div className="settings-page-history-heading-actions">
                                <span className="settings-page-history-count">
                                    {importHistoryLoading
                                        ? "Loading..."
                                        : `${importHistory.length} record(s)`}
                                </span>

                                <button
                                    type="button"
                                    className="settings-page-history-link-button"
                                    onClick={openSmartImport}
                                >
                                    <span className="material-symbols-outlined">
                                        open_in_new
                                    </span>
                                    Open Smart Import
                                </button>
                            </div>
                        </div>

                        <div className="settings-page-table-wrapper settings-page-history-table-wrapper">
                            <table className="settings-page-archive-table settings-page-data-history-table settings-page-import-history-table">
                                <thead>
                                    <tr>
                                        <th>File</th>
                                        <th>Module</th>
                                        <th>Imported</th>
                                        <th>Status</th>
                                        <th>Total</th>
                                        <th>Success</th>
                                        <th>Skipped</th>
                                        <th>Failed</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {importHistory.length > 0 ? (
                                        importHistory.map((batch) => (
                                            <tr key={batch.id}>
                                                <td>
                                                    <div className="settings-page-import-file-cell">
                                                        <span className="material-symbols-outlined">
                                                            table_view
                                                        </span>
                                                        <strong>
                                                            {batch.fileName ||
                                                                `Import #${batch.id}`}
                                                        </strong>
                                                    </div>
                                                </td>

                                                <td>
                                                    <span className="settings-page-module-badge inventory">
                                                        {batch.module || "General"}
                                                    </span>
                                                </td>

                                                <td>
                                                    {formatDateTime(
                                                        batch.completedAt ||
                                                            batch.createdAt
                                                    )}
                                                </td>

                                                <td>
                                                    <span
                                                        className={`settings-page-history-status ${getClassName(
                                                            batch.status
                                                        )}`}
                                                    >
                                                        {batch.status || "Unknown"}
                                                    </span>
                                                </td>

                                                <td>{batch.totalRows}</td>
                                                <td className="settings-page-count-success">
                                                    {batch.successRows}
                                                </td>
                                                <td className="settings-page-count-skipped">
                                                    <button
                                                        type="button"
                                                        className="settings-page-import-count-button skipped"
                                                        disabled={Number(batch.skippedRows || 0) === 0}
                                                        title="Show skipped import rows"
                                                        onClick={() =>
                                                            openImportHistoryDetails(
                                                                batch,
                                                                "skipped"
                                                            )
                                                        }
                                                    >
                                                        {batch.skippedRows}
                                                    </button>
                                                </td>
                                                <td className="settings-page-count-failed">
                                                    <button
                                                        type="button"
                                                        className="settings-page-import-count-button failed"
                                                        disabled={Number(batch.failedRows || 0) === 0}
                                                        title="Show failed import rows"
                                                        onClick={() =>
                                                            openImportHistoryDetails(
                                                                batch,
                                                                "failed"
                                                            )
                                                        }
                                                    >
                                                        {batch.failedRows}
                                                    </button>
                                                </td>

                                                <td>
                                                    <div className="settings-page-archive-actions">
                                                        <button
                                                            type="button"
                                                            title="View import details"
                                                            aria-label="View import details"
                                                            onClick={() =>
                                                                openImportHistoryDetails(
                                                                    batch
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                visibility
                                                            </span>
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        ))
                                    ) : (
                                        <tr>
                                            <td
                                                colSpan="9"
                                                className="settings-page-empty-table"
                                            >
                                                <span className="material-symbols-outlined">
                                                    upload_file
                                                </span>
                                                <p>
                                                    {importHistoryLoading
                                                        ? "Loading Smart Import history..."
                                                        : importHistoryError ||
                                                          "No Smart Import batch has been recorded yet."}
                                                </p>
                                            </td>
                                        </tr>
                                    )}
                                </tbody>
                            </table>
                        </div>

                        <div className="settings-page-table-footer settings-page-history-footer-text">
                            {importHistoryError
                                ? importHistoryError
                                : `Showing ${importHistory.length} Smart Import batch record(s)`}
                        </div>
                    </article>
                </div>
            </section>
        );

    const renderNotificationSection =
        () => (
            <section className="settings-page-section">
                <div className="settings-page-section-heading">
                    <div>
                        <h2>
                            Notification Settings
                        </h2>

                        <p>
                            Choose the farm
                            notifications and
                            delivery methods you
                            want to receive.
                        </p>
                    </div>
                </div>

                <div className="settings-page-toggle-grid">
                    <SettingsToggle
                        icon="grass"
                        title="Crop Alerts"
                        description="Planting, growth, harvest, pest, and crop status notifications."
                        checked={
                            notificationSettings.cropAlerts
                        }
                        onChange={() =>
                            toggleNotification(
                                "cropAlerts"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="pets"
                        title="Livestock Alerts"
                        description="Feeding, vaccination, health, and livestock production notifications."
                        checked={
                            notificationSettings.livestockAlerts
                        }
                        onChange={() =>
                            toggleNotification(
                                "livestockAlerts"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="partly_cloudy_day"
                        title="Weather Alerts"
                        description="Heavy rain, high temperature, strong wind, and storm warnings."
                        checked={
                            notificationSettings.weatherAlerts
                        }
                        onChange={() =>
                            toggleNotification(
                                "weatherAlerts"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="inventory_2"
                        title="Inventory Alerts"
                        description="Low stock, expiration, damaged item, and restocking notifications."
                        checked={
                            notificationSettings.inventoryAlerts
                        }
                        onChange={() =>
                            toggleNotification(
                                "inventoryAlerts"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="settings"
                        title="System Alerts"
                        description="Backup, storage, security, login, and maintenance notifications."
                        checked={
                            notificationSettings.systemAlerts
                        }
                        onChange={() =>
                            toggleNotification(
                                "systemAlerts"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="mail"
                        title="Email Notifications"
                        description="Send important farm notifications to the registered email address."
                        checked={
                            notificationSettings.emailNotifications
                        }
                        onChange={() =>
                            toggleNotification(
                                "emailNotifications"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="notifications_active"
                        title="In-App Notifications"
                        description="Display notifications inside the Joross Farm management system."
                        checked={
                            notificationSettings.inAppNotifications
                        }
                        onChange={() =>
                            toggleNotification(
                                "inAppNotifications"
                            )
                        }
                    />

                    <SettingsToggle
                        icon="volume_up"
                        title="Notification Sound"
                        description="Play a sound when a new important notification is received."
                        checked={
                            notificationSettings.soundNotifications
                        }
                        onChange={() =>
                            toggleNotification(
                                "soundNotifications"
                            )
                        }
                    />
                </div>

                <article className="settings-page-frequency-card">
                    <div>
                        <span className="material-symbols-outlined">
                            schedule
                        </span>

                        <div>
                            <h3>
                                Notification
                                Frequency
                            </h3>

                            <p>
                                Choose how often
                                general notification
                                summaries are
                                delivered.
                            </p>
                        </div>
                    </div>

                    <select
                        value={
                            notificationSettings.notificationFrequency
                        }
                        onChange={(event) =>
                            setNotificationSettings(
                                (current) => ({
                                    ...current,

                                    notificationFrequency:
                                        event
                                            .target
                                            .value,
                                })
                            )
                        }
                    >
                        <option value="Immediate">
                            Immediate
                        </option>

                        <option value="Daily Summary">
                            Daily Summary
                        </option>

                        <option value="Weekly Summary">
                            Weekly Summary
                        </option>
                    </select>
                </article>

                <div className="settings-page-section-save">
                    <button
                        type="button"
                        className="settings-page-primary-button"
                        onClick={
                            saveNotificationSettings
                        }
                    >
                        <span className="material-symbols-outlined">
                            save
                        </span>

                        Save Notifications
                    </button>
                </div>
            </section>
        );

    const renderArchiveSection = () => <ArchiveRecords central onCounts={updateArchiveCounts} />;

    const renderActiveSection =
        () => {
            if (
                activeSection ===
                "users"
            ) {
                return (
                    <UserManagement
                        currentProfile={
                            profile
                        }
                        roles={roles}
                        isAdministrator={
                            isSystemAdministrator
                        }
                    />
                );
            }

            if (
                activeSection ===
                "security"
            ) {
                return isSystemAdministrator
                    ? renderSecuritySection()
                    : renderAccountSection();
            }

            if (
                activeSection ===
                "data"
            ) {
                return renderDataSection();
            }

            if (
                activeSection ===
                "notifications"
            ) {
                return renderNotificationSection();
            }

            if (
                activeSection ===
                "archive"
            ) {
                return renderArchiveSection();
            }

            return renderAccountSection();
        };

    return (
        <div className="settings-page-layout">
            <Sidebar />

            <main className="settings-page-content">
                <header className="settings-page-header">
                    <div className="settings-page-heading">
                        <h1>
                            System Settings
                        </h1>

                        <p>
                            Manage accounts,
                            users, security,
                            system data,
                            notifications, and
                            archived records.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <section className="settings-page-summary-grid">
                    <article className="settings-page-summary-card account">
                        <span>
                            <span className="material-symbols-outlined">
                                person
                            </span>
                        </span>

                        <div>
                            <p>
                                Current Account
                            </p>

                            <h2>
                                {
                                    profile.username
                                }
                            </h2>

                            <small>
                                {
                                    profile.role
                                }
                            </small>
                        </div>
                    </article>

                    <article className="settings-page-summary-card security">
                        <span>
                            <span className="material-symbols-outlined">
                                verified_user
                            </span>
                        </span>

                        <div>
                            <p>
                                Two-Factor
                                Authentication
                            </p>

                            <h2>
                                {twoFactorEnabled
                                    ? "Enabled"
                                    : "Disabled"}
                            </h2>

                            <small>
                                Account security
                            </small>
                        </div>
                    </article>

                    {isSystemAdministrator && (
                        <article className="settings-page-summary-card roles">
                            <span>
                                <span className="material-symbols-outlined">
                                    admin_panel_settings
                                </span>
                            </span>

                            <div>
                                <p>
                                    User Roles
                                </p>

                                <h2>
                                    {roles.length}
                                </h2>

                                <small>
                                    Access roles
                                </small>
                            </div>
                        </article>
                    )}

                    <article className="settings-page-summary-card archive">
                        <span>
                            <span className="material-symbols-outlined">
                                archive
                            </span>
                        </span>

                        <div>
                            <p>
                                Archived Records
                            </p>

                            <h2>
                                {
                                    archiveTotal ?? "—"
                                }
                            </h2>

                            <small>
                                Stored records
                            </small>
                        </div>
                    </article>
                </section>

                <section className="settings-page-main-card">
                    <aside className="settings-page-section-menu">
                        <div className="settings-page-menu-heading">
                            <strong>
                                Settings Menu
                            </strong>

                            <small>
                                Select a settings
                                category
                            </small>
                        </div>

                        {visibleSettingSections.map(
                            (section) => (
                                <button
                                    type="button"
                                    key={
                                        section.id
                                    }
                                    className={
                                        activeSection ===
                                        section.id
                                            ? "active"
                                            : ""
                                    }
                                    onClick={() =>
                                        setActiveSection(
                                            section.id
                                        )
                                    }
                                >
                                    <span className="material-symbols-outlined">
                                        {
                                            section.icon
                                        }
                                    </span>

                                    <span>
                                        <strong>
                                            {
                                                section.label
                                            }
                                        </strong>

                                        <small>
                                            {
                                                section.description
                                            }
                                        </small>
                                    </span>
                                </button>
                            )
                        )}
                    </aside>

                    <div className="settings-page-section-content">
                        {renderActiveSection()}
                    </div>
                </section>
            </main>

            <ChangePasswordModal
                open={passwordModalOpen}
                onClose={() => setPasswordModalOpen(false)}
                onPasswordChanged={endSecuritySession}
            />

            <TwoFactorSetupModal
                open={Boolean(twoFactorSetup)}
                setup={twoFactorSetup}
                onClose={() => setTwoFactorSetup(null)}
                onEnabled={handleTwoFactorEnabled}
            />

            <SmartImportModal
                open={smartImportOpen}
                isAdministrator={isSystemAdministrator}
                onClose={() => setSmartImportOpen(false)}
                onComplete={() =>
                    setSmartImportRefreshKey((current) => current + 1)
                }
            />

            <ImportHistoryModal
                open={importHistoryOpen}
                batch={selectedImportBatch}
                details={importHistoryDetails}
                loading={importDetailsLoading}
                error={importDetailsError}
                resultFilter={importDetailsFilter}
                onFilterChange={changeImportDetailsFilter}
                onClose={closeImportHistoryDetails}
            />
        </div>
    );
}

export default Settings;
