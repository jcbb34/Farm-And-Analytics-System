// Small overview cards shown above the settings menu
export default function SettingsSummaryCards({
    profile,
    twoFactorEnabled,
    rolesCount,
    archivedCount,
    isSystemAdministrator,
}) {
    return (
        <section className="settings-page-summary-grid">
            <article className="settings-page-summary-card account">
                <span>
                    <span className="material-symbols-outlined">person</span>
                </span>

                <div>
                    <p>Current Account</p>
                    <h2>{profile.username}</h2>
                    <small>{profile.role}</small>
                </div>
            </article>

            <article className="settings-page-summary-card security">
                <span>
                    <span className="material-symbols-outlined">verified_user</span>
                </span>

                <div>
                    <p>Two-Factor Authentication</p>
                    <h2>{twoFactorEnabled ? "Enabled" : "Disabled"}</h2>
                    <small>Account security</small>
                </div>
            </article>

            {isSystemAdministrator && (
                <article className="settings-page-summary-card roles">
                    <span>
                        <span className="material-symbols-outlined">admin_panel_settings</span>
                    </span>

                    <div>
                        <p>User Roles</p>
                        <h2>{rolesCount}</h2>
                        <small>Access roles</small>
                    </div>
                </article>
            )}

            <article className="settings-page-summary-card archive">
                <span>
                    <span className="material-symbols-outlined">archive</span>
                </span>

                <div>
                    <p>Archived Records</p>
                    <h2>{archivedCount}</h2>
                    <small>Stored records</small>
                </div>
            </article>
        </section>
    );
}
