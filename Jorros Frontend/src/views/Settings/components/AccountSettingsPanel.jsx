"use client";

// Account profile and security controls.
const recentActivity = [
    {
        id: 1,
        action: "Updated livestock health record",
        date: "2026-08-04T18:30:00",
        icon: "pets",
    },
    {
        id: 2,
        action: "Generated crop production report",
        date: "2026-08-04T14:10:00",
        icon: "description",
    },
    {
        id: 3,
        action: "Changed weather alert settings",
        date: "2026-08-03T16:45:00",
        icon: "notifications",
    },
    {
        id: 4,
        action: "Added inventory stock",
        date: "2026-08-03T09:25:00",
        icon: "inventory_2",
    },
];

function getInitials(name = "") {
    return name
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toUpperCase();
}

function formatDateTime(value) {
    if (!value) return "Not specified";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Not specified";

    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

export default function AccountSettingsPanel({
    profile,
    profileForm,
    profileDetailsRef,
    accountSecurityRef,
    twoFactorEnabled,
    onProfileChange,
    onSaveProfile,
    onChangePassword,
    onToggleTwoFactor,
}) {
    return (
        <section className="settings-page-section">
            <div className="settings-page-section-heading">
                <div>
                    <h2>Account Settings</h2>
                    <p>
                        Manage your profile information, password, and account
                        security.
                    </p>
                </div>
            </div>

            {/* Profile details */}
            <article
                ref={profileDetailsRef}
                className="settings-page-account-card settings-page-scroll-target"
            >
                <div className="settings-page-account-profile">
                    <span className="settings-page-large-avatar">
                        {getInitials(profile.fullName)}
                    </span>

                    <div>
                        <h3>{profile.fullName}</h3>
                        <p>{profile.role}</p>
                        <small>{profile.email}</small>
                    </div>
                </div>

                <form
                    className="settings-page-account-form"
                    onSubmit={onSaveProfile}
                >
                    <div className="settings-page-form-grid">
                        <div className="settings-page-form-group">
                            <label htmlFor="settingsFullName">
                                Full Name <span>*</span>
                            </label>
                            <input
                                id="settingsFullName"
                                name="fullName"
                                type="text"
                                value={profileForm.fullName}
                                onChange={onProfileChange}
                                required
                            />
                        </div>

                        <div className="settings-page-form-group">
                            <label htmlFor="settingsUsername">
                                Username <span>*</span>
                            </label>
                            <input
                                id="settingsUsername"
                                name="username"
                                type="text"
                                value={profileForm.username}
                                onChange={onProfileChange}
                                required
                            />
                        </div>

                        <div className="settings-page-form-group">
                            <label htmlFor="settingsEmail">
                                Email Address <span>*</span>
                            </label>
                            <input
                                id="settingsEmail"
                                name="email"
                                type="email"
                                value={profileForm.email}
                                onChange={onProfileChange}
                                required
                            />
                        </div>

                        <div className="settings-page-form-group">
                            <label htmlFor="settingsContact">
                                Contact Number <span>*</span>
                            </label>
                            <input
                                id="settingsContact"
                                name="contactNumber"
                                type="text"
                                maxLength="11"
                                value={profileForm.contactNumber}
                                onChange={onProfileChange}
                                required
                            />
                        </div>

                        <div className="settings-page-form-group">
                            <label htmlFor="settingsPosition">
                                Position <span>*</span>
                            </label>
                            <input
                                id="settingsPosition"
                                name="position"
                                type="text"
                                value={profileForm.position}
                                onChange={onProfileChange}
                                required
                            />
                        </div>

                        <div className="settings-page-form-group">
                            <label htmlFor="settingsRole">
                                Role <span>*</span>
                            </label>
                            <input
                                id="settingsRole"
                                name="role"
                                type="text"
                                value={profile.role}
                                readOnly
                                aria-readonly="true"
                            />
                            <small>
                                Your own role cannot be changed here. Roles are
                                assigned by a System Administrator through User
                                Management.
                            </small>
                        </div>
                    </div>

                    <div className="settings-page-account-form-footer">
                        <button
                            type="submit"
                            className="settings-page-primary-button"
                        >
                            <span className="material-symbols-outlined">save</span>
                            Save Account
                        </button>
                    </div>
                </form>
            </article>

            {/* Password and 2FA */}
            <div
                ref={accountSecurityRef}
                className="settings-page-security-actions settings-page-scroll-target"
            >
                <article className="settings-page-action-card">
                    <span className="settings-page-action-icon">
                        <span className="material-symbols-outlined">password</span>
                    </span>
                    <div>
                        <h3>Password</h3>
                        <p>
                            Change your account password regularly to keep your
                            account secure.
                        </p>
                    </div>
                    <button type="button" onClick={onChangePassword}>
                        Change Password
                    </button>
                </article>

                <article className="settings-page-action-card">
                    <span className="settings-page-action-icon">
                        <span className="material-symbols-outlined">
                            verified_user
                        </span>
                    </span>
                    <div>
                        <h3>Two-Factor Authentication</h3>
                        <p>Add another verification step when signing in.</p>
                    </div>
                    <button
                        type="button"
                        className={twoFactorEnabled ? "enabled" : ""}
                        onClick={onToggleTwoFactor}
                    >
                        {twoFactorEnabled ? "Enabled" : "Enable 2FA"}
                    </button>
                </article>
            </div>

            {/* Recent account activity */}
            <article className="settings-page-activity-card">
                <div className="settings-page-card-heading">
                    <div>
                        <h3>Recent Activity</h3>
                        <p>Latest account activities performed in the system.</p>
                    </div>
                    <span className="material-symbols-outlined">history</span>
                </div>

                <div className="settings-page-activity-list">
                    {recentActivity.map((activity) => (
                        <div key={activity.id}>
                            <span>
                                <span className="material-symbols-outlined">
                                    {activity.icon}
                                </span>
                            </span>
                            <div>
                                <strong>{activity.action}</strong>
                                <small>{formatDateTime(activity.date)}</small>
                            </div>
                        </div>
                    ))}
                </div>
            </article>
        </section>
    );
}
