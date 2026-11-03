"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useRef, useState } from "react";

import { authService } from "../../../services/authService.js";
import { promptAction } from "../../../context/NotificationContext.jsx";

const initialProfile = {
    fullName: "Juan Dela Cruz",
    username: "admin",
    email: "admin@example.com",
    contactNumber: "09123456789",
    position: "Farm Administrator",
    role: "System Administrator",
};

function getStoredProfile() {
    try {
        const storedProfile = localStorage.getItem("joross-profile");

        if (!storedProfile) {
            return initialProfile;
        }

        return {
            ...initialProfile,
            ...JSON.parse(storedProfile),
        };
    } catch {
        return initialProfile;
    }
}

export function useAccountSettings({
    user,
    updateCurrentUser,
    refreshCurrentUser,
}) {
    const [profile, setProfile] = useState(() => ({
        ...getStoredProfile(),
        ...(user || {}),
    }));

    const [profileForm, setProfileForm] = useState(() => ({
        ...getStoredProfile(),
        ...(user || {}),
    }));

    const [passwordModalOpen, setPasswordModalOpen] = useState(false);
    const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
    const [twoFactorSetup, setTwoFactorSetup] = useState(null);

    const profileDetailsRef = useRef(null);
    const accountSecurityRef = useRef(null);

    // Keep the form in sync with the signed-in account.
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

    const handleProfileChange = (event) => {
        const { name, value } = event.target;

        setProfileForm((currentProfile) => ({
            ...currentProfile,
            [name]: value,
        }));
    };

    const saveProfile = async (event) => {
        event.preventDefault();

        const requiredFields = [
            "fullName",
            "username",
            "email",
            "contactNumber",
            "position",
            "role",
        ];

        const missingField = requiredFields.some(
            (fieldName) => !String(profileForm[fieldName] || "").trim()
        );

        if (missingField) {
            notify("Please complete all account information.");
            return;
        }

        if (!profileForm.email.toLowerCase().endsWith("@gmail.com")) {
            notify("Please enter a valid Gmail address.");
            return;
        }

        if (!/^09\d{9}$/.test(profileForm.contactNumber)) {
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

            notify("Account information saved successfully.");
        } catch (error) {
            notify(
                error?.message || "Unable to save account information."
            );
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
        });

        if (!currentPassword) {
            return;
        }

        const otpCode = await promptAction({
            title: "Authenticator Code",
            message:
                "Enter the current 6-digit code from your authenticator app.",
            label: "6-Digit Code",
            confirmText: "Disable 2FA",
            cancelText: "Cancel",
            required: true,
        });

        if (!otpCode) {
            return;
        }

        try {
            await authService.disableTwoFactor({
                currentPassword,
                otpCode: otpCode.trim(),
            });

            setTwoFactorEnabled(false);
            await refreshCurrentUser();
            notify("Two-factor authentication disabled.");
        } catch (error) {
            notify(
                error?.message ||
                    "Unable to disable two-factor authentication."
            );
        }
    };

    const handleTwoFactorEnabled = async () => {
        setTwoFactorEnabled(true);
        await refreshCurrentUser();
    };

    return {
        profile,
        profileForm,
        profileDetailsRef,
        accountSecurityRef,
        passwordModalOpen,
        twoFactorEnabled,
        twoFactorSetup,
        handleProfileChange,
        saveProfile,
        toggleTwoFactor,
        openPasswordModal: () => setPasswordModalOpen(true),
        closePasswordModal: () => setPasswordModalOpen(false),
        closeTwoFactorSetup: () => setTwoFactorSetup(null),
        handleTwoFactorEnabled,
    };
}
