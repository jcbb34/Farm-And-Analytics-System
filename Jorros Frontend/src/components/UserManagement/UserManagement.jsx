"use client";
import { requestArchive } from "../../services/archiveService.js";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import {
    confirmAction,
    notifyError,
    notifySuccess,
    notifyWarning,
} from "../../context/NotificationContext.jsx";

import { userService } from "../../services/userService.js";
import { permissionsAreTaskOnly } from "../../utils/accessControl.js";
import { PersonalNameFields, PersonalAddressFields } from "../PersonalDetails/PersonalDetails.jsx";
import { composeFullName, emptyPersonalDetails, validatePersonalDetails } from "../PersonalDetails/personalDetails.js";
import "./UserManagement.css";

const USER_STATUSES = [
    "Active",
    "Disabled",
    "Archived",
];

function normalizeRole(role = "") {
    return String(role)
        .trim()
        .toLowerCase();
}

function isAdministratorRole(role) {
    return [
        "system administrator",
        "administrator",
        "admin",
    ].includes(
        normalizeRole(role)
    );
}

function isTaskManagementEmployeeRole(role) {
    return normalizeRole(role) === "employee";
}

function getInitials(name = "") {
    const initials = String(name)
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toUpperCase();

    return initials || "U";
}

function formatDateTime(value) {
    if (!value) {
        return "Never";
    }

    const date = new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return "Never";
    }

    return date.toLocaleString(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
        }
    );
}

function getStatusClass(status = "") {
    return String(status)
        .toLowerCase()
        .replaceAll(" ", "-");
}

function isTaskOnlyRole(roleName, roleDefinitions = []) {
    const definition = roleDefinitions.find(
        (role) => role.roleName === roleName
    );
    return permissionsAreTaskOnly(definition?.permissions);
}

function createEmptyForm(
    roleOptions,
    roleDefinitions = []
) {
    const defaultRole =
        roleOptions.find(
            (role) =>
                !isAdministratorRole(
                    role
                )
        ) ||
        roleOptions[0] ||
        "Farm Staff";

    return {
        fullName: "",
        personalDetails: emptyPersonalDetails(),
        username: "",
        email: "",
        contactNumber: "",
        position: "",
        role: defaultRole,
        status: "Active",
        password: "",
        confirmPassword: "",
    };
}

function UserFormModal({
    open,
    user,
    users,
    roleOptions,
    roleDefinitions,
    onClose,
    onSave,
}) {
    const isEditing =
        Boolean(user);

    const isCurrentAccount =
        Boolean(user?.isCurrentAccount);

    const [form, setForm] =
        useState(() =>
            createEmptyForm(
                roleOptions,
                roleDefinitions
            )
        );

    const [showPassword, setShowPassword] =
        useState(false);
    const modalRef = useRef(null);
    const saveInFlightRef = useRef(false);
    const [formSaving, setFormSaving] = useState(false);
    const closeIfReady = () => { if (!saveInFlightRef.current) onClose(); };
    useEffect(() => {
        if (!open) return;
        const previousFocus = document.activeElement;
        const handleKey = (event) => {
            const top = [...document.querySelectorAll('[role="dialog"][aria-modal="true"]')].at(-1);
            if (top !== modalRef.current) return;
            if (event.key === "Escape") { event.preventDefault(); if (!saveInFlightRef.current) onClose(); }
            if (event.key === "Tab") {
                const fields = [...modalRef.current.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled)')];
                const first = fields[0], last = fields.at(-1);
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
        };
        modalRef.current?.querySelector('input')?.focus();
        document.addEventListener("keydown", handleKey);
        return () => { document.removeEventListener("keydown", handleKey); previousFocus?.focus?.(); };
    }, [open]);


    useEffect(() => {
        if (!open) {
            return undefined;
        }

        if (user) {
            setForm({
                fullName:
                    user.fullName || "",
                personalDetails: user.personalDetails || null,
                username:
                    user.username || "",
                email:
                    user.email || "",
                contactNumber:
                    user.contactNumber ||
                    "",
                position:
                    user.position || "",
                role:
                    user.role ||
                    roleOptions[0] ||
                    "Farm Staff",
                status:
                    user.status ||
                    "Active",
                password: "",
                confirmPassword: "",
            });
        } else {
            setForm(
                createEmptyForm(
                    roleOptions,
                    roleDefinitions
                )
            );
        }

        setShowPassword(false);

        const previousOverflow =
            document.body.style
                .overflow;

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                previousOverflow;
        };
    }, [
        open,
        user,
        roleOptions,
        roleDefinitions,
    ]);

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

    const validateForm = () => {
        const detailsError = validatePersonalDetails(form.personalDetails, !isEditing);
        if (detailsError) { notifyWarning(detailsError); return false; }
        const employeeRole = isTaskOnlyRole(form.role, roleDefinitions);
        const requiredFields = [
            "fullName",
            "username",
            "contactNumber",
            "position",
            "role",
            "status",
            ...(employeeRole ? [] : ["email"]),
        ];

        const hasMissingField =
            requiredFields.some(
                (fieldName) =>
                    !String(
                        form[
                            fieldName
                        ] || ""
                    ).trim()
            );

        if (hasMissingField) {
            notifyWarning(
                "Please complete all required user fields."
            );

            return false;
        }

        if (
            !/^[A-Za-z0-9._-]{4,}$/.test(
                form.username.trim()
            )
        ) {
            notifyWarning(
                "Username must contain at least four characters and may only use letters, numbers, dots, underscores, or hyphens."
            );

            return false;
        }

        if (
            form.email.trim() &&
            !form.email.trim().toLowerCase().endsWith("@gmail.com")
        ) {
            notifyWarning("Please enter a valid Gmail address or leave it blank for an employee account.");
            return false;
        }

        if (
            !/^09\d{9}$/.test(
                form.contactNumber.trim()
            )
        ) {
            notifyWarning(
                "The contact number must contain 11 digits and begin with 09."
            );

            return false;
        }

        const duplicateUsername =
            users.some(
                (existingUser) =>
                    existingUser.id !==
                        user?.id &&
                    existingUser.username
                        .trim()
                        .toLowerCase() ===
                        form.username
                            .trim()
                            .toLowerCase()
            );

        if (duplicateUsername) {
            notifyWarning(
                "That username is already assigned to another user."
            );

            return false;
        }

        const duplicateEmail = Boolean(form.email.trim()) &&
            users.some(
                (existingUser) =>
                    existingUser.id !== user?.id &&
                    String(existingUser.email || "").trim().toLowerCase() === form.email.trim().toLowerCase()
            );

        if (duplicateEmail) {
            notifyWarning(
                "That email address is already assigned to another user."
            );

            return false;
        }

        const passwordRequired =
            !isEditing;

        const passwordProvided =
            Boolean(
                form.password ||
                    form.confirmPassword
            );

        if (
            passwordRequired &&
            !form.password
        ) {
            notifyWarning(
                "Please create a temporary password for the new user."
            );

            return false;
        }

        if (
            passwordProvided &&
            form.password.length < 8
        ) {
            notifyWarning(
                "The password must contain at least eight characters."
            );

            return false;
        }

        if (
            passwordProvided &&
            form.password !==
                form.confirmPassword
        ) {
            notifyWarning(
                "The password confirmation does not match."
            );

            return false;
        }

        return true;
    };

    const handleSubmit = async (
        event
    ) => {
        event.preventDefault();

        if (saveInFlightRef.current || !validateForm()) {
            return;
        }

        saveInFlightRef.current = true; setFormSaving(true);
        try { await onSave({
            personalDetails: form.personalDetails,
            fullName:
                form.fullName.trim(),
            username:
                form.username.trim(),
            email:
                form.email
                    .trim()
                    .toLowerCase(),
            contactNumber:
                form.contactNumber.trim(),
            position:
                form.position.trim(),
            role: form.role,
            status: form.status,
            password: form.password,
            passwordConfigured:
                isEditing
                    ? user
                          .passwordConfigured ||
                      Boolean(
                          form.password
                      )
                    : true,
            passwordUpdatedAt:
                form.password
                    ? new Date().toISOString()
                    : user
                          ?.passwordUpdatedAt ||
                      null,
        }); } finally { saveInFlightRef.current = false; setFormSaving(false); }
    };

    return (
        <div
            className="user-management-modal-overlay"
            onMouseDown={closeIfReady}
        >
            <div
                ref={modalRef}
                role="dialog" aria-modal="true" aria-labelledby="user-form-title"
                className="user-management-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="user-management-modal-header">
                    <div>
                        <span className="material-symbols-outlined" aria-hidden="true">
                            {isEditing
                                ? "manage_accounts"
                                : "person_add"}
                        </span>

                        <div>
                            <h2 id="user-form-title">
                                {isEditing
                                    ? "Edit User Account"
                                    : "Create User Account"}
                            </h2>

                            <p>
                                {isEditing
                                    ? "Update the selected user's account details and access role."
                                    : "Create a new account and assign the correct system role."}
                            </p>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={closeIfReady}
                            disabled={formSaving}
                        aria-label="Close user form"
                    >
                        <span className="material-symbols-outlined" aria-hidden="true">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="user-management-form"
                    onSubmit={handleSubmit}
                >
                    <section className="user-management-form-section">
                        <div className="user-management-section-title">
                            <span className="material-symbols-outlined" aria-hidden="true">
                                badge
                            </span>

                            <div>
                                <h3>
                                    Personal Information
                                </h3>

                                <p>
                                    Enter the user's identity and contact details.
                                </p>
                            </div>
                        </div>

                        <div className="user-management-form-grid">
                            <PersonalNameFields value={form.personalDetails} legacyFullName={user?.fullName} isNew={!isEditing}
                                onChange={(details) => setForm((current) => ({ ...current, personalDetails: details, fullName: composeFullName(details, current.fullName) }))}/>
                            <div className="user-management-form-group">
                                <label htmlFor="userEmail">
                                    Email Address
                                    {!isTaskOnlyRole(form.role, roleDefinitions) && <span>*</span>}
                                </label>

                                <input
                                    id="userEmail"
                                    name="email"
                                    type="email"
                                    placeholder={isTaskOnlyRole(form.role, roleDefinitions) ? "Optional for task-only accounts" : "name@gmail.com"}
                                    value={
                                        form.email
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="user-management-form-group">
                                <label htmlFor="userContactNumber">
                                    Contact Number
                                    <span>*</span>
                                </label>

                                <input
                                    id="userContactNumber"
                                    name="contactNumber"
                                    type="text"
                                    inputMode="numeric"
                                    maxLength="11"
                                    placeholder="09XXXXXXXXX"
                                    value={
                                        form.contactNumber
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="user-management-form-group full-width">
                                <label htmlFor="userPosition">
                                    Position
                                    <span>*</span>
                                </label>

                                <input
                                    id="userPosition"
                                    name="position"
                                    type="text"
                                    placeholder="Example: Farm Staff"
                                    value={
                                        form.position
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                            <PersonalAddressFields value={form.personalDetails} onChange={(details) => setForm((current) => ({ ...current, personalDetails: details }))}/>
                        </div>
                    </section>

                    <section className="user-management-form-section">
                        <div className="user-management-section-title">
                            <span className="material-symbols-outlined" aria-hidden="true">
                                security
                            </span>

                            <div>
                                <h3>
                                    Account and Access
                                </h3>

                                <p>
                                    Set the username, role, status, and account password.
                                </p>
                            </div>
                        </div>

                        <div className="user-management-form-grid">
                            <div className="user-management-form-group">
                                <label htmlFor="userUsername">
                                    Username
                                    <span>*</span>
                                </label>

                                <input
                                    id="userUsername"
                                    name="username"
                                    type="text"
                                    autoComplete="off"
                                    placeholder="Enter username"
                                    value={
                                        form.username
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="user-management-form-group">
                                <label htmlFor="userRole">
                                    Role
                                    <span>*</span>
                                </label>

                                <select
                                    id="userRole"
                                    name="role"
                                    value={
                                        form.role
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    disabled={
                                        isCurrentAccount
                                    }
                                >
                                    {roleOptions.map(
                                        (role) => (
                                            <option
                                                key={role}
                                                value={role}
                                            >
                                                {role}
                                            </option>
                                        )
                                    )}
                                </select>

                                {isCurrentAccount && (
                                    <small>
                                        You cannot change the role of the account currently signed in.
                                    </small>
                                )}
                            </div>

                            <div className="user-management-form-group">
                                <label htmlFor="userStatus">
                                    Account Status
                                    <span>*</span>
                                </label>

                                <select
                                    id="userStatus"
                                    name="status"
                                    value={
                                        form.status
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    disabled={
                                        isCurrentAccount
                                    }
                                >
                                    {USER_STATUSES.filter(
                                        (status) =>
                                            status !==
                                            "Archived"
                                    ).map(
                                        (status) => (
                                            <option
                                                key={status}
                                                value={status}
                                            >
                                                {status}
                                            </option>
                                        )
                                    )}
                                </select>

                                {isCurrentAccount && (
                                    <small>
                                        The signed-in account must remain active.
                                    </small>
                                )}
                            </div>

                            <div className="user-management-form-group">
                                <label htmlFor="userPassword">
                                    {isEditing
                                        ? "New Password"
                                        : "Temporary Password"}
                                    {!isEditing && (
                                        <span>*</span>
                                    )}
                                </label>

                                <div className="user-management-password-input">
                                    <input
                                        id="userPassword"
                                        name="password"
                                        type={
                                            showPassword
                                                ? "text"
                                                : "password"
                                        }
                                        autoComplete="new-password"
                                        placeholder={
                                            isEditing
                                                ? "Leave blank to keep current password"
                                                : "Minimum 8 characters"
                                        }
                                        value={
                                            form.password
                                        }
                                        onChange={
                                            handleChange
                                        }
                                    />

                                    <button
                                        type="button"
                                        onClick={() =>
                                            setShowPassword(
                                                (current) =>
                                                    !current
                                            )
                                        }
                                        aria-label={
                                            showPassword
                                                ? "Hide password"
                                                : "Show password"
                                        }
                                    >
                                        <span className="material-symbols-outlined" aria-hidden="true">
                                            {showPassword
                                                ? "visibility_off"
                                                : "visibility"}
                                        </span>
                                    </button>
                                </div>
                            </div>

                            <div className="user-management-form-group full-width">
                                <label htmlFor="userConfirmPassword">
                                    Confirm Password
                                    {!isEditing && (
                                        <span>*</span>
                                    )}
                                </label>

                                <input
                                    id="userConfirmPassword"
                                    name="confirmPassword"
                                    type={
                                        showPassword
                                            ? "text"
                                            : "password"
                                    }
                                    autoComplete="new-password"
                                    placeholder="Re-enter password"
                                    value={
                                        form.confirmPassword
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                        </div>

                        <div className="user-management-security-note">
                            <span className="material-symbols-outlined" aria-hidden="true">
                                shield_lock
                            </span>

                            <p>
                                The password is sent securely to the FastAPI backend, where it is hashed before being stored in the database.
                            </p>
                        </div>
                    </section>

                    <footer className="user-management-form-footer">
                        <button
                            type="button"
                            className="user-management-secondary-button"
                            onClick={closeIfReady}
                            disabled={formSaving}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            disabled={formSaving}
                            className="user-management-primary-button"
                        >
                            <span className="material-symbols-outlined" aria-hidden="true">
                                {isEditing
                                    ? "save"
                                    : "person_add"}
                            </span>

                            {formSaving ? "Saving..." : isEditing
                                ? "Save Changes"
                                : "Create User"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}

function UserManagement({
    currentProfile,
    isAdministrator,
}) {
    const [users, setUsers] =
        useState([]);

    const [availableRoles, setAvailableRoles] =
        useState([]);

    const [isLoadingUsers, setIsLoadingUsers] =
        useState(true);

    const [searchText, setSearchText] =
        useState("");

    const [roleFilter, setRoleFilter] =
        useState("All");

    const [statusFilter, setStatusFilter] =
        useState("All");

    const [formOpen, setFormOpen] =
        useState(false);

    const [selectedUser, setSelectedUser] =
        useState(null);

    const roleOptions =
        useMemo(() => {
            const roleNames =
                availableRoles
                    .map(
                        (role) =>
                            role.roleName
                    )
                    .filter(
                        (roleName) =>
                            Boolean(roleName) &&
                            !isTaskManagementEmployeeRole(roleName)
                    );

            return [
                ...new Set(roleNames),
            ];
        }, [availableRoles]);

    useEffect(() => {
        let cancelled = false;

        async function loadUsersAndRoles() {
            setIsLoadingUsers(true);

            try {
                const [
                    databaseUsers,
                    databaseRoles,
                ] = await Promise.all([
                    userService.getUsers(),
                    userService.getRoles(),
                ]);

                if (cancelled) {
                    return;
                }

                const normalizedUsers =
                    databaseUsers.map(
                        (user) => ({
                            ...user,
                            isCurrentAccount:
                                user.username ===
                                currentProfile.username,
                        })
                    );

                setUsers(normalizedUsers);
                setAvailableRoles(databaseRoles);
            } catch (error) {
                if (cancelled) {
                    return;
                }

                console.error(
                    "Failed to load User Management data:",
                    error
                );

                notifyError(
                    error?.message ||
                        "Unable to load users from the database."
                );
            } finally {
                if (!cancelled) {
                    setIsLoadingUsers(false);
                }
            }
        }

        if (isAdministrator) {
            loadUsersAndRoles();
        } else {
            setIsLoadingUsers(false);
        }

        return () => {
            cancelled = true;
        };
    }, [
        isAdministrator,
        currentProfile.username,
    ]);

    const systemUsers =
        useMemo(
            () =>
                users.filter(
                    (user) =>
                        !isTaskManagementEmployeeRole(
                            user.role
                        )
                ),
            [users]
        );

    const filteredUsers =
        useMemo(() => {
            const normalizedSearch =
                searchText
                    .trim()
                    .toLowerCase();

            return systemUsers.filter(
                (user) => {
                    const matchesSearch =
                        !normalizedSearch ||
                        user.fullName
                            .toLowerCase()
                            .includes(
                                normalizedSearch
                            ) ||
                        user.username
                            .toLowerCase()
                            .includes(
                                normalizedSearch
                            ) ||
                        user.email
                            .toLowerCase()
                            .includes(
                                normalizedSearch
                            ) ||
                        user.userCode
                            .toLowerCase()
                            .includes(
                                normalizedSearch
                            );

                    const matchesRole =
                        roleFilter ===
                            "All" ||
                        user.role ===
                            roleFilter;

                    const matchesStatus =
                        statusFilter ===
                            "All" ||
                        user.status ===
                            statusFilter;

                    return (
                        matchesSearch &&
                        matchesRole &&
                        matchesStatus
                    );
                }
            );
        }, [
            systemUsers,
            searchText,
            roleFilter,
            statusFilter,
        ]);

    const statistics =
        useMemo(() => {
            const activeUsers =
                systemUsers.filter(
                    (user) =>
                        user.status ===
                        "Active"
                ).length;

            const disabledUsers =
                systemUsers.filter(
                    (user) =>
                        user.status ===
                        "Disabled"
                ).length;

            const administrators =
                systemUsers.filter(
                    (user) =>
                        isAdministratorRole(
                            user.role
                        ) &&
                        user.status !==
                            "Archived"
                ).length;

            return {
                total: systemUsers.length,
                active: activeUsers,
                disabled: disabledUsers,
                administrators,
            };
        }, [systemUsers]);

    if (!isAdministrator) {
        return (
            <section className="user-management-access-denied">
                <span className="material-symbols-outlined">
                    lock
                </span>

                <h2>
                    Administrator Access Required
                </h2>

                <p>
                    Only a System Administrator can create or manage user accounts.
                </p>
            </section>
        );
    }

    const activeAdministratorCount =
        () =>
            users.filter(
                (user) =>
                    isAdministratorRole(
                        user.role
                    ) &&
                    user.status ===
                        "Active"
            ).length;

    const openCreateUser = () => {
        setSelectedUser(null);
        setFormOpen(true);
    };

    const openEditUser = (
        user
    ) => {
        if (
            user.status ===
            "Archived"
        ) {
            notifyWarning(
                "Restore this archived user before editing the account."
            );

            return;
        }

        setSelectedUser(user);
        setFormOpen(true);
    };

    const closeForm = () => {
        setFormOpen(false);
        setSelectedUser(null);
    };

    const saveUser = async (
        formData
    ) => {
        try {
            if (selectedUser) {
                const protectedFormData =
                    selectedUser.isCurrentAccount
                        ? {
                              ...formData,
                              role: selectedUser.role,
                              status: selectedUser.status,
                          }
                        : formData;

                const removingLastAdmin =
                    isAdministratorRole(
                        selectedUser.role
                    ) &&
                    selectedUser.status ===
                        "Active" &&
                    (!isAdministratorRole(
                        protectedFormData.role
                    ) ||
                        protectedFormData.status !==
                            "Active") &&
                    activeAdministratorCount() <=
                        1;

                if (removingLastAdmin) {
                    notifyError(
                        "The last active administrator cannot be changed to a non-administrator role or disabled."
                    );

                    return;
                }

                const updatedUser =
                    await userService.updateUser(
                        selectedUser.id,
                        protectedFormData
                    );

                const normalizedUpdatedUser = {
                    ...updatedUser,
                    isCurrentAccount:
                        selectedUser.isCurrentAccount,
                };

                setUsers(
                    (currentUsers) =>
                        currentUsers.map(
                            (user) =>
                                user.id ===
                                selectedUser.id
                                    ? normalizedUpdatedUser
                                    : user
                        )
                );

                if (
                    selectedUser.isCurrentAccount
                ) {
                    const updatedProfile = {
                        ...currentProfile,
                        fullName:
                            normalizedUpdatedUser.fullName,
                        username:
                            normalizedUpdatedUser.username,
                        email:
                            normalizedUpdatedUser.email,
                        contactNumber:
                            normalizedUpdatedUser.contactNumber,
                        position:
                            normalizedUpdatedUser.position,
                        role:
                            normalizedUpdatedUser.role,
                    };

                    localStorage.setItem(
                        "joross-profile",
                        JSON.stringify(
                            updatedProfile
                        )
                    );

                    window.dispatchEvent(
                        new CustomEvent(
                            "joross-profile-updated",
                            {
                                detail:
                                    updatedProfile,
                            }
                        )
                    );
                }

                notifySuccess(
                    "User account updated successfully."
                );
            } else {
                const createdUser =
                    await userService.createUser(
                        formData
                    );

                setUsers(
                    (currentUsers) => [
                        {
                            ...createdUser,
                            isCurrentAccount:
                                createdUser.username ===
                                currentProfile.username,
                        },
                        ...currentUsers,
                    ]
                );

                notifySuccess(
                    "User account created successfully."
                );
            }

            closeForm();
        } catch (error) {
            console.error(
                "Unable to save user:",
                error
            );

            notifyError(
                error?.message ||
                    "Unable to save the user account."
            );
        }
    };

    const toggleUserStatus = async (
        user
    ) => {
        if (user.isCurrentAccount) {
            notifyWarning(
                "You cannot disable the account currently signed in."
            );

            return;
        }

        if (
            user.status ===
            "Archived"
        ) {
            const confirmed =
                await confirmAction({
                    title:
                        "Restore User Account",
                    message: `Restore ${user.fullName} as an active user?`,
                    type: "info",
                    confirmText:
                        "Restore",
                    cancelText:
                        "Cancel",
                });

            if (!confirmed) {
                return;
            }

            try {
                const restoredUser =
                    await userService.restoreUser(
                        user.id
                    );

                setUsers(
                    (currentUsers) =>
                        currentUsers.map(
                            (item) =>
                                item.id ===
                                user.id
                                    ? {
                                          ...restoredUser,
                                          isCurrentAccount:
                                              false,
                                      }
                                    : item
                        )
                );

                notifySuccess(
                    "User account restored successfully."
                );
            } catch (error) {
                notifyError(
                    error?.message ||
                        "Unable to restore the user account."
                );
            }

            return;
        }

        const nextStatus =
            user.status ===
            "Active"
                ? "Disabled"
                : "Active";

        if (
            user.status ===
                "Active" &&
            isAdministratorRole(
                user.role
            ) &&
            activeAdministratorCount() <=
                1
        ) {
            notifyError(
                "The last active administrator cannot be disabled."
            );

            return;
        }

        const confirmed =
            await confirmAction({
                title:
                    nextStatus ===
                    "Active"
                        ? "Enable User Account"
                        : "Disable User Account",
                message:
                    nextStatus ===
                    "Active"
                        ? `Enable ${user.fullName}'s account?`
                        : `Disable ${user.fullName}'s account? The user will not be allowed to sign in.`,
                type:
                    nextStatus ===
                    "Active"
                        ? "info"
                        : "warning",
                confirmText:
                    nextStatus ===
                    "Active"
                        ? "Enable"
                        : "Disable",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            const updatedUser =
                nextStatus === "Active"
                    ? await userService.activateUser(
                          user.id
                      )
                    : await userService.disableUser(
                          user.id
                      );

            setUsers(
                (currentUsers) =>
                    currentUsers.map(
                        (item) =>
                            item.id ===
                            user.id
                                ? {
                                      ...updatedUser,
                                      isCurrentAccount:
                                          false,
                                  }
                                : item
                    )
            );

            notifySuccess(
                nextStatus === "Active"
                    ? "User account enabled successfully."
                    : "User account disabled successfully."
            );
        } catch (error) {
            notifyError(
                error?.message ||
                    "Unable to change the user account status."
            );
        }
    };

    const archiveUser = async (
        user
    ) => {
        if (user.isCurrentAccount) {
            notifyWarning(
                "You cannot archive the account currently signed in."
            );

            return;
        }

        if (
            isAdministratorRole(
                user.role
            ) &&
            user.status ===
                "Active" &&
            activeAdministratorCount() <=
                1
        ) {
            notifyError(
                "The last active administrator cannot be archived."
            );

            return;
        }

        const confirmed = await requestArchive("User", user.id, user.fullName);

        if (!confirmed) {
            return;
        }

        try {
            const archivedUser = { ...user, status: "Archived" };

            setUsers(
                (currentUsers) =>
                    currentUsers.map(
                        (item) =>
                            item.id ===
                            user.id
                                ? {
                                      ...archivedUser,
                                      isCurrentAccount:
                                          false,
                                  }
                                : item
                    )
            );

            notifySuccess(
                "User account archived successfully."
            );
        } catch (error) {
            notifyError(
                error?.message ||
                    "Unable to archive the user account."
            );
        }
    };

    const resetFilters = () => {
        setSearchText("");
        setRoleFilter("All");
        setStatusFilter("All");
    };

    return (
        <section className="user-management-section">
            <div className="user-management-heading">
                <div>
                    <div className="user-management-heading-label">
                        <span className="material-symbols-outlined">
                            admin_panel_settings
                        </span>

                        Administrator Only
                    </div>

                    <h2>
                        User Management
                    </h2>

                    <p>
                        Create user accounts, assign roles, and control account access.
                    </p>
                </div>

                <button
                    type="button"
                    className="user-management-primary-button"
                    onClick={openCreateUser}
                >
                    <span className="material-symbols-outlined">
                        person_add
                    </span>

                    Create User
                </button>
            </div>

            <div className="user-management-stat-grid">
                <article className="user-management-stat-card total">
                    <span className="material-symbols-outlined">
                        group
                    </span>

                    <div>
                        <p>
                            Total Users
                        </p>

                        <strong>
                            {statistics.total}
                        </strong>
                    </div>
                </article>

                <article className="user-management-stat-card active">
                    <span className="material-symbols-outlined">
                        person_check
                    </span>

                    <div>
                        <p>
                            Active Users
                        </p>

                        <strong>
                            {statistics.active}
                        </strong>
                    </div>
                </article>

                <article className="user-management-stat-card disabled">
                    <span className="material-symbols-outlined">
                        person_off
                    </span>

                    <div>
                        <p>
                            Disabled Users
                        </p>

                        <strong>
                            {statistics.disabled}
                        </strong>
                    </div>
                </article>

                <article className="user-management-stat-card admin">
                    <span className="material-symbols-outlined">
                        shield_person
                    </span>

                    <div>
                        <p>
                            Administrators
                        </p>

                        <strong>
                            {statistics.administrators}
                        </strong>
                    </div>
                </article>
            </div>

            <div className="user-management-toolbar">
                <div className="user-management-search">
                    <span className="material-symbols-outlined">
                        search
                    </span>

                    <input
                        type="text"
                        placeholder="Search user, username, email, or code..."
                        value={searchText}
                        onChange={(event) =>
                            setSearchText(
                                event.target
                                    .value
                            )
                        }
                    />
                </div>

                <select
                    value={roleFilter}
                    onChange={(event) =>
                        setRoleFilter(
                            event.target
                                .value
                        )
                    }
                >
                    <option value="All">
                        All Roles
                    </option>

                    {roleOptions.map(
                        (role) => (
                            <option
                                key={role}
                                value={role}
                            >
                                {role}
                            </option>
                        )
                    )}
                </select>

                <select
                    value={statusFilter}
                    onChange={(event) =>
                        setStatusFilter(
                            event.target
                                .value
                        )
                    }
                >
                    <option value="All">
                        All Status
                    </option>

                    {USER_STATUSES.map(
                        (status) => (
                            <option
                                key={status}
                                value={status}
                            >
                                {status}
                            </option>
                        )
                    )}
                </select>

                <button
                    type="button"
                    className="user-management-reset-button"
                    onClick={resetFilters}
                >
                    <span className="material-symbols-outlined">
                        restart_alt
                    </span>

                    Reset
                </button>
            </div>

            <article className="user-management-table-card">
                <div className="user-management-table-heading">
                    <div>
                        <h3>
                            System Users
                        </h3>

                        <p>
                            {filteredUsers.length}{" "}
                            user account(s) found
                        </p>
                    </div>

                    <span>
                        {systemUsers.length}{" "}
                        total accounts
                    </span>
                </div>

                <div className="user-management-table-wrapper">
                    <table className="user-management-table">
                        <thead>
                            <tr>
                                <th>
                                    User
                                </th>

                                <th>
                                    Username
                                </th>

                                <th>
                                    Role
                                </th>

                                <th>
                                    Position
                                </th>

                                <th>
                                    Status
                                </th>

                                <th>
                                    Last Login
                                </th>

                                <th>
                                    Actions
                                </th>
                            </tr>
                        </thead>

                        <tbody>
                            {isLoadingUsers ? (
                                <tr>
                                    <td
                                        colSpan="7"
                                        className="user-management-empty"
                                    >
                                        <span className="material-symbols-outlined">
                                            progress_activity
                                        </span>

                                        <h4>
                                            Loading users...
                                        </h4>

                                        <p>
                                            Retrieving user accounts from the database.
                                        </p>
                                    </td>
                                </tr>
                            ) : filteredUsers.length >
                            0 ? (
                                filteredUsers.map(
                                    (user) => (
                                        <tr
                                            key={
                                                user.id
                                            }
                                        >
                                            <td>
                                                <div className="user-management-user-cell">
                                                    <span className="user-management-avatar">
                                                        {getInitials(
                                                            user.fullName
                                                        )}
                                                    </span>

                                                    <div>
                                                        <strong>
                                                            {
                                                                user.fullName
                                                            }
                                                        </strong>

                                                        <small>
                                                            {
                                                                user.userCode
                                                            }
                                                            {user.isCurrentAccount && (
                                                                <em>
                                                                    Current account
                                                                </em>
                                                            )}
                                                        </small>

                                                        <span>
                                                            {
                                                                user.email
                                                            }
                                                        </span>
                                                    </div>
                                                </div>
                                            </td>

                                            <td>
                                                <strong className="user-management-username">
                                                    @{
                                                        user.username
                                                    }
                                                </strong>
                                            </td>

                                            <td>
                                                <span
                                                    className={`user-management-role-badge ${
                                                        isAdministratorRole(
                                                            user.role
                                                        )
                                                            ? "administrator"
                                                            : "standard"
                                                    }`}
                                                >
                                                    {
                                                        user.role
                                                    }
                                                </span>
                                            </td>

                                            <td>
                                                {
                                                    user.position
                                                }
                                            </td>

                                            <td>
                                                <span
                                                    className={`user-management-status-badge ${getStatusClass(
                                                        user.status
                                                    )}`}
                                                >
                                                    {
                                                        user.status
                                                    }
                                                </span>
                                            </td>

                                            <td>
                                                <span className="user-management-last-login">
                                                    {formatDateTime(
                                                        user.lastLogin
                                                    )}
                                                </span>
                                            </td>

                                            <td>
                                                <div className="user-management-actions">
                                                    <button
                                                        type="button"
                                                        title="Edit user"
                                                        disabled={
                                                            user.status ===
                                                            "Archived"
                                                        }
                                                        onClick={() =>
                                                            openEditUser(
                                                                user
                                                            )
                                                        }
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            edit
                                                        </span>
                                                    </button>

                                                    <button
                                                        type="button"
                                                        className={
                                                            user.status ===
                                                            "Active"
                                                                ? "disable"
                                                                : "enable"
                                                        }
                                                        title={
                                                            user.status ===
                                                            "Active"
                                                                ? "Disable user"
                                                                : user.status ===
                                                                  "Archived"
                                                                ? "Restore user"
                                                                : "Enable user"
                                                        }
                                                        onClick={() =>
                                                            toggleUserStatus(
                                                                user
                                                            )
                                                        }
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            {user.status ===
                                                            "Active"
                                                                ? "person_off"
                                                                : user.status ===
                                                                  "Archived"
                                                                ? "restore"
                                                                : "person_check"}
                                                        </span>
                                                    </button>

                                                    {user.status !==
                                                        "Archived" && (
                                                        <button
                                                            type="button"
                                                            className="archive"
                                                            title="Archive user"
                                                            onClick={() =>
                                                                archiveUser(
                                                                    user
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                archive
                                                            </span>
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    )
                                )
                            ) : (
                                <tr>
                                    <td
                                        colSpan="7"
                                        className="user-management-empty"
                                    >
                                        <span className="material-symbols-outlined">
                                            group_off
                                        </span>

                                        <h4>
                                            No users found
                                        </h4>

                                        <p>
                                            No user accounts match the selected filters.
                                        </p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </article>

            <UserFormModal
                open={formOpen}
                user={selectedUser}
                users={users}
                roleOptions={roleOptions}
                roleDefinitions={availableRoles}
                onClose={closeForm}
                onSave={saveUser}
            />
        </section>
    );
}

export default UserManagement;
