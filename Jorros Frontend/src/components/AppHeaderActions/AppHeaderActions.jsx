"use client";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";
import { useRouter } from "next/navigation";

import { useAppHeader } from "../../context/AppHeaderContext.jsx";
import {
    confirmAction,
    notifyError,
    notifyInfo,
} from "../../context/NotificationContext.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { useTheme } from "../../context/ThemeContext.jsx";
import { useUnsavedChanges } from "../../context/UnsavedChangesContext.jsx";
import { isTaskOnlyUser } from "../../utils/accessControl.js";
import ThemeToggle from "../ThemeToggle/ThemeToggle.jsx";

import "./AppHeaderActions.css";

function getInitials(name = "") {
    const initials = name
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toUpperCase();

    return initials || "U";
}

function ProfileAvatar({ profile, large = false }) {
    const imageSource =
        profile.profileImage ||
        profile.avatarUrl ||
        profile.imageUrl ||
        "";

    return (
        <span
            className={`app-header-avatar ${
                large ? "large" : ""
            }`}
            aria-hidden="true"
        >
            {imageSource ? (
                <img
                    src={imageSource}
                    alt=""
                    className="app-header-avatar-image"
                />
            ) : (
                <span className="app-header-avatar-fallback">
                    {getInitials(profile.fullName)}
                </span>
            )}
        </span>
    );
}

function AppHeaderActions() {
    const router = useRouter();
    const { isDarkMode } = useTheme();
    const { user, hasPermission, logout } = useAuth();
    const {
        isDirty,
        confirmDiscard,
        requestNavigation,
    } = useUnsavedChanges();

    const {
        profile: storedProfile,
        notifications,
        unreadCount,
        markAsRead,
        markAllAsRead,
        removeNotification,
        moduleRoutes,
    } = useAppHeader();

    const taskOnlyMode = isTaskOnlyUser(user);

    const profile = useMemo(
        () => ({
            ...(storedProfile || {}),
            ...(user || {}),
        }),
        [storedProfile, user]
    );

    const [openMenu, setOpenMenu] = useState(null);
    const actionsRef = useRef(null);

    useEffect(() => {
        const handleOutsideClick = (event) => {
            if (
                actionsRef.current &&
                !actionsRef.current.contains(event.target)
            ) {
                setOpenMenu(null);
            }
        };

        const handleEscape = (event) => {
            if (event.key === "Escape") {
                setOpenMenu(null);
            }
        };

        const handleModalOpen = () => {
            setOpenMenu(null);
        };

        document.addEventListener(
            "mousedown",
            handleOutsideClick
        );
        document.addEventListener(
            "keydown",
            handleEscape
        );
        window.addEventListener(
            "joross:modal-open",
            handleModalOpen
        );

        return () => {
            document.removeEventListener(
                "mousedown",
                handleOutsideClick
            );
            document.removeEventListener(
                "keydown",
                handleEscape
            );
            window.removeEventListener(
                "joross:modal-open",
                handleModalOpen
            );
        };
    }, []);

    const toggleMenu = (menuName) => {
        setOpenMenu((currentMenu) =>
            currentMenu === menuName ? null : menuName
        );
    };

    const openNotification = async (notification) => {
        markAsRead(notification.id);
        setOpenMenu(null);

        const targetRoute =
            notification.route ||
            moduleRoutes[notification.module] ||
            "/dashboard";

        await requestNavigation(targetRoute, {
            state: {
                appNotification: notification,
                notificationClickId: `${notification.id}-${Date.now()}`,
            },
        });
    };

    const openSettings = async (focus) => {
        setOpenMenu(null);

        if (taskOnlyMode) {
            await requestNavigation("/profile");
            return;
        }

        await requestNavigation(
            `/settings?section=account&focus=${focus}`
        );
    };

    const openAlerts = async () => {
        setOpenMenu(null);
        await requestNavigation("/alerts");
    };

    const handleLogout = async () => {
        if (isDirty) {
            const discardConfirmed = await confirmDiscard(
                "Some form changes have not been saved. Leave them and continue logging out?"
            );

            if (!discardConfirmed) {
                return;
            }
        }

        const confirmed = await confirmAction({
            title: "Log Out",
            message:
                "Saved farm records and settings will be kept. Do you want to log out of Joross Farm?",
            type: "warning",
            confirmText: "Yes, Log Out",
            cancelText: "No, Stay",
        });

        if (!confirmed) {
            return;
        }

        setOpenMenu(null);
        const previousUser = encodeURIComponent(
            profile.fullName || user?.fullName || "User"
        );

        try {
            await logout();
        } catch (error) {
            notifyError(error?.message || "Unable to log out. Please try again.", "Logout Not Completed");
            return;
        }

        notifyInfo(
            "You have been logged out. Your saved changes were kept.",
            "Logged Out"
        );

        router.replace(
            `/login?loggedOut=1&previousUser=${previousUser}`
        );
    };

    return (
        <div
            className="app-header-actions"
            ref={actionsRef}
        >
            {hasPermission("notifications:view") && (
                <div className="app-header-notification-wrap">
                    <button
                        type="button"
                        className="app-header-notification-button"
                        aria-label="Open notifications"
                        aria-expanded={
                            openMenu === "notifications"
                        }
                        onClick={() =>
                            toggleMenu("notifications")
                        }
                    >
                        <span className="material-symbols-outlined">
                            notifications
                        </span>

                        {unreadCount > 0 && (
                            <span className="app-header-notification-dot">
                                {unreadCount > 9
                                    ? "9+"
                                    : unreadCount}
                            </span>
                        )}
                    </button>

                    <div
                        className={`app-header-notification-dropdown ${
                            openMenu === "notifications"
                                ? "show"
                                : ""
                        }`}
                    >
                        <div className="app-header-dropdown-heading">
                            <div>
                                <h3>Notifications</h3>
                                <p>
                                    {unreadCount > 0
                                        ? `${unreadCount} unread notification${
                                              unreadCount === 1
                                                  ? ""
                                                  : "s"
                                          }`
                                        : "You are all caught up"}
                                </p>
                            </div>

                            {unreadCount > 0 && (
                                <button
                                    type="button"
                                    onClick={markAllAsRead}
                                >
                                    Mark all as read
                                </button>
                            )}
                        </div>

                        <div className="app-header-notification-list">
                            {notifications.length > 0 ? (
                                notifications.map(
                                    (notification) => (
                                        <div
                                            className={`app-header-notification-row ${
                                                notification.unread
                                                    ? "unread"
                                                    : ""
                                            }`}
                                            key={notification.id}
                                        >
                                            <button
                                                type="button"
                                                className="app-header-notification-main"
                                                onClick={() =>
                                                    openNotification(
                                                        notification
                                                    )
                                                }
                                            >
                                                <span
                                                    className={`app-header-notification-icon ${
                                                        notification.tone ||
                                                        "info"
                                                    }`}
                                                >
                                                    <span className="material-symbols-outlined">
                                                        {notification.icon ||
                                                            "notifications"}
                                                    </span>
                                                </span>

                                                <span className="app-header-notification-copy">
                                                    <span className="app-header-notification-meta">
                                                        <strong>
                                                            {
                                                                notification.module
                                                            }
                                                        </strong>

                                                        <small>
                                                            {
                                                                notification.time
                                                            }
                                                        </small>
                                                    </span>

                                                    <b>
                                                        {
                                                            notification.title
                                                        }
                                                    </b>

                                                    <span>
                                                        {
                                                            notification.description
                                                        }
                                                    </span>
                                                </span>
                                            </button>

                                            <button
                                                type="button"
                                                className="app-header-notification-remove"
                                                aria-label={`Remove ${notification.title}`}
                                                onClick={() =>
                                                    removeNotification(
                                                        notification.id
                                                    )
                                                }
                                            >
                                                <span className="material-symbols-outlined">
                                                    close
                                                </span>
                                            </button>
                                        </div>
                                    )
                                )
                            ) : (
                                <div className="app-header-empty-notifications">
                                    <span className="material-symbols-outlined">
                                        notifications_off
                                    </span>

                                    <strong>
                                        No notifications
                                    </strong>

                                    <p>
                                        New farm updates will
                                        appear here.
                                    </p>
                                </div>
                            )}
                        </div>

                        {hasPermission("alerts:view") && (
                            <button
                                type="button"
                                className="app-header-view-alerts"
                                onClick={openAlerts}
                            >
                                View all farm alerts

                                <span className="material-symbols-outlined">
                                    arrow_forward
                                </span>
                            </button>
                        )}
                    </div>
                </div>
            )}

            <div className="app-header-profile-wrap">
                <div className="app-header-profile-button">
                    <ProfileAvatar profile={profile} />

                    <span className="app-header-profile-copy">
                        <strong>{profile.fullName}</strong>
                        <small>{profile.role}</small>
                    </span>

                    <button
                        type="button"
                        className={`app-header-profile-menu-button ${
                            openMenu === "profile" ? "open" : ""
                        }`}
                        aria-label={
                            openMenu === "profile"
                                ? "Close profile menu"
                                : "Open profile menu"
                        }
                        aria-expanded={openMenu === "profile"}
                        onClick={() => toggleMenu("profile")}
                    >
                        <span
                            className="app-header-menu-lines"
                            aria-hidden="true"
                        >
                            <span />
                            <span />
                            <span />
                        </span>
                    </button>
                </div>

                <div
                    className={`app-header-profile-dropdown ${
                        openMenu === "profile" ? "show" : ""
                    }`}
                >
                    <div className="app-header-profile-summary">
                        <ProfileAvatar
                            profile={profile}
                            large
                        />

                        <div>
                            <strong>{profile.fullName}</strong>
                            <span>{profile.role}</span>

                            {profile.email && (
                                <small>{profile.email}</small>
                            )}
                        </div>
                    </div>

                    <div className="app-header-profile-menu">
                        <button
                            type="button"
                            className="app-header-profile-action"
                            onClick={() =>
                                openSettings("profile")
                            }
                        >
                            <span className="material-symbols-outlined">
                                person
                            </span>

                            <span>
                                <strong>
                                    {taskOnlyMode ? "My Profile" : "Profile Settings"}
                                </strong>
                                <small>
                                    {taskOnlyMode
                                        ? "View your employee information"
                                        : "Edit your personal information"}
                                </small>
                            </span>
                        </button>

                        {!taskOnlyMode && (
                            <button
                                type="button"
                                className="app-header-profile-action"
                                onClick={() =>
                                    openSettings("security")
                                }
                            >
                                <span className="material-symbols-outlined">
                                    manage_accounts
                                </span>

                                <span>
                                    <strong>
                                        Account Settings
                                    </strong>
                                    <small>
                                        Password and account security
                                    </small>
                                </span>
                            </button>
                        )}

                        <div className="app-header-theme-row">
                            <span className="material-symbols-outlined app-header-theme-icon">
                                dark_mode
                            </span>

                            <span className="app-header-theme-copy">
                                <strong>Dark Mode</strong>
                                <small>
                                    {isDarkMode
                                        ? "Dark theme is currently enabled"
                                        : "Use a darker color theme"}
                                </small>
                            </span>

                            <ThemeToggle className="app-header-theme-toggle" />
                        </div>

                        <button
                            type="button"
                            className="app-header-profile-action app-header-logout-action"
                            onClick={handleLogout}
                        >
                            <span className="material-symbols-outlined">
                                logout
                            </span>

                            <span>
                                <strong>Log Out</strong>
                                <small>
                                    End this session on this device
                                </small>
                            </span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default AppHeaderActions;
