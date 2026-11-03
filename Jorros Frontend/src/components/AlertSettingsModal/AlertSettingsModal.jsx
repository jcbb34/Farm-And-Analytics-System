"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useState,
} from "react";

import "./AlertSettingsModal.css";

export const DEFAULT_ALERT_SETTINGS = {
    crop: {
        plantingReminder: true,
        growthCheck: true,
        harvestReminder: true,
        pestDiseaseAlert: true,

        harvestAdvanceDays: 7,
        growthCheckFrequency: 7,
        soilMoistureThreshold: 30,
    },

    livestock: {
        feedingReminder: true,
        vaccinationReminder: true,
        healthCheck: true,
        productionCheck: false,

        vaccinationAdvanceDays: 7,
        healthCheckFrequency: 14,
        feedingReminderTime: "06:00",
    },

    weather: {
        heavyRainAlert: true,
        highTemperatureAlert: true,
        strongWindAlert: true,
        thunderstormAlert: true,

        rainfallThreshold: 80,
        temperatureThreshold: 32,
        windSpeedThreshold: 40,
    },

    system: {
        backupReminder: true,
        lowInventoryAlert: true,
        lowStorageAlert: true,
        failedLoginAlert: true,

        backupFrequency: 7,
        storageThreshold: 10,
        failedLoginLimit: 5,
    },
};

const settingTabs = [
    {
        id: "crop",
        label: "Crop Alerts",
        icon: "grass",
    },
    {
        id: "livestock",
        label: "Livestock Alerts",
        icon: "pets",
    },
    {
        id: "inventory",
        label: "Inventory Alerts",
        icon: "inventory_2",
    },
    {
        id: "weather",
        label: "Weather Alerts",
        icon: "partly_cloudy_day",
    },
    {
        id: "system",
        label: "System Alerts",
        icon: "settings",
    },
];

function cloneSettings(settings) {
    return JSON.parse(
        JSON.stringify(settings)
    );
}

function ToggleSetting({
    icon,
    title,
    description,
    checked,
    onChange,
}) {
    return (
        <article className="alert-settings-toggle-card">
            <span className="alert-settings-toggle-icon">
                <span className="material-symbols-outlined">
                    {icon}
                </span>
            </span>

            <div className="alert-settings-toggle-content">
                <strong>
                    {title}
                </strong>

                <p>
                    {description}
                </p>
            </div>

            <button
                type="button"
                role="switch"
                aria-checked={checked}
                className={`alert-settings-switch ${
                    checked
                        ? "enabled"
                        : ""
                }`}
                onClick={onChange}
            >
                <span />
            </button>
        </article>
    );
}

function AlertSettingsModal({
    open,
    settings,
    onClose,
    onSave,
}) {
    const [
        activeTab,
        setActiveTab,
    ] = useState("crop");

    const [
        draftSettings,
        setDraftSettings,
    ] = useState(
        cloneSettings(
            DEFAULT_ALERT_SETTINGS
        )
    );

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        setActiveTab("crop");

        setDraftSettings(
            cloneSettings(
                settings ||
                    DEFAULT_ALERT_SETTINGS
            )
        );

        document.body.style.overflow =
            "hidden";

        const handleEscape = (
            event
        ) => {
            if (
                event.key === "Escape"
            ) {
                onClose();
            }
        };

        document.addEventListener(
            "keydown",
            handleEscape
        );

        return () => {
            document.body.style.overflow =
                "";

            document.removeEventListener(
                "keydown",
                handleEscape
            );
        };
    }, [open, settings, onClose]);

    if (!open) {
        return null;
    }

    const toggleSetting = (
        section,
        field
    ) => {
        setDraftSettings(
            (currentSettings) => ({
                ...currentSettings,

                [section]: {
                    ...currentSettings[
                        section
                    ],

                    [field]:
                        !currentSettings[
                            section
                        ][field],
                },
            })
        );
    };

    const updateSetting = (
        section,
        field,
        value
    ) => {
        setDraftSettings(
            (currentSettings) => ({
                ...currentSettings,

                [section]: {
                    ...currentSettings[
                        section
                    ],

                    [field]: value,
                },
            })
        );
    };

    const handleSave = () => {
        const normalizedSettings = {
            crop: {
                ...draftSettings.crop,

                harvestAdvanceDays:
                    Number(
                        draftSettings.crop
                            .harvestAdvanceDays
                    ),

                growthCheckFrequency:
                    Number(
                        draftSettings.crop
                            .growthCheckFrequency
                    ),

                soilMoistureThreshold:
                    Number(
                        draftSettings.crop
                            .soilMoistureThreshold
                    ),
            },

            livestock: {
                ...draftSettings.livestock,

                vaccinationAdvanceDays:
                    Number(
                        draftSettings
                            .livestock
                            .vaccinationAdvanceDays
                    ),

                healthCheckFrequency:
                    Number(
                        draftSettings
                            .livestock
                            .healthCheckFrequency
                    ),
            },

            weather: {
                ...draftSettings.weather,

                rainfallThreshold:
                    Number(
                        draftSettings.weather
                            .rainfallThreshold
                    ),

                temperatureThreshold:
                    Number(
                        draftSettings.weather
                            .temperatureThreshold
                    ),

                windSpeedThreshold:
                    Number(
                        draftSettings.weather
                            .windSpeedThreshold
                    ),
            },

            system: {
                ...draftSettings.system,

                backupFrequency:
                    Number(
                        draftSettings.system
                            .backupFrequency
                    ),

                storageThreshold:
                    Number(
                        draftSettings.system
                            .storageThreshold
                    ),

                failedLoginLimit:
                    Number(
                        draftSettings.system
                            .failedLoginLimit
                    ),
            },
        };

        const numericValues = [
            normalizedSettings.crop
                .harvestAdvanceDays,

            normalizedSettings.crop
                .growthCheckFrequency,

            normalizedSettings.crop
                .soilMoistureThreshold,

            normalizedSettings.livestock
                .vaccinationAdvanceDays,

            normalizedSettings.livestock
                .healthCheckFrequency,

            normalizedSettings.weather
                .rainfallThreshold,

            normalizedSettings.weather
                .temperatureThreshold,

            normalizedSettings.weather
                .windSpeedThreshold,

            normalizedSettings.system
                .backupFrequency,

            normalizedSettings.system
                .storageThreshold,

            normalizedSettings.system
                .failedLoginLimit,
        ];

        const invalidValue =
            numericValues.some(
                (value) =>
                    Number.isNaN(value) ||
                    value < 0
            );

        if (invalidValue) {
            notify(
                "Alert thresholds and frequencies must contain valid numbers."
            );

            return;
        }

        if (
            normalizedSettings.crop
                .soilMoistureThreshold >
                100 ||
            normalizedSettings.system
                .storageThreshold >
                100
        ) {
            notify(
                "Percentage thresholds cannot be greater than 100."
            );

            return;
        }

        onSave(
            normalizedSettings
        );
    };

    return (
        <div
            className="alert-settings-overlay"
            onMouseDown={onClose}
        >
            <div
                className="alert-settings-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="alert-settings-header">
                    <div>
                        <h2>
                            Alert Settings
                        </h2>

                        <p>
                            Configure important
                            crop, livestock,
                            inventory, weather,
                            and system notifications.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close alert settings"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="alert-settings-layout">
                    <nav className="alert-settings-tabs">
                        {settingTabs.map(
                            (tab) => (
                                <button
                                    type="button"
                                    key={tab.id}
                                    className={
                                        activeTab ===
                                        tab.id
                                            ? "active"
                                            : ""
                                    }
                                    onClick={() =>
                                        setActiveTab(
                                            tab.id
                                        )
                                    }
                                >
                                    <span className="material-symbols-outlined">
                                        {tab.icon}
                                    </span>

                                    <span>
                                        {tab.label}
                                    </span>
                                </button>
                            )
                        )}
                    </nav>

                    <div className="alert-settings-body">
                        {activeTab ===
                            "crop" && (
                            <section>
                                <div className="alert-settings-section-heading">
                                    <span className="material-symbols-outlined">
                                        grass
                                    </span>

                                    <div>
                                        <h3>
                                            Crop Alert
                                            Settings
                                        </h3>

                                        <p>
                                            Control
                                            reminders and
                                            important crop
                                            monitoring
                                            alerts.
                                        </p>
                                    </div>
                                </div>

                                <div className="alert-settings-toggle-list">
                                    <ToggleSetting
                                        icon="event_note"
                                        title="Planting Reminder"
                                        description="Notify farm personnel about scheduled planting activities."
                                        checked={
                                            draftSettings
                                                .crop
                                                .plantingReminder
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "crop",
                                                "plantingReminder"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="monitoring"
                                        title="Growth Check"
                                        description="Remind personnel to record and update crop growth."
                                        checked={
                                            draftSettings
                                                .crop
                                                .growthCheck
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "crop",
                                                "growthCheck"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="agriculture"
                                        title="Harvest Reminder"
                                        description="Notify personnel before the expected crop harvest date."
                                        checked={
                                            draftSettings
                                                .crop
                                                .harvestReminder
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "crop",
                                                "harvestReminder"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="pest_control"
                                        title="Pest and Disease Alert"
                                        description="Notify personnel when pests or diseases are recorded."
                                        checked={
                                            draftSettings
                                                .crop
                                                .pestDiseaseAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "crop",
                                                "pestDiseaseAlert"
                                            )
                                        }
                                    />
                                </div>

                                <div className="alert-settings-fields-card">
                                    <h4>
                                        Crop Thresholds
                                        and Frequency
                                    </h4>

                                    <div className="alert-settings-field-grid">
                                        <div className="alert-settings-field">
                                            <label htmlFor="harvestAdvanceDays">
                                                Harvest
                                                reminder
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="harvestAdvanceDays"
                                                    type="number"
                                                    min="0"
                                                    value={
                                                        draftSettings
                                                            .crop
                                                            .harvestAdvanceDays
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "crop",
                                                            "harvestAdvanceDays",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    days
                                                    before
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="growthCheckFrequency">
                                                Growth
                                                check
                                                frequency
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="growthCheckFrequency"
                                                    type="number"
                                                    min="1"
                                                    value={
                                                        draftSettings
                                                            .crop
                                                            .growthCheckFrequency
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "crop",
                                                            "growthCheckFrequency",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    days
                                                </span>
                                            </div>
                                        </div>

                                    </div>
                                </div>
                            </section>
                        )}

                        {activeTab ===
                            "livestock" && (
                            <section>
                                <div className="alert-settings-section-heading">
                                    <span className="material-symbols-outlined">
                                        pets
                                    </span>

                                    <div>
                                        <h3>
                                            Livestock
                                            Alert Settings
                                        </h3>

                                        <p>
                                            Configure
                                            feeding,
                                            vaccination,
                                            health, and
                                            production
                                            reminders.
                                        </p>
                                    </div>
                                </div>

                                <div className="alert-settings-toggle-list">
                                    <ToggleSetting
                                        icon="nutrition"
                                        title="Feeding Reminder"
                                        description="Notify personnel when livestock feeding is scheduled."
                                        checked={
                                            draftSettings
                                                .livestock
                                                .feedingReminder
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "livestock",
                                                "feedingReminder"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="vaccines"
                                        title="Vaccination Reminder"
                                        description="Notify personnel before the next vaccination date."
                                        checked={
                                            draftSettings
                                                .livestock
                                                .vaccinationReminder
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "livestock",
                                                "vaccinationReminder"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="health_and_safety"
                                        title="Health Check"
                                        description="Remind personnel to check and update livestock health."
                                        checked={
                                            draftSettings
                                                .livestock
                                                .healthCheck
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "livestock",
                                                "healthCheck"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="production_quantity_limits"
                                        title="Production Check"
                                        description="Notify personnel to record livestock production output."
                                        checked={
                                            draftSettings
                                                .livestock
                                                .productionCheck
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "livestock",
                                                "productionCheck"
                                            )
                                        }
                                    />
                                </div>

                                <div className="alert-settings-fields-card">
                                    <h4>
                                        Livestock
                                        Schedule
                                    </h4>

                                    <div className="alert-settings-field-grid">
                                        <div className="alert-settings-field">
                                            <label htmlFor="vaccinationAdvanceDays">
                                                Vaccination
                                                reminder
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="vaccinationAdvanceDays"
                                                    type="number"
                                                    min="0"
                                                    value={
                                                        draftSettings
                                                            .livestock
                                                            .vaccinationAdvanceDays
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "livestock",
                                                            "vaccinationAdvanceDays",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    days
                                                    before
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="healthCheckFrequency">
                                                Health
                                                check
                                                frequency
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="healthCheckFrequency"
                                                    type="number"
                                                    min="1"
                                                    value={
                                                        draftSettings
                                                            .livestock
                                                            .healthCheckFrequency
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "livestock",
                                                            "healthCheckFrequency",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    days
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="feedingReminderTime">
                                                Feeding
                                                reminder
                                                time
                                            </label>

                                            <input
                                                id="feedingReminderTime"
                                                type="time"
                                                value={
                                                    draftSettings
                                                        .livestock
                                                        .feedingReminderTime
                                                }
                                                onChange={(
                                                    event
                                                ) =>
                                                    updateSetting(
                                                        "livestock",
                                                        "feedingReminderTime",
                                                        event
                                                            .target
                                                            .value
                                                    )
                                                }
                                            />
                                        </div>
                                    </div>
                                </div>
                            </section>
                        )}

                        {activeTab ===
                            "inventory" && (
                            <section>
                                <div className="alert-settings-section-heading">
                                    <span className="material-symbols-outlined">
                                        inventory_2
                                    </span>

                                    <div>
                                        <h3>
                                            Inventory Alert Settings
                                        </h3>

                                        <p>
                                            Control source-driven stock alerts from the Inventory module.
                                        </p>
                                    </div>
                                </div>

                                <div className="alert-settings-toggle-list">
                                    <ToggleSetting
                                        icon="inventory_2"
                                        title="Low Inventory Alert"
                                        description="Create one alert when an item reaches or falls below its reorder level. The alert resolves automatically after stock is replenished."
                                        checked={
                                            draftSettings
                                                .system
                                                .lowInventoryAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "system",
                                                "lowInventoryAlert"
                                            )
                                        }
                                    />
                                </div>

                                <div className="alert-settings-fields-card">
                                    <h4>
                                        Automatic Resolution
                                    </h4>

                                    <p>
                                        Low-stock alerts are condition-based. They cannot be manually marked fixed; replenishing the exact Inventory item above its reorder level resolves the alert automatically.
                                    </p>
                                </div>
                            </section>
                        )}

                        {activeTab ===
                            "weather" && (
                            <section>
                                <div className="alert-settings-section-heading">
                                    <span className="material-symbols-outlined">
                                        partly_cloudy_day
                                    </span>

                                    <div>
                                        <h3>
                                            Weather Alert
                                            Settings
                                        </h3>

                                        <p>
                                            Configure
                                            important
                                            weather
                                            warnings for
                                            farm operations.
                                        </p>
                                    </div>
                                </div>

                                <div className="alert-settings-toggle-list">
                                    <ToggleSetting
                                        icon="rainy"
                                        title="Heavy Rain Alert"
                                        description="Notify personnel when rainfall exceeds the configured threshold."
                                        checked={
                                            draftSettings
                                                .weather
                                                .heavyRainAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "weather",
                                                "heavyRainAlert"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="thermostat"
                                        title="High Temperature Alert"
                                        description="Notify personnel when farm temperature becomes too high."
                                        checked={
                                            draftSettings
                                                .weather
                                                .highTemperatureAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "weather",
                                                "highTemperatureAlert"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="air"
                                        title="Strong Wind Alert"
                                        description="Notify personnel when wind speed may affect crops or facilities."
                                        checked={
                                            draftSettings
                                                .weather
                                                .strongWindAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "weather",
                                                "strongWindAlert"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="thunderstorm"
                                        title="Thunderstorm Alert"
                                        description="Notify personnel when a thunderstorm is expected."
                                        checked={
                                            draftSettings
                                                .weather
                                                .thunderstormAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "weather",
                                                "thunderstormAlert"
                                            )
                                        }
                                    />
                                </div>

                                <div className="alert-settings-fields-card">
                                    <h4>
                                        Weather
                                        Thresholds
                                    </h4>

                                    <div className="alert-settings-field-grid">
                                        <div className="alert-settings-field">
                                            <label htmlFor="rainfallThreshold">
                                                Heavy
                                                rainfall
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="rainfallThreshold"
                                                    type="number"
                                                    min="0"
                                                    value={
                                                        draftSettings
                                                            .weather
                                                            .rainfallThreshold
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "weather",
                                                            "rainfallThreshold",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    mm/day
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="temperatureThreshold">
                                                High
                                                temperature
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="temperatureThreshold"
                                                    type="number"
                                                    min="0"
                                                    value={
                                                        draftSettings
                                                            .weather
                                                            .temperatureThreshold
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "weather",
                                                            "temperatureThreshold",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    °C
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="windSpeedThreshold">
                                                Strong
                                                wind
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="windSpeedThreshold"
                                                    type="number"
                                                    min="0"
                                                    value={
                                                        draftSettings
                                                            .weather
                                                            .windSpeedThreshold
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "weather",
                                                            "windSpeedThreshold",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    km/h
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        )}

                        {activeTab ===
                            "system" && (
                            <section>
                                <div className="alert-settings-section-heading">
                                    <span className="material-symbols-outlined">
                                        settings
                                    </span>

                                    <div>
                                        <h3>
                                            System Alert
                                            Settings
                                        </h3>

                                        <p>
                                            Configure
                                            security,
                                            storage, and
                                            backup
                                            notifications.
                                        </p>
                                    </div>
                                </div>

                                <div className="alert-settings-toggle-list">
                                    <ToggleSetting
                                        icon="backup"
                                        title="Backup Reminder"
                                        description="Remind the administrator to create a system backup."
                                        checked={
                                            draftSettings
                                                .system
                                                .backupReminder
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "system",
                                                "backupReminder"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="storage"
                                        title="Low Storage Alert"
                                        description="Notify the administrator when system storage becomes low."
                                        checked={
                                            draftSettings
                                                .system
                                                .lowStorageAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "system",
                                                "lowStorageAlert"
                                            )
                                        }
                                    />

                                    <ToggleSetting
                                        icon="security"
                                        title="Failed Login Alert"
                                        description="Notify the administrator about repeated failed login attempts."
                                        checked={
                                            draftSettings
                                                .system
                                                .failedLoginAlert
                                        }
                                        onChange={() =>
                                            toggleSetting(
                                                "system",
                                                "failedLoginAlert"
                                            )
                                        }
                                    />
                                </div>

                                <div className="alert-settings-fields-card">
                                    <h4>
                                        System
                                        Thresholds
                                    </h4>

                                    <div className="alert-settings-field-grid">
                                        <div className="alert-settings-field">
                                            <label htmlFor="backupFrequency">
                                                Backup
                                                reminder
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="backupFrequency"
                                                    type="number"
                                                    min="1"
                                                    value={
                                                        draftSettings
                                                            .system
                                                            .backupFrequency
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "system",
                                                            "backupFrequency",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    days
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="storageThreshold">
                                                Low storage
                                                warning
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="storageThreshold"
                                                    type="number"
                                                    min="0"
                                                    max="100"
                                                    value={
                                                        draftSettings
                                                            .system
                                                            .storageThreshold
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "system",
                                                            "storageThreshold",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    %
                                                    remaining
                                                </span>
                                            </div>
                                        </div>

                                        <div className="alert-settings-field">
                                            <label htmlFor="failedLoginLimit">
                                                Failed
                                                login
                                                limit
                                            </label>

                                            <div className="alert-settings-unit-input">
                                                <input
                                                    id="failedLoginLimit"
                                                    type="number"
                                                    min="1"
                                                    value={
                                                        draftSettings
                                                            .system
                                                            .failedLoginLimit
                                                    }
                                                    onChange={(
                                                        event
                                                    ) =>
                                                        updateSetting(
                                                            "system",
                                                            "failedLoginLimit",
                                                            event
                                                                .target
                                                                .value
                                                        )
                                                    }
                                                />

                                                <span>
                                                    attempts
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </section>
                        )}
                    </div>
                </div>

                <footer className="alert-settings-footer">
                    <button
                        type="button"
                        className="alert-settings-cancel"
                        onClick={onClose}
                    >
                        Cancel
                    </button>

                    <button
                        type="button"
                        className="alert-settings-save"
                        onClick={
                            handleSave
                        }
                    >
                        <span className="material-symbols-outlined">
                            save
                        </span>

                        Save Settings
                    </button>
                </footer>
            </div>
        </div>
    );
}

export default AlertSettingsModal;
