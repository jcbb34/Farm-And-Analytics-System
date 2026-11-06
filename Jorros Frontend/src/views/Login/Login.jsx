"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "../../context/AuthContext.jsx";
import { useNotification } from "../../context/NotificationContext.jsx";
import { storageKeys } from "../../config/appConfig.js";
import {
    resolvePostAuthDestination,
    sanitizeRequestedDestination,
} from "../../utils/accessControl.js";
import {
    SHARED_DEVICE_LANGUAGE_KEY,
    SHARED_DEVICE_TRANSLATIONS,
    normalizeSharedLanguage,
} from "../MyTasks/sharedDeviceMode.js";

import "./Login.css";


function Login() {
    const router = useRouter();
    const { login, isLoading: authIsLoading, authError } = useAuth();
    const {
        success,
        error: showErrorNotification,
    } = useNotification();

    const [form, setForm] = useState({
        username: "",
        password: "",
    });
    const [showPassword, setShowPassword] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [formError, setFormError] = useState("");
    const [sharedLogin, setSharedLogin] = useState(false);
    const [sharedLocked, setSharedLocked] = useState(false);
    const [sharedLanguage, setSharedLanguage] = useState("en");

    useEffect(() => {
        const params = new URLSearchParams(window.location.search);
        const requested = params.get("from") || "";
        let requestedShared = params.get("shared") === "1";
        try {
            const requestedUrl = new URL(requested || "/", window.location.origin);
            requestedShared = requestedShared || requestedUrl.searchParams.get("shared") === "1";
        } catch {}
        setSharedLogin(requestedShared);
        setSharedLocked(params.get("locked") === "1");
        if (params.get("releasePending") === "1") {
            setFormError(
                "This device was locked, but the server could not confirm logout. If sign-in says the account is in use, wait for the previous session to expire."
            );
        }
        try {
            setSharedLanguage(normalizeSharedLanguage(localStorage.getItem(SHARED_DEVICE_LANGUAGE_KEY)));
        } catch {
            setSharedLanguage("en");
        }
    }, []);

    const sharedText = SHARED_DEVICE_TRANSLATIONS[sharedLanguage];
    const setLoginLanguage = (value) => {
        const normalized = normalizeSharedLanguage(value);
        setSharedLanguage(normalized);
        try { localStorage.setItem(SHARED_DEVICE_LANGUAGE_KEY, normalized); } catch {}
    };

    const handleChange = (event) => {
        const { name, value } = event.target;

        setForm((currentForm) => ({
            ...currentForm,
            [name]: value,
        }));

        if (formError) {
            setFormError("");
        }
    };

    const completeLogin = (session) => {
        const params = new URLSearchParams(window.location.search);
        const requested = params.get("from");
        const requestedDestination = sanitizeRequestedDestination(requested);
        const destination = resolvePostAuthDestination(
            session?.user,
            requestedDestination
        );

        try { sessionStorage.removeItem(storageKeys.twoFactorChallenge); } catch {}

        success(
            `Welcome back, ${session?.user?.fullName || "Administrator"}.`,
            "Login Successful"
        );

        router.replace(destination);
    };

    const beginTwoFactorVerification = (result) => {
        const params = new URLSearchParams(window.location.search);
        const requested = params.get("from");
        const destination = sanitizeRequestedDestination(requested);
        const expiresInSeconds = Number(result?.challengeExpiresIn || 300);

        const pendingChallenge = {
            challengeToken: result.challengeToken,
            username: result.username || form.username.trim(),
            expiresAt: Date.now() + Math.max(30, expiresInSeconds) * 1000,
            destination,
            sharedDevice: sharedLogin,
        };

        try {
            sessionStorage.setItem(
                storageKeys.twoFactorChallenge,
                JSON.stringify(pendingChallenge)
            );
        } catch {
            const message = "This browser is blocking temporary session storage. Allow site data for this local address and try again.";
            setFormError(message);
            showErrorNotification(message, "Login Failed");
            return;
        }

        router.push(
            destination
                ? `/verify-2fa?from=${encodeURIComponent(destination)}`
                : "/verify-2fa"
        );
    };

    const handleSubmit = async (event) => {
        event.preventDefault();

        const username = form.username.trim();
        const password = form.password;

        if (!username || !password) {
            const message = "Please enter your username and password.";
            setFormError(message);
            showErrorNotification(message, "Login Failed");
            return;
        }

        setIsSubmitting(true);
        setFormError("");

        try {
            const result = await login({
                username,
                password,
                sharedDevice: sharedLogin,
            });

            if (result?.requiresTwoFactor) {
                beginTwoFactorVerification(result);
                return;
            }

            completeLogin(result);
        } catch (loginError) {
            const message =
                loginError?.message ||
                "Unable to sign in. Please check your account and try again.";

            setFormError(message);
            showErrorNotification(message, "Login Failed");
        } finally {
            setIsSubmitting(false);
        }
    };

    const buttonIsDisabled = isSubmitting || authIsLoading;

    return (
        <main className="login-page">
            <section className="login-container">
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
                    {sharedLogin && <div className="login-shared-device-banner" role="status">
                        <div className="login-shared-device-copy">
                            <span className="material-symbols-outlined" aria-hidden="true">tablet_mac</span>
                            <div><strong>{sharedText.signInTitle}</strong><span>{sharedLocked ? sharedText.lockedMessage : sharedText.signInHelp}</span></div>
                        </div>
                        <div className="login-shared-language" role="group" aria-label="Language / Wika">
                            <button type="button" className={sharedLanguage === "en" ? "active" : ""} onClick={() => setLoginLanguage("en")}>English</button>
                            <button type="button" className={sharedLanguage === "fil" ? "active" : ""} onClick={() => setLoginLanguage("fil")}>Filipino</button>
                        </div>
                    </div>}

                    <div className="login-form-heading">
                        <h2>{sharedLogin ? sharedText.signInTitle : "Welcome Back"}</h2>
                        <p>{sharedLogin ? sharedText.signInHelp : "Sign in to continue to Joross Farm."}</p>
                    </div>

                    <div className="login-form-group">
                        <label htmlFor="loginUsername">{sharedLogin ? sharedText.username : "User Account"}</label>

                        <div className="login-input-wrapper">
                            <span className="material-symbols-outlined">
                                person
                            </span>

                            <input
                                id="loginUsername"
                                name="username"
                                type="text"
                                value={form.username}
                                onChange={handleChange}
                                placeholder="Enter your username"
                                autoComplete="username"
                                disabled={buttonIsDisabled}
                                required
                            />
                        </div>
                    </div>

                    <div className="login-form-group">
                        <label htmlFor="loginPassword">{sharedLogin ? sharedText.password : "Password"}</label>

                        <div className="login-input-wrapper">
                            <span className="material-symbols-outlined">
                                lock
                            </span>

                            <input
                                id="loginPassword"
                                name="password"
                                type={showPassword ? "text" : "password"}
                                value={form.password}
                                onChange={handleChange}
                                placeholder="Enter your password"
                                autoComplete="current-password"
                                disabled={buttonIsDisabled}
                                required
                            />

                            <button
                                type="button"
                                className="login-password-toggle"
                                onClick={() =>
                                    setShowPassword((currentValue) => !currentValue)
                                }
                                aria-label={
                                    showPassword
                                        ? "Hide password"
                                        : "Show password"
                                }
                                disabled={buttonIsDisabled}
                            >
                                <span className="material-symbols-outlined">
                                    {showPassword
                                        ? "visibility_off"
                                        : "visibility"}
                                </span>
                            </button>
                        </div>
                    </div>

                    {(formError || authError) && (
                        <div
                            className="login-error-message"
                            role="alert"
                            aria-live="polite"
                        >
                            <span className="material-symbols-outlined">
                                error
                            </span>
                            <p>{formError || authError}</p>
                        </div>
                    )}

                    <button
                        type="submit"
                        className="login-button"
                        disabled={buttonIsDisabled}
                    >
                        {buttonIsDisabled ? (
                            <>
                                <span className="login-button-spinner" />
                                Signing In...
                            </>
                        ) : (
                            <>
                                <span className="material-symbols-outlined">
                                    login
                                </span>
                                {sharedLogin ? sharedText.signIn : "Login"}
                            </>
                        )}
                    </button>
                </form>
            </section>
        </main>
    );
}

export default Login;
