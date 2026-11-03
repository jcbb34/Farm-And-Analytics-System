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
import { usePathname, useRouter } from "next/navigation";

import { confirmAction } from "./NotificationContext.jsx";

const UnsavedChangesContext = createContext(null);

function getFormSource(form) {
    return (
        form?.dataset?.dirtySource ||
        form?.id ||
        form?.className ||
        "active-form"
    );
}

function shouldIgnoreField(field) {
    const type = String(field?.type || "").toLowerCase();
    const placeholder = String(
        field?.placeholder || ""
    ).toLowerCase();
    const classNames = String(
        field?.className || ""
    ).toLowerCase();

    return (
        type === "search" ||
        placeholder.includes("search") ||
        classNames.includes("filter") ||
        Boolean(field?.closest?.("[data-ignore-dirty='true']"))
    );
}

export function UnsavedChangesProvider({ children }) {
    const router = useRouter();
    const pathname = usePathname();
    const dirtySourcesRef = useRef(new Set());
    const [dirtyVersion, setDirtyVersion] = useState(0);
    const bypassNextInteractionRef = useRef(false);

    const isDirty = dirtySourcesRef.current.size > 0;

    const refreshDirtyState = useCallback(() => {
        setDirtyVersion((version) => version + 1);
    }, []);

    const markDirty = useCallback(
        (source = "manual") => {
            dirtySourcesRef.current.add(String(source));
            refreshDirtyState();
        },
        [refreshDirtyState]
    );

    const markClean = useCallback(
        (source) => {
            if (source === undefined) {
                dirtySourcesRef.current.clear();
            } else {
                dirtySourcesRef.current.delete(
                    String(source)
                );
            }

            refreshDirtyState();
        },
        [refreshDirtyState]
    );

    const confirmDiscard = useCallback(
        async (
            message =
                "You have unsaved changes. Leave without saving them?"
        ) => {
            if (dirtySourcesRef.current.size === 0) {
                return true;
            }

            const confirmed = await confirmAction({
                title: "Unsaved Changes",
                message,
                type: "warning",
                confirmText: "Leave Without Saving",
                cancelText: "Stay Here",
            });

            if (confirmed) {
                dirtySourcesRef.current.clear();
                refreshDirtyState();
            }

            return confirmed;
        },
        [refreshDirtyState]
    );

    const requestNavigation = useCallback(
        async (to, options = {}) => {
            const confirmed = await confirmDiscard();

            if (!confirmed) {
                return false;
            }

            if (options.replace) {
                router.replace(to);
            } else {
                router.push(to);
            }

            return true;
        },
        [confirmDiscard, router]
    );

    useEffect(() => {
        const handleFieldChange = (event) => {
            const field = event.target;
            const form = field?.closest?.("form");

            if (!form || shouldIgnoreField(field)) {
                return;
            }

            markDirty(getFormSource(form));
        };

        const handleFormSubmit = (event) => {
            const source = getFormSource(event.target);

            window.setTimeout(() => {
                markClean(source);
            }, 0);
        };

        const handleBeforeUnload = (event) => {
            if (dirtySourcesRef.current.size === 0) {
                return;
            }

            event.preventDefault();
            event.returnValue = "";
        };

        const handleDocumentClick = async (event) => {
            if (bypassNextInteractionRef.current) {
                bypassNextInteractionRef.current = false;
                return;
            }

            if (dirtySourcesRef.current.size === 0) {
                return;
            }

            const link = event.target.closest?.("a[href]");

            if (link) {
                const url = new URL(link.href, window.location.href);
                const nextLocation = `${url.pathname}${url.search}${url.hash}`;
                const currentLocation = `${window.location.pathname}${window.location.search}${window.location.hash}`;

                if (
                    url.origin === window.location.origin &&
                    nextLocation !== currentLocation
                ) {
                    event.preventDefault();
                    event.stopPropagation();
                    await requestNavigation(nextLocation);
                }

                return;
            }

            const button = event.target.closest?.("button");

            if (!button) {
                return;
            }

            const buttonLabel = `${button.textContent || ""} ${
                button.getAttribute("aria-label") || ""
            } ${button.className || ""}`.toLowerCase();

            const isCloseOrCancel =
                buttonLabel.includes("close") ||
                buttonLabel.includes("cancel");

            if (
                !isCloseOrCancel ||
                !button.closest(
                    "form, [class*='modal'], [role='dialog']"
                )
            ) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();

            const confirmed = await confirmDiscard(
                "This form has unsaved changes. Close it without saving?"
            );

            if (confirmed) {
                bypassNextInteractionRef.current = true;
                button.click();
            }
        };

        document.addEventListener(
            "input",
            handleFieldChange,
            true
        );
        document.addEventListener(
            "change",
            handleFieldChange,
            true
        );
        document.addEventListener(
            "submit",
            handleFormSubmit,
            true
        );
        document.addEventListener(
            "click",
            handleDocumentClick,
            true
        );
        window.addEventListener(
            "beforeunload",
            handleBeforeUnload
        );

        return () => {
            document.removeEventListener(
                "input",
                handleFieldChange,
                true
            );
            document.removeEventListener(
                "change",
                handleFieldChange,
                true
            );
            document.removeEventListener(
                "submit",
                handleFormSubmit,
                true
            );
            document.removeEventListener(
                "click",
                handleDocumentClick,
                true
            );
            window.removeEventListener(
                "beforeunload",
                handleBeforeUnload
            );
        };
    }, [
        pathname,
        markClean,
        markDirty,
        confirmDiscard,
        requestNavigation,
    ]);

    const value = useMemo(
        () => ({
            isDirty,
            dirtyCount: dirtySourcesRef.current.size,
            dirtyVersion,
            markDirty,
            markClean,
            confirmDiscard,
            requestNavigation,
        }),
        [
            isDirty,
            dirtyVersion,
            markDirty,
            markClean,
            confirmDiscard,
            requestNavigation,
        ]
    );

    return (
        <UnsavedChangesContext.Provider value={value}>
            {children}
        </UnsavedChangesContext.Provider>
    );
}

export function useUnsavedChanges() {
    const context = useContext(UnsavedChangesContext);

    if (!context) {
        throw new Error(
            "useUnsavedChanges must be used inside UnsavedChangesProvider."
        );
    }

    return context;
}
