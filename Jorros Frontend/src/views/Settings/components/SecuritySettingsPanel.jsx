"use client";

// Role permissions and access settings
export default function SecuritySettingsPanel({
    roles,
    permissionLabels,
    onAddRole,
    onDeleteRole,
    onTogglePermission,
}) {
    return (
        <section className="settings-page-section">
            <div className="settings-page-section-heading with-button">
                <div>
                    <h2>Security and Access</h2>
                    <p>
                        Manage user roles and control which modules each role can
                        access.
                    </p>
                </div>

                <button
                    type="button"
                    className="settings-page-primary-button"
                    onClick={onAddRole}
                >
                    <span className="material-symbols-outlined">add</span>
                    Add Role
                </button>
            </div>

            <div className="settings-page-role-list">
                {roles.map((role) => (
                    <article className="settings-page-role-card" key={role.id}>
                        <div className="settings-page-role-header">
                            <div>
                                <span className="material-symbols-outlined">
                                    admin_panel_settings
                                </span>

                                <div>
                                    <h3>{role.roleName}</h3>
                                    <p>{role.description}</p>
                                </div>
                            </div>

                            <button
                                type="button"
                                disabled={[
                                    "System Administrator",
                                    "Farm Staff",
                                    "Viewer",
                                ].includes(role.roleName)}
                                onClick={() => onDeleteRole(role)}
                            >
                                <span className="material-symbols-outlined">
                                    delete
                                </span>
                            </button>
                        </div>

                        <div className="settings-page-permission-grid">
                            {Object.entries(permissionLabels).map(
                                ([permission, label]) => (
                                    <label
                                        key={permission}
                                        className="settings-page-permission-item"
                                    >
                                        <input
                                            type="checkbox"
                                            checked={Boolean(
                                                role.permissions[permission]
                                            )}
                                            disabled={
                                                role.roleName ===
                                                "System Administrator"
                                            }
                                            onChange={() =>
                                                onTogglePermission(
                                                    role.id,
                                                    permission
                                                )
                                            }
                                        />
                                        <span>{label}</span>
                                    </label>
                                )
                            )}
                        </div>
                    </article>
                ))}
            </div>
        </section>
    );
}
