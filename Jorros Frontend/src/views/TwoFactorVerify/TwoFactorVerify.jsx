"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import { useNotification } from "../../context/NotificationContext.jsx";
import { storageKeys } from "../../config/appConfig.js";
import {
    resolvePostAuthDestination,
    sanitizeRequestedDestination,
} from "../../utils/accessControl.js";

import "../Login/Login.css";
import "./TwoFactorVerify.css";


function readPendingChallenge() {
    try {
        return JSON.parse(
            sessionStorage.getItem(storageKeys.twoFactorChallenge) || "null"
        );
    } catch {
        return null;
    }
}

function TwoFactorVerify() {
    const router = useRouter();
    const { verifyTwoFactorLogin, isLoading: authIsLoading } = useAuth();
    const {
        success,
        error: showErrorNotification,
    } = useNotification();

    const [challenge, setChallenge] = useState(null);
    const [otpCode, setOtpCode] = useState("");
    const [formError, setFormError] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [secondsRemaining, setSecondsRemaining] = useState(0);
    const otpInputRef = useRef(null);

    const destination = sanitizeRequestedDestination(
        challenge?.destination
    );

    useEffect(() => {
        const pending = readPendingChallenge();

        if (
            !pending?.challengeToken ||
            !pending?.expiresAt ||
            Number(pending.expiresAt) <= Date.now()
        ) {
            sessionStorage.removeItem(storageKeys.twoFactorChallenge);
            const params = new URLSearchParams(window.location.search);
            const backTo = sanitizeRequestedDestination(params.get("from"));
            router.replace(
                backTo
                    ? `/login?from=${encodeURIComponent(backTo)}&twoFactorExpired=1`
                    : "/login?twoFactorExpired=1"
            );
            return;
        }

        setChallenge(pending);

        window.setTimeout(() => {
            otpInputRef.current?.focus();
        }, 80);
    }, [router]);

    useEffect(() => {
        if (!challenge?.expiresAt) {
            return undefined;
        }

        const updateRemainingTime = () => {
            const remaining = Math.max(
                0,
                Math.ceil((Number(challenge.expiresAt) - Date.now()) / 1000)
            );

            setSecondsRemaining(remaining);

            if (remaining === 0) {
                sessionStorage.removeItem(storageKeys.twoFactorChallenge);
            }
        };

        updateRemainingTime();
        const timer = window.setInterval(updateRemainingTime, 1000);

        return () => window.clearInterval(timer);
    }, [challenge?.expiresAt]);

    const handleCodeChange = (event) => {
        setOtpCode(event.target.value.replace(/\D/g, "").slice(0, 6));

        if (formError) {
            setFormError("");
        }
    };

    const goBackToLogin = () => {
        sessionStorage.removeItem(storageKeys.twoFactorChallenge);
        router.replace(
            destination
                ? `/login?from=${encodeURIComponent(destination)}`
                : "/login"
        );
    };

    const handleSubmit = async (event) => {
        event.preventDefault();

        if (!challenge?.challengeToken) {
            setFormError(
                "Your verification session is missing. Return to login and enter your username and password again."
            );
            return;
        }

        if (secondsRemaining <= 0) {
            setFormError(
                "Your verification session expired. Return to login and sign in again."
            );
            return;
        }

        if (!/^\d{6}$/.test(otpCode)) {
            setFormError(
                "Enter the current 6-digit code shown in Microsoft Authenticator."
            );
            return;
        }

        setIsSubmitting(true);
        setFormError("");

        try {
            const session = await verifyTwoFactorLogin({
                challengeToken: challenge.challengeToken,
                otpCode,
                sharedDevice: Boolean(challenge.sharedDevice),
            });

            sessionStorage.removeItem(storageKeys.twoFactorChallenge);

            success(
                `Welcome back, ${session?.user?.fullName || challenge.username || "Administrator"}.`,
                "Login Successful"
            );

            const finalDestination = resolvePostAuthDestination(
                session?.user,
                destination
            );
            router.replace(finalDestination);
        } catch (verificationError) {
            const message =
                verificationError?.message ||
                "Unable to verify the authentication code.";

            setOtpCode("");
            setFormError(message);
            otpInputRef.current?.focus();

            if (
                /verification session expired|return to login/i.test(message)
            ) {
                sessionStorage.removeItem(storageKeys.twoFactorChallenge);
            }

            showErrorNotification(message, "Verification Failed");
        } finally {
            setIsSubmitting(false);
        }
    };

    const buttonIsDisabled =
        isSubmitting || authIsLoading || !challenge || secondsRemaining <= 0;

    return (
        <main className="login-page">
            <section className="login-container two-factor-container">
                <div className="login-brand">
                    <img
                        src="/images/Jorros Logo 1.png"
                        alt="JoRoss Farm logo"
                        className="login-logo"
                    />
                    <p>Farm Analytics and Production Monitoring System</p>
                </div>

                <div className="login-divider" />

                <form
                    className="login-form"
                    onSubmit={handleSubmit}
                    noValidate
                >
                    <div className="two-factor-title-row">
                        <span className="material-symbols-outlined two-factor-shield">
                            verified_user
                        </span>

                        <div className="login-form-heading two-factor-heading">
                            <h2>Two-Factor Authentication</h2>
                            <p>
                                Open Microsoft Authenticator and enter the current 6-digit code for JoRoss Farm.
                            </p>
                        </div>
                    </div>

                    {challenge?.username && (
                        <div className="two-factor-account">
                            <span className="material-symbols-outlined">
                                person
                            </span>
                            <span>
                                Verifying <strong>{challenge.username}</strong>
                            </span>
                        </div>
                    )}

                    <div className="login-form-group">
                        <label htmlFor="twoFactorOtpCode">
                            Authenticator Code
                        </label>

                        <div className="login-input-wrapper two-factor-code-wrapper">
                            <span className="material-symbols-outlined">
                                pin
                            </span>

                            <input
                                ref={otpInputRef}
                                id="twoFactorOtpCode"
                                name="otpCode"
                                type="text"
                                inputMode="numeric"
                                pattern="[0-9]*"
                                maxLength="6"
                                value={otpCode}
                                onChange={handleCodeChange}
                                placeholder="000000"
                                autoComplete="one-time-code"
                                disabled={buttonIsDisabled}
                                required
                            />
                        </div>

                        <div className="two-factor-help-row">
                            <span>
                                Use the newest code shown in Microsoft Authenticator.
                            </span>
                            {secondsRemaining > 0 && (
                                <strong>
                                    Login session: {Math.floor(secondsRemaining / 60)}:
                                    {String(secondsRemaining % 60).padStart(2, "0")}
                                </strong>
                            )}
                        </div>
                    </div>

                    {formError && (
                        <div
                            className="login-error-message"
                            role="alert"
                            aria-live="polite"
                        >
                            <span className="material-symbols-outlined">
                                error
                            </span>
                            <p>{formError}</p>
                        </div>
                    )}

                    <button
                        type="submit"
                        className="login-button"
                        disabled={buttonIsDisabled}
                    >
                        {buttonIsDisabled && isSubmitting ? (
                            <>
                                <span className="login-button-spinner" />
                                Verifying...
                            </>
                        ) : (
                            <>
                                <span className="material-symbols-outlined">
                                    verified_user
                                </span>
                                Verify &amp; Sign In
                            </>
                        )}
                    </button>

                    <button
                        type="button"
                        className="two-factor-back-button"
                        onClick={goBackToLogin}
                        disabled={isSubmitting || authIsLoading}
                    >
                        <span className="material-symbols-outlined">
                            arrow_back
                        </span>
                        Back to Login
                    </button>
                </form>
            </section>
        </main>
    );
}

export default TwoFactorVerify;
