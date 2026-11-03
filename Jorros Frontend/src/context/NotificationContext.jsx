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
import { createPortal } from "react-dom";

import "../components/AppNotification/AppNotification.css";

const NotificationContext = createContext(null);

let toastDispatcher = null;
let confirmDispatcher = null;
let promptDispatcher = null;

const pendingToasts = [];

function createId() {
    return `${Date.now()}-${Math.random()
        .toString(16)
        .slice(2)}`;
}

function normalizeMessage(message) {
    if (message instanceof Error) {
        return message.message;
    }

    if (
        typeof message === "object" &&
        message !== null
    ) {
        try {
            return JSON.stringify(message);
        } catch {
            return String(message);
        }
    }

    return String(message ?? "");
}

function detectNotificationType(message) {
    const normalizedMessage =
        normalizeMessage(message).toLowerCase();

    const errorWords = [
        "error",
        "failed",
        "invalid",
        "not found",
        "cannot",
        "can't",
        "must",
        "required",
        "does not",
        "do not match",
        "earlier than",
    ];

    const warningWords = [
        "please complete",
        "please enter",
        "no report",
        "no records",
        "already exists",
        "low stock",
        "out of stock",
        "attention",
    ];

    const successWords = [
        "success",
        "successfully",
        "saved",
        "updated",
        "added",
        "created",
        "generated",
        "exported",
        "imported",
        "restored",
        "enabled",
        "disabled",
        "completed",
    ];

    if (
        errorWords.some((word) =>
            normalizedMessage.includes(word)
        )
    ) {
        return "error";
    }

    if (
        warningWords.some((word) =>
            normalizedMessage.includes(word)
        )
    ) {
        return "warning";
    }

    if (
        successWords.some((word) =>
            normalizedMessage.includes(word)
        )
    ) {
        return "success";
    }

    return "info";
}

function getDefaultTitle(type) {
    const titles = {
        success: "Success",
        error: "Unable to Continue",
        warning: "Please Check",
        info: "Notification",
    };

    return titles[type] || titles.info;
}

export function showNotification({
    type = "info",
    title,
    message = "",
    duration = 3500,
} = {}) {
    const normalizedMessage =
        normalizeMessage(message);

    const notification = {
        id: createId(),
        type,
        title:
            title ||
            getDefaultTitle(type),
        message:
            normalizedMessage,
        duration,
    };

    if (toastDispatcher) {
        toastDispatcher(notification);
    } else {
        pendingToasts.push(
            notification
        );
    }

    return notification.id;
}

export function notifySuccess(
    message,
    title = "Success"
) {
    return showNotification({
        type: "success",
        title,
        message,
    });
}

export function notifyError(
    message,
    title = "Unable to Continue"
) {
    return showNotification({
        type: "error",
        title,
        message,
        duration: 4500,
    });
}

export function notifyWarning(
    message,
    title = "Please Check"
) {
    return showNotification({
        type: "warning",
        title,
        message,
        duration: 4200,
    });
}

export function notifyInfo(
    message,
    title = "Notification"
) {
    return showNotification({
        type: "info",
        title,
        message,
    });
}

export function notify(message) {
    const type = detectNotificationType(message);
    return showNotification({
        type,
        title: getDefaultTitle(type),
        message: normalizeMessage(message),
    });
}

export function confirmAction({
    title = "Confirm Action",
    message =
        "Are you sure you want to continue?",
    type = "warning",
    confirmText = "Confirm",
    cancelText = "Cancel",
} = {}) {
    if (!confirmDispatcher) {
        return Promise.resolve(
            window.confirm(message)
        );
    }

    return confirmDispatcher({
        title,
        message,
        type,
        confirmText,
        cancelText,
    });
}

export function promptAction({
    title = "Enter Information",
    message = "",
    label = "Value",
    placeholder = "",
    initialValue = "",
    confirmText = "Continue",
    cancelText = "Cancel",
    required = false,
    inputType = "text",
} = {}) {
    if (!promptDispatcher) {
        return Promise.resolve(
            window.prompt(
                message || label,
                initialValue
            )
        );
    }

    return promptDispatcher({
        title,
        message,
        label,
        placeholder,
        initialValue,
        confirmText,
        cancelText,
        required,
        inputType,
    });
}

function getNotificationIcon(type) {
    const icons = {
        success: "check_circle",
        error: "error",
        warning: "warning",
        info: "info",
    };

    return icons[type] || icons.info;
}

export function NotificationProvider({
    children,
}) {
    const [
        notifications,
        setNotifications,
    ] = useState([]);

    const [
        confirmDialog,
        setConfirmDialog,
    ] = useState(null);

    const [
        promptDialog,
        setPromptDialog,
    ] = useState(null);

    const [
        promptValue,
        setPromptValue,
    ] = useState("");

    const [
        overlayPortalReady,
        setOverlayPortalReady,
    ] = useState(false);

    useEffect(() => {
        setOverlayPortalReady(true);
    }, []);

    const timersRef = useRef(
        new Map()
    );

    const promptInputRef =
        useRef(null);

    const removeNotification =
        useCallback((id) => {
            setNotifications(
                (currentNotifications) =>
                    currentNotifications.filter(
                        (notification) =>
                            notification.id !== id
                    )
            );

            const timer =
                timersRef.current.get(id);

            if (timer) {
                clearTimeout(timer);
                timersRef.current.delete(
                    id
                );
            }
        }, []);

    const addNotification =
        useCallback(
            (notification) => {
                setNotifications(
                    (currentNotifications) => [
                        ...currentNotifications.slice(
                            -4
                        ),
                        notification,
                    ]
                );

                if (
                    ["warning", "error", "info"].includes(
                        notification.type
                    )
                ) {
                    window.dispatchEvent(
                        new CustomEvent("joross:header-notification", {
                            detail: {
                                module: "System",
                                title: notification.title,
                                description: notification.message,
                                icon:
                                    notification.type === "error"
                                        ? "error"
                                        : notification.type === "warning"
                                        ? "warning"
                                        : "info",
                                tone: notification.type,
                                route: "/alerts",
                            },
                        })
                    );
                }

                if (
                    notification.duration >
                    0
                ) {
                    const timer =
                        window.setTimeout(
                            () => {
                                removeNotification(
                                    notification.id
                                );
                            },
                            notification.duration
                        );

                    timersRef.current.set(
                        notification.id,
                        timer
                    );
                }
            },
            [removeNotification]
        );

    const openConfirm =
        useCallback((options) => {
            return new Promise(
                (resolve) => {
                    setConfirmDialog({
                        ...options,
                        resolve,
                    });
                }
            );
        }, []);

    const closeConfirm =
        useCallback((result) => {
            setConfirmDialog(
                (currentDialog) => {
                    currentDialog?.resolve(
                        result
                    );

                    return null;
                }
            );
        }, []);

    const openPrompt =
        useCallback((options) => {
            return new Promise(
                (resolve) => {
                    setPromptValue(
                        String(
                            options.initialValue ??
                                ""
                        )
                    );

                    setPromptDialog({
                        ...options,
                        resolve,
                    });
                }
            );
        }, []);

    const closePrompt =
        useCallback((result) => {
            setPromptDialog(
                (currentDialog) => {
                    currentDialog?.resolve(
                        result
                    );

                    return null;
                }
            );
        }, []);

    useEffect(() => {
        toastDispatcher =
            addNotification;

        confirmDispatcher =
            openConfirm;

        promptDispatcher =
            openPrompt;

        pendingToasts
            .splice(0)
            .forEach(
                addNotification
            );

        return () => {
            if (
                toastDispatcher ===
                addNotification
            ) {
                toastDispatcher =
                    null;
            }

            if (
                confirmDispatcher ===
                openConfirm
            ) {
                confirmDispatcher =
                    null;
            }

            if (
                promptDispatcher ===
                openPrompt
            ) {
                promptDispatcher =
                    null;
            }
        };
    }, [
        addNotification,
        openConfirm,
        openPrompt,
    ]);

    useEffect(() => {
        return () => {
            timersRef.current.forEach(
                (timer) =>
                    clearTimeout(
                        timer
                    )
            );

            timersRef.current.clear();
        };
    }, []);

    useEffect(() => {
        const dialogIsOpen =
            Boolean(
                confirmDialog ||
                    promptDialog
            );

        if (!dialogIsOpen) {
            return undefined;
        }

        const previousOverflow =
            document.body.style
                .overflow;

        document.body.style.overflow =
            "hidden";

        const handleKeyDown = (
            event
        ) => {
            if (
                event.key === "Escape"
            ) {
                if (promptDialog) {
                    closePrompt(null);
                } else {
                    closeConfirm(false);
                }
            }

            if (
                event.key ===
                    "Enter" &&
                promptDialog &&
                document.activeElement ===
                    promptInputRef.current
            ) {
                event.preventDefault();

                const cleanedValue =
                    promptValue.trim();

                if (
                    promptDialog.required &&
                    !cleanedValue
                ) {
                    notifyWarning(
                        `${promptDialog.label} is required.`
                    );

                    return;
                }

                closePrompt(
                    cleanedValue
                );
            }
        };

        document.addEventListener(
            "keydown",
            handleKeyDown
        );

        return () => {
            document.body.style.overflow =
                previousOverflow;

            document.removeEventListener(
                "keydown",
                handleKeyDown
            );
        };
    }, [
        closeConfirm,
        closePrompt,
        confirmDialog,
        promptDialog,
        promptValue,
    ]);

    useEffect(() => {
        if (
            promptDialog &&
            promptInputRef.current
        ) {
            window.setTimeout(
                () => {
                    promptInputRef.current?.focus();
                    promptInputRef.current?.select();
                },
                0
            );
        }
    }, [promptDialog]);

    const contextValue =
        useMemo(
            () => ({
                showNotification,
                success:
                    notifySuccess,
                error: notifyError,
                warning:
                    notifyWarning,
                info: notifyInfo,
                confirm:
                    confirmAction,
                prompt: promptAction,
            }),
            []
        );

    const handlePromptSubmit = (
        event
    ) => {
        event.preventDefault();

        const cleanedValue =
            promptValue.trim();

        if (
            promptDialog?.required &&
            !cleanedValue
        ) {
            notifyWarning(
                `${promptDialog.label} is required.`
            );

            return;
        }

        closePrompt(cleanedValue);
    };

    return (
        <NotificationContext.Provider
            value={contextValue}
        >
            {children}

            {overlayPortalReady && createPortal(
                <>
            <div
                    className="app-toast-stack"
                    aria-live="polite"
                    aria-atomic="false"
                >
                    {notifications.map(
                        (notification) => (
                            <article
                                key={
                                    notification.id
                                }
                                className={`app-toast app-toast-${notification.type}`}
                            >
                                <span className="app-toast-icon">
                                    <span className="material-symbols-outlined">
                                        {getNotificationIcon(
                                            notification.type
                                        )}
                                    </span>
                                </span>
    
                                <div className="app-toast-content">
                                    <strong>
                                        {
                                            notification.title
                                        }
                                    </strong>
    
                                    <p>
                                        {
                                            notification.message
                                        }
                                    </p>
                                </div>
    
                                <button
                                    type="button"
                                    className="app-toast-close"
                                    aria-label="Close notification"
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
    
                                <span className="app-toast-progress" />
                            </article>
                        )
                    )}
                </div>
    
                {confirmDialog && (
                    <div
                        className="app-dialog-overlay"
                        onMouseDown={() =>
                            closeConfirm(false)
                        }
                    >
                        <section
                            className="app-dialog"
                            role="alertdialog"
                            aria-modal="true"
                            aria-labelledby="app-confirm-title"
                            aria-describedby="app-confirm-message"
                            onMouseDown={(
                                event
                            ) =>
                                event.stopPropagation()
                            }
                        >
                            <div className="app-dialog-body">
                                <span
                                    className={`app-dialog-icon app-dialog-icon-${confirmDialog.type}`}
                                >
                                    <span className="material-symbols-outlined">
                                        {getNotificationIcon(
                                            confirmDialog.type
                                        )}
                                    </span>
                                </span>
    
                                <div className="app-dialog-copy">
                                    <h2 id="app-confirm-title">
                                        {
                                            confirmDialog.title
                                        }
                                    </h2>
    
                                    <p id="app-confirm-message">
                                        {
                                            confirmDialog.message
                                        }
                                    </p>
                                </div>
                            </div>
    
                            <footer className="app-dialog-actions">
                                <button
                                    type="button"
                                    className="app-dialog-cancel"
                                    onClick={() =>
                                        closeConfirm(
                                            false
                                        )
                                    }
                                >
                                    {
                                        confirmDialog.cancelText
                                    }
                                </button>
    
                                <button
                                    type="button"
                                    autoFocus
                                    className={`app-dialog-confirm app-dialog-confirm-${confirmDialog.type}`}
                                    onClick={() =>
                                        closeConfirm(
                                            true
                                        )
                                    }
                                >
                                    {
                                        confirmDialog.confirmText
                                    }
                                </button>
                            </footer>
                        </section>
                    </div>
                )}
    
                {promptDialog && (
                    <div
                        className="app-dialog-overlay"
                        onMouseDown={() =>
                            closePrompt(null)
                        }
                    >
                        <form
                            className="app-dialog app-prompt-dialog"
                            role="dialog"
                            aria-modal="true"
                            aria-labelledby="app-prompt-title"
                            onSubmit={
                                handlePromptSubmit
                            }
                            onMouseDown={(
                                event
                            ) =>
                                event.stopPropagation()
                            }
                        >
                            <div className="app-dialog-body">
                                <span className="app-dialog-icon app-dialog-icon-info">
                                    <span className="material-symbols-outlined">
                                        edit_note
                                    </span>
                                </span>
    
                                <div className="app-dialog-copy">
                                    <h2 id="app-prompt-title">
                                        {
                                            promptDialog.title
                                        }
                                    </h2>
    
                                    {promptDialog.message && (
                                        <p>
                                            {
                                                promptDialog.message
                                            }
                                        </p>
                                    )}
                                </div>
                            </div>
    
                            <div className="app-prompt-field">
                                <label htmlFor="app-prompt-input">
                                    {
                                        promptDialog.label
                                    }
                                    {promptDialog.required && (
                                        <span>
                                            *
                                        </span>
                                    )}
                                </label>
    
                                <input
                                    ref={
                                        promptInputRef
                                    }
                                    id="app-prompt-input"
                                    type={promptDialog.inputType || "text"}
                                    value={
                                        promptValue
                                    }
                                    placeholder={
                                        promptDialog.placeholder
                                    }
                                    onChange={(
                                        event
                                    ) =>
                                        setPromptValue(
                                            event
                                                .target
                                                .value
                                        )
                                    }
                                />
                            </div>
    
                            <footer className="app-dialog-actions">
                                <button
                                    type="button"
                                    className="app-dialog-cancel"
                                    onClick={() =>
                                        closePrompt(
                                            null
                                        )
                                    }
                                >
                                    {
                                        promptDialog.cancelText
                                    }
                                </button>
    
                                <button
                                    type="submit"
                                    className="app-dialog-confirm app-dialog-confirm-info"
                                >
                                    {
                                        promptDialog.confirmText
                                    }
                                </button>
                            </footer>
                        </form>
                    </div>
                )}
    
                </>,
                document.body
            )}
        </NotificationContext.Provider>
    );
}

export function useNotification() {
    const context =
        useContext(
            NotificationContext
        );

    if (!context) {
        throw new Error(
            "useNotification must be used inside NotificationProvider."
        );
    }

    return context;
}
