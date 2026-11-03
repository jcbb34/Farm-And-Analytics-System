import { httpClient } from "./httpClient.js";

// Lets the header bell refresh immediately after an alert changes.
function notifyAlertsUpdated(detail = {}) {
    if (typeof window === "undefined") {
        return;
    }

    window.dispatchEvent(
        new CustomEvent("joross:alerts-updated", {
            detail,
        })
    );
}

function getScheduleParts(value) {
    const text = String(value || "").trim();
    const match = text.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/);

    return {
        scheduleDate: match?.[1] || "",
        scheduleTime: match?.[2] || "",
    };
}

function getScheduledFields(data = {}) {
    const scheduleDate = String(data.scheduleDate || "").trim();
    const scheduleTime = String(data.scheduleTime || "").trim();

    if (!scheduleDate || !scheduleTime) {
        return null;
    }

    return {
        condition: "Scheduled",
        threshold: `${scheduleDate}T${scheduleTime}:00`,
        unit:
            data.repeat && data.repeat !== "None"
                ? data.repeat
                : null,
    };
}

function normalizeAlert(record = {}) {
    return {
        id: record.id,

        alertName:
            record.alertName ??
            record.alert_name ??
            "",

        category:
            record.category ??
            "System",

        subject:
            record.subject ??
            "",

        alertType:
            record.alertType ??
            record.alert_type ??
            "",

        condition:
            record.condition ??
            "Within",

        threshold:
            String(
                record.threshold ??
                    ""
            ),

        unit:
            record.unit ??
            "",

        priority:
            record.priority ??
            "Medium",

        status:
            record.status ??
            "Active",

        description:
            record.description ??
            "",

        lastTriggered:
            record.lastTriggered ??
            record.last_triggered ??
            null,

        // System alerts are created by the automatic alert engine.
        isAutomatic:
            Boolean(
                record.isAutomatic ??
                    record.is_automatic ??
                    false
            ),

        sourceType:
            record.sourceType ??
            record.source_type ??
            null,

        sourceId:
            record.sourceId ??
            record.source_id ??
            null,

        source:
            Boolean(
                record.isAutomatic ??
                    record.is_automatic ??
                    false
            )
                ? "System"
                : "Manual",

        // Manual schedules are stored in the existing condition fields.
        ...getScheduleParts(
            String(record.condition || "") === "Scheduled"
                ? record.threshold
                : ""
        ),

        repeat:
            String(record.condition || "") === "Scheduled"
                ? record.unit || "None"
                : "None",

        createdByUserId:
            record.createdByUserId ??
            record.created_by_user_id ??
            null,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,

        updatedAt:
            record.updatedAt ??
            record.updated_at ??
            null,
    };
}

function createAlertPayload(data = {}) {
    const scheduled = getScheduledFields(data);

    return {
        alert_name:
            data.alertName?.trim() ??
            "",

        category:
            data.category ??
            "System",

        subject:
            data.subject?.trim() ??
            "",

        alert_type:
            data.alertType?.trim() ??
            "",

        condition:
            scheduled?.condition ??
            data.condition ??
            "Within",

        threshold:
            scheduled?.threshold ??
            String(
                data.threshold ??
                    ""
            ).trim(),

        unit:
            scheduled
                ? scheduled.unit
                : data.unit?.trim() || null,

        priority:
            data.priority ??
            "Medium",

        status:
            data.status ??
            "Active",

        description:
            data.description?.trim() ||
            null,

        source_type:
            data.sourceType?.trim() || null,

        source_id:
            data.sourceId ? Number(data.sourceId) : null,
    };
}

// Updates only send fields that actually changed.
function createAlertUpdatePayload(data = {}) {
    const payload = {};
    const scheduled = getScheduledFields(data);

    if (scheduled) {
        payload.condition = scheduled.condition;
        payload.threshold = scheduled.threshold;
        payload.unit = scheduled.unit;
    }

    if (data.alertName !== undefined) {
        payload.alert_name =
            data.alertName?.trim() ?? "";
    }

    if (data.category !== undefined) {
        payload.category = data.category;
    }

    if (data.subject !== undefined) {
        payload.subject =
            data.subject?.trim() ?? "";
    }

    if (data.alertType !== undefined) {
        payload.alert_type =
            data.alertType?.trim() ?? "";
    }

    if (!scheduled && data.condition !== undefined) {
        payload.condition = data.condition;
    }

    if (!scheduled && data.threshold !== undefined) {
        payload.threshold = String(
            data.threshold ?? ""
        ).trim();
    }

    if (!scheduled && data.unit !== undefined) {
        payload.unit =
            data.unit?.trim() || null;
    }

    if (data.priority !== undefined) {
        payload.priority = data.priority;
    }

    if (data.status !== undefined) {
        payload.status = data.status;
    }

    if (data.description !== undefined) {
        payload.description =
            data.description?.trim() || null;
    }

    if (data.sourceType !== undefined) {
        payload.source_type =
            data.sourceType?.trim() || null;
    }

    if (data.sourceId !== undefined) {
        payload.source_id =
            data.sourceId ? Number(data.sourceId) : null;
    }

    return payload;
}

function normalizeSettings(response = {}) {
    const crop = response.crop ?? {};
    const livestock =
        response.livestock ?? {};
    const weather =
        response.weather ?? {};
    const system =
        response.system ?? {};

    return {
        crop: {
            plantingReminder:
                crop.plantingReminder ??
                crop.planting_reminder ??
                true,

            growthCheck:
                crop.growthCheck ??
                crop.growth_check ??
                true,

            harvestReminder:
                crop.harvestReminder ??
                crop.harvest_reminder ??
                true,

            pestDiseaseAlert:
                crop.pestDiseaseAlert ??
                crop.pest_disease_alert ??
                true,

            harvestAdvanceDays:
                Number(
                    crop.harvestAdvanceDays ??
                        crop.harvest_advance_days ??
                        7
                ),

            growthCheckFrequency:
                Number(
                    crop.growthCheckFrequency ??
                        crop.growth_check_frequency ??
                        7
                ),

            soilMoistureThreshold:
                Number(
                    crop.soilMoistureThreshold ??
                        crop.soil_moisture_threshold ??
                        30
                ),
        },

        livestock: {
            feedingReminder:
                livestock.feedingReminder ??
                livestock.feeding_reminder ??
                true,

            vaccinationReminder:
                livestock.vaccinationReminder ??
                livestock.vaccination_reminder ??
                true,

            healthCheck:
                livestock.healthCheck ??
                livestock.health_check ??
                true,

            productionCheck:
                livestock.productionCheck ??
                livestock.production_check ??
                false,

            vaccinationAdvanceDays:
                Number(
                    livestock.vaccinationAdvanceDays ??
                        livestock.vaccination_advance_days ??
                        7
                ),

            healthCheckFrequency:
                Number(
                    livestock.healthCheckFrequency ??
                        livestock.health_check_frequency ??
                        14
                ),

            feedingReminderTime:
                livestock.feedingReminderTime ??
                livestock.feeding_reminder_time ??
                "06:00",
        },

        weather: {
            heavyRainAlert:
                weather.heavyRainAlert ??
                weather.heavy_rain_alert ??
                true,

            highTemperatureAlert:
                weather.highTemperatureAlert ??
                weather.high_temperature_alert ??
                true,

            strongWindAlert:
                weather.strongWindAlert ??
                weather.strong_wind_alert ??
                true,

            thunderstormAlert:
                weather.thunderstormAlert ??
                weather.thunderstorm_alert ??
                true,

            rainfallThreshold:
                Number(
                    weather.rainfallThreshold ??
                        weather.rainfall_threshold ??
                        80
                ),

            temperatureThreshold:
                Number(
                    weather.temperatureThreshold ??
                        weather.temperature_threshold ??
                        32
                ),

            windSpeedThreshold:
                Number(
                    weather.windSpeedThreshold ??
                        weather.wind_speed_threshold ??
                        40
                ),
        },

        system: {
            backupReminder:
                system.backupReminder ??
                system.backup_reminder ??
                true,

            lowInventoryAlert:
                system.lowInventoryAlert ??
                system.low_inventory_alert ??
                true,

            lowStorageAlert:
                system.lowStorageAlert ??
                system.low_storage_alert ??
                true,

            failedLoginAlert:
                system.failedLoginAlert ??
                system.failed_login_alert ??
                true,

            backupFrequency:
                Number(
                    system.backupFrequency ??
                        system.backup_frequency ??
                        7
                ),

            storageThreshold:
                Number(
                    system.storageThreshold ??
                        system.storage_threshold ??
                        10
                ),

            failedLoginLimit:
                Number(
                    system.failedLoginLimit ??
                        system.failed_login_limit ??
                        5
                ),
        },
    };
}

function createSettingsPayload(settings = {}) {
    const crop = settings.crop ?? {};
    const livestock =
        settings.livestock ?? {};
    const weather =
        settings.weather ?? {};
    const system =
        settings.system ?? {};

    return {
        crop: {
            planting_reminder:
                Boolean(
                    crop.plantingReminder
                ),

            growth_check:
                Boolean(
                    crop.growthCheck
                ),

            harvest_reminder:
                Boolean(
                    crop.harvestReminder
                ),

            pest_disease_alert:
                Boolean(
                    crop.pestDiseaseAlert
                ),

            harvest_advance_days:
                Number(
                    crop.harvestAdvanceDays ??
                        7
                ),

            growth_check_frequency:
                Number(
                    crop.growthCheckFrequency ??
                        7
                ),

            soil_moisture_threshold:
                Number(
                    crop.soilMoistureThreshold ??
                        30
                ),
        },

        livestock: {
            feeding_reminder:
                Boolean(
                    livestock.feedingReminder
                ),

            vaccination_reminder:
                Boolean(
                    livestock.vaccinationReminder
                ),

            health_check:
                Boolean(
                    livestock.healthCheck
                ),

            production_check:
                Boolean(
                    livestock.productionCheck
                ),

            vaccination_advance_days:
                Number(
                    livestock.vaccinationAdvanceDays ??
                        7
                ),

            health_check_frequency:
                Number(
                    livestock.healthCheckFrequency ??
                        14
                ),

            feeding_reminder_time:
                livestock.feedingReminderTime ||
                "06:00",
        },

        weather: {
            heavy_rain_alert:
                Boolean(
                    weather.heavyRainAlert
                ),

            high_temperature_alert:
                Boolean(
                    weather.highTemperatureAlert
                ),

            strong_wind_alert:
                Boolean(
                    weather.strongWindAlert
                ),

            thunderstorm_alert:
                Boolean(
                    weather.thunderstormAlert
                ),

            rainfall_threshold:
                Number(
                    weather.rainfallThreshold ??
                        80
                ),

            temperature_threshold:
                Number(
                    weather.temperatureThreshold ??
                        32
                ),

            wind_speed_threshold:
                Number(
                    weather.windSpeedThreshold ??
                        40
                ),
        },

        system: {
            backup_reminder:
                Boolean(
                    system.backupReminder
                ),

            low_inventory_alert:
                Boolean(
                    system.lowInventoryAlert
                ),

            low_storage_alert:
                Boolean(
                    system.lowStorageAlert
                ),

            failed_login_alert:
                Boolean(
                    system.failedLoginAlert
                ),

            backup_frequency:
                Number(
                    system.backupFrequency ??
                        7
                ),

            storage_threshold:
                Number(
                    system.storageThreshold ??
                        10
                ),

            failed_login_limit:
                Number(
                    system.failedLoginLimit ??
                        5
                ),
        },
    };
}

export const alertService = Object.freeze({
    async getAlertPage(options = {}) {
        const result = await httpClient.get("/alerts/page", { query: options });
        return { ...result, items: (result.items || []).map(normalizeAlert) };
    },
    getAlertSummary() {
        return httpClient.get("/alerts/summary");
    },
    async getNotificationPreview() {
        const rows = await httpClient.get("/alerts/notification-preview", { query: { limit: 30 } });
        return (rows || []).map(normalizeAlert);
    },
    async getAlerts() {
        const response =
            await httpClient.get(
                "/alerts"
            );

        const records =
            Array.isArray(response)
                ? response
                : response?.data ?? [];

        return records.map(
            normalizeAlert
        );
    },

    async getAlert(alertId) {
        const response =
            await httpClient.get(
                `/alerts/${alertId}`
            );

        return normalizeAlert(
            response?.data ??
                response
        );
    },

    async createAlert(data) {
        const response =
            await httpClient.post(
                "/alerts",
                createAlertPayload(
                    data
                )
            );

        const createdAlert = normalizeAlert(
            response?.data ??
                response
        );

        notifyAlertsUpdated({
            action: "created",
            alert: createdAlert,
        });

        return createdAlert;
    },

    async updateAlert(
        alertId,
        data
    ) {
        const response =
            await httpClient.put(
                `/alerts/${alertId}`,
                createAlertUpdatePayload(
                    data
                )
            );

        const updatedAlert = normalizeAlert(
            response?.data ??
                response
        );

        notifyAlertsUpdated({
            action: "updated",
            alert: updatedAlert,
        });

        return updatedAlert;
    },

    async triggerAlert(alertId) {
        const response =
            await httpClient.post(
                `/alerts/${alertId}/trigger`,
                {}
            );

        const triggeredAlert = normalizeAlert(
            response?.data ??
                response
        );

        notifyAlertsUpdated({
            action: "triggered",
            alert: triggeredAlert,
        });

        return triggeredAlert;
    },

    async deleteAlert(alertId) {
        await httpClient.delete(
            `/alerts/${alertId}`
        );

        notifyAlertsUpdated({
            action: "deleted",
            alertId,
        });
    },

    async getSettings() {
        const response =
            await httpClient.get(
                "/alerts/settings"
            );

        return normalizeSettings(
            response?.data ??
                response
        );
    },

    async updateSettings(settings) {
        const response =
            await httpClient.put(
                "/alerts/settings",
                createSettingsPayload(
                    settings
                )
            );

        const savedSettings = normalizeSettings(
            response?.data ??
                response
        );

        notifyAlertsUpdated({
            action: "settings-updated",
        });

        return savedSettings;
    },
});
