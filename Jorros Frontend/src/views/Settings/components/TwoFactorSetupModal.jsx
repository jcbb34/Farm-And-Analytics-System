"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useState } from "react";
import { authService } from "../../../services/authService.js";

// Authenticator setup and OTP verification.
export default function TwoFactorSetupModal({
    open,
    setup,
    onClose,
    onEnabled,
}) {
    const [otpCode, setOtpCode] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (open) {
            setOtpCode("");
        }
    }, [open]);

    if (!open || !setup) {
        return null;
    }

    const handleEnable = async (event) => {
        event.preventDefault();

        if (!/^\d{6}$/.test(otpCode.trim())) {
            notify(
                "Enter the 6-digit code from your authenticator app."
            );
            return;
        }

        try {
            setSubmitting(true);
            const result = await authService.enableTwoFactor(
                otpCode.trim()
            );
            onClose();
            await onEnabled?.(result);
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to enable two-factor authentication."
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
                className="settings-page-password-modal settings-page-2fa-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="settings-page-modal-header">
                    <div>
                        <h2>Set Up Authenticator</h2>
                        <p>
                            Scan this QR code with Google Authenticator,
                            Microsoft Authenticator, or another TOTP app.
                        </p>
                    </div>
                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close two-factor setup"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="settings-page-password-form"
                    onSubmit={handleEnable}
                >
                    <div className="settings-page-2fa-qr-wrap">
                        <img
                            src={setup.qr_code_data_url}
                            alt="Authenticator QR code"
                            className="settings-page-2fa-qr"
                        />
                    </div>

                    <div className="settings-page-form-group">
                        <label>Manual Setup Key</label>
                        <input
                            type="text"
                            value={setup.secret || ""}
                            readOnly
                            aria-readonly="true"
                        />
                        <small>
                            Use this key only if your authenticator cannot scan the QR code.
                        </small>
                    </div>

                    <div className="settings-page-form-group">
                        <label htmlFor="twoFactorOtpCode">
                            6-Digit Verification Code
                            <span>*</span>
                        </label>
                        <input
                            id="twoFactorOtpCode"
                            type="text"
                            inputMode="numeric"
                            maxLength="6"
                            value={otpCode}
                            onChange={(event) =>
                                setOtpCode(
                                    event.target.value.replace(/\D/g, "")
                                )
                            }
                            placeholder="000000"
                            autoComplete="one-time-code"
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
                                verified_user
                            </span>
                            {submitting ? "Verifying..." : "Verify and Enable"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}
