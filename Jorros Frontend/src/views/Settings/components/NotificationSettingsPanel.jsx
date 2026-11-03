"use client";

import { notify } from "../../../context/NotificationContext.jsx";

// Notification preferences used in Settings.
function SettingsToggle({
    icon,
    title,
    description,
    checked,
    onChange,
}) {
    return (
        <article className="settings-page-toggle-card">
            <span className="settings-page-toggle-icon">
                <span className="material-symbols-outlined">
                    {icon}
                </span>
            </span>

            <div className="settings-page-toggle-content">
                <strong>{title}</strong>
                <p>{description}</p>
            </div>

            <button
                type="button"
                role="switch"
                aria-checked={checked}
                className={`settings-page-switch ${checked ? "enabled" : ""}`}
                onClick={onChange}
            >
                <span />
            </button>
        </article>
    );
}

export default function NotificationSettingsPanel({
    settings,
    setSettings,
}) {
    const toggleSetting = (fieldName) => {
        setSettings((current) => ({
            ...current,
            [fieldName]: !current[fieldName],
        }));
    };

    return (
        <section className="settings-page-section">
            <div className="settings-page-section-heading">
                <div>
                    <h2>Notification Settings</h2>
                    <p>
                        Choose the farm notifications and delivery methods you
                        want to receive.
                    </p>
                </div>
            </div>

            <div className="settings-page-toggle-grid">
                <SettingsToggle
                    icon="grass"
                    title="Crop Alerts"
                    description="Planting, growth, harvest, pest, and crop status notifications."
                    checked={settings.cropAlerts}
                    onChange={() => toggleSetting("cropAlerts")}
                />

                <SettingsToggle
                    icon="pets"
                    title="Livestock Alerts"
                    description="Feeding, vaccination, health, and livestock production notifications."
                    checked={settings.livestockAlerts}
                    onChange={() => toggleSetting("livestockAlerts")}
                />

                <SettingsToggle
                    icon="partly_cloudy_day"
                    title="Weather Alerts"
                    description="Heavy rain, high temperature, strong wind, and storm warnings."
                    checked={settings.weatherAlerts}
                    onChange={() => toggleSetting("weatherAlerts")}
                />

                <SettingsToggle
                    icon="inventory_2"
                    title="Inventory Alerts"
                    description="Low stock, expiration, damaged item, and restocking notifications."
                    checked={settings.inventoryAlerts}
                    onChange={() => toggleSetting("inventoryAlerts")}
                />

                <SettingsToggle
                    icon="settings"
                    title="System Alerts"
                    description="Backup, storage, security, login, and maintenance notifications."
                    checked={settings.systemAlerts}
                    onChange={() => toggleSetting("systemAlerts")}
                />

                <SettingsToggle
                    icon="mail"
                    title="Email Notifications"
                    description="Send important farm notifications to the registered email address."
                    checked={settings.emailNotifications}
                    onChange={() => toggleSetting("emailNotifications")}
                />

                <SettingsToggle
                    icon="notifications_active"
                    title="In-App Notifications"
                    description="Display notifications inside the Joross Farm management system."
                    checked={settings.inAppNotifications}
                    onChange={() => toggleSetting("inAppNotifications")}
                />

                <SettingsToggle
                    icon="volume_up"
                    title="Notification Sound"
                    description="Play a sound when a new important notification is received."
                    checked={settings.soundNotifications}
                    onChange={() => toggleSetting("soundNotifications")}
                />
            </div>

            <article className="settings-page-frequency-card">
                <div>
                    <span className="material-symbols-outlined">schedule</span>
                    <div>
                        <h3>Notification Frequency</h3>
                        <p>
                            Choose how often general notification summaries are
                            delivered.
                        </p>
                    </div>
                </div>

                <select
                    value={settings.notificationFrequency}
                    onChange={(event) =>
                        setSettings((current) => ({
                            ...current,
                            notificationFrequency: event.target.value,
                        }))
                    }
                >
                    <option value="Immediate">Immediate</option>
                    <option value="Daily Summary">Daily Summary</option>
                    <option value="Weekly Summary">Weekly Summary</option>
                </select>
            </article>

            <div className="settings-page-section-save">
                <button
                    type="button"
                    className="settings-page-primary-button"
                    onClick={() =>
                        notify("Notification settings saved successfully. Sound preferences now apply to new bell notifications.")
                    }
                >
                    <span className="material-symbols-outlined">save</span>
                    Save Notifications
                </button>
            </div>
        </section>
    );
}
