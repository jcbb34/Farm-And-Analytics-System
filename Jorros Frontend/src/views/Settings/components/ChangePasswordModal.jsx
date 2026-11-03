"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useState } from "react";
import { authService } from "../../../services/authService.js";
import { useAuth } from "../../../context/AuthContext.jsx";

// Change password form shown from Account Settings.
export default function ChangePasswordModal({
    open,
    onClose,
}) {
    const { logout } = useAuth();
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

    const handleSubmit = async (event) => {
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

        if (form.newPassword.length < 8) {
            notify(
                "The new password must contain at least eight characters."
            );
            return;
        }

        if (form.newPassword !== form.confirmPassword) {
            notify(
                "The new passwords do not match."
            );
            return;
        }

        if (form.currentPassword === form.newPassword) {
            notify(
                "The new password must be different from the current password."
            );
            return;
        }

        try {
            setSubmitting(true);
            await authService.changePassword({
                currentPassword: form.currentPassword,
                newPassword: form.newPassword,
            });

            notify(
                "Password changed successfully. Please sign in again with your new password."
            );
            onClose();
            await logout();
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
