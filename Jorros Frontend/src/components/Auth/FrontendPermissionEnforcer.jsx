"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import { notifyWarning } from "../../context/NotificationContext.jsx";

const MUTATING_TERMS = [
    "add ",
    "create ",
    "edit",
    "update",
    "archive",
    "delete",
    "remove",
    "restore",
    "save",
    "adjust stock",
    "set stock",
    "complete task",
    "mark complete",
    "trigger test",
    "test alert",
    "generate report",
    "import data",
    "reset system",
    "create backup",
    "add role",
    "create user",
    "disable user",
    "enable user",
];

const SAFE_TERMS = [
    "view",
    "close",
    "cancel",
    "search",
    "filter",
    "clear",
    "export",
    "print",
    "download",
    "previous",
    "next",
    "dark mode",
    "light mode",
    "notification",
    "profile settings",
    "account settings",
    "logout",
];

const BUTTON_SELECTOR = "button, [role='button']";

function getButtonDescription(button) {
    return `${button.textContent || ""} ${
        button.title || ""
    } ${button.getAttribute("aria-label") || ""} ${
        button.className || ""
    }`.toLowerCase();
}

function isMutatingButton(button) {
    const description = getButtonDescription(button);

    if (
        SAFE_TERMS.some((term) =>
            description.includes(term)
        )
    ) {
        return false;
    }

    return MUTATING_TERMS.some((term) =>
        description.includes(term)
    );
}

function isAdministratorOnlyButton(button) {
    const description = getButtonDescription(button);

    return [
        "user management",
        "create user",
        "add role",
        "delete role",
        "reset system",
        "import data",
        "create backup",
    ].some((term) => description.includes(term));
}

function FrontendPermissionEnforcer({ children }) {
    const pathname = usePathname();
    const {
        user,
        isAdministrator,
        hasPermission,
    } = useAuth();

    useEffect(() => {
        const role = user?.role || "Unknown";
        const viewerMode = role === "Viewer";

        document.body.dataset.userRole = role;
        document.body.dataset.readOnly = viewerMode
            ? "true"
            : "false";

        const enforceButton = (button) => {
            if (!(button instanceof Element)) {
                return;
            }

            const explicitPermission =
                button.dataset.permission;

            let denied = false;

            if (explicitPermission) {
                denied = !hasPermission(
                    explicitPermission
                );
            } else if (
                viewerMode &&
                isMutatingButton(button)
            ) {
                denied = true;
            } else if (
                !isAdministrator &&
                pathname === "/settings" &&
                isAdministratorOnlyButton(button)
            ) {
                denied = true;
            }

            button.classList.toggle(
                "app-action-denied",
                denied
            );
            button.setAttribute(
                "aria-disabled",
                denied ? "true" : "false"
            );

            if (denied) {
                button.dataset.permissionDenied = "true";
            } else {
                delete button.dataset.permissionDenied;
            }
        };

        const enforceTree = (rootNode) => {
            if (!(rootNode instanceof Element)) {
                return;
            }

            if (rootNode.matches?.(BUTTON_SELECTOR)) {
                enforceButton(rootNode);
            }

            rootNode
                .querySelectorAll?.(BUTTON_SELECTOR)
                .forEach(enforceButton);
        };

        // One full pass when the role or route changes.
        document
            .querySelectorAll(BUTTON_SELECTOR)
            .forEach(enforceButton);

        // Afterwards, process only newly-added controls instead of rescanning
        // every button whenever any class changes anywhere on the page.
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (
                    mutation.type === "attributes" &&
                    mutation.target instanceof Element
                ) {
                    enforceButton(mutation.target);
                    return;
                }

                mutation.addedNodes.forEach((node) => {
                    enforceTree(node);
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["data-permission"],
        });

        const blockDeniedAction = (event) => {
            const button = event.target.closest?.(
                "[data-permission-denied='true']"
            );

            if (!button) {
                return;
            }

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation?.();

            notifyWarning(
                "Your account has view-only or limited access to this action.",
                "Permission Required"
            );
        };

        document.addEventListener(
            "click",
            blockDeniedAction,
            true
        );

        return () => {
            observer.disconnect();
            document.removeEventListener(
                "click",
                blockDeniedAction,
                true
            );
            delete document.body.dataset.userRole;
            delete document.body.dataset.readOnly;
        };
    }, [
        user?.role,
        isAdministrator,
        hasPermission,
        pathname,
    ]);

    return children;
}

export default FrontendPermissionEnforcer;
