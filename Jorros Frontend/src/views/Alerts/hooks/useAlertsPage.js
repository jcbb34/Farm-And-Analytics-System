import { notify } from "../../../context/NotificationContext.jsx";
import { useEffect, useMemo, useState } from "react";

import { confirmAction } from "../../../context/NotificationContext.jsx";
import { alertService } from "../../../services/alertService.js";
import { DEFAULT_ALERT_SETTINGS } from "../../../components/AlertSettingsModal/AlertSettingsModal.jsx";

export const ALERT_CATEGORIES = [
    "Crop",
    "Livestock",
    "Inventory",
    "Task",
    "Weather",
    "Report",
    "System",
];

function cloneSettings(settings) {
    return JSON.parse(JSON.stringify(settings));
}

// Loads alert data and keeps page actions in one place.
export default function useAlertsPage() {
    const [alerts, setAlerts] = useState([]);
    const [alertsLoading, setAlertsLoading] = useState(true);
    const [alertsError, setAlertsError] = useState("");
    const [actionBusyId, setActionBusyId] = useState(null);

    const [alertSettings, setAlertSettings] = useState(() =>
        cloneSettings(DEFAULT_ALERT_SETTINGS)
    );

    const [activeTab, setActiveTab] = useState("All Alerts");
    const [searchText, setSearchText] = useState("");
    const [categoryFilter, setCategoryFilter] = useState("All");
    const [statusFilter, setStatusFilter] = useState("All");

    const [alertFormOpen, setAlertFormOpen] = useState(false);
    const [alertSettingsOpen, setAlertSettingsOpen] = useState(false);
    const [editingAlert, setEditingAlert] = useState(null);
    const [viewingAlert, setViewingAlert] = useState(null);

    useEffect(() => {
        let cancelled = false;

        const loadAlertData = async () => {
            setAlertsLoading(true);
            setAlertsError("");

            const [alertsResult, settingsResult] = await Promise.allSettled([
                alertService.getAlerts(),
                alertService.getSettings(),
            ]);

            if (cancelled) return;

            if (alertsResult.status === "fulfilled") {
                setAlerts(alertsResult.value);
            } else {
                console.error("Failed to load alerts:", alertsResult.reason);
                setAlertsError(
                    alertsResult.reason?.message || "Unable to load alert records."
                );
            }

            if (settingsResult.status === "fulfilled") {
                setAlertSettings(settingsResult.value);
            } else {
                console.error(
                    "Failed to load alert settings:",
                    settingsResult.reason
                );
            }

            setAlertsLoading(false);
        };

        loadAlertData();

        return () => {
            cancelled = true;
        };
    }, []);

    const filteredAlerts = useMemo(() => {
        const search = searchText.trim().toLowerCase();

        return alerts.filter((item) => {
            const matchesTab =
                activeTab === "All Alerts" ||
                (activeTab === "Active Alerts" && item.status === "Active") ||
                (activeTab === "High Priority" && item.priority === "High");

            const matchesSearch =
                !search ||
                String(item.alertName || "").toLowerCase().includes(search) ||
                String(item.subject || "").toLowerCase().includes(search) ||
                String(item.category || "").toLowerCase().includes(search) ||
                String(item.alertType || "").toLowerCase().includes(search);

            const matchesCategory =
                categoryFilter === "All" || item.category === categoryFilter;

            const matchesStatus =
                statusFilter === "All" || item.status === statusFilter;

            return matchesTab && matchesSearch && matchesCategory && matchesStatus;
        });
    }, [alerts, activeTab, searchText, categoryFilter, statusFilter]);

    const openAddAlert = () => {
        setEditingAlert(null);
        setAlertFormOpen(true);
    };

    const closeAlertForm = () => {
        setAlertFormOpen(false);
        setEditingAlert(null);
    };

    const openViewAlert = (selectedAlert) => {
        setViewingAlert(selectedAlert);
    };

    const closeViewAlert = () => {
        setViewingAlert(null);
    };

    const openEditAlert = (selectedAlert) => {
        if (selectedAlert.isAutomatic) return;

        setEditingAlert(selectedAlert);
        setAlertFormOpen(true);
    };

    const handleSaveAlert = async (formData) => {
        try {
            setActionBusyId(editingAlert?.id ?? "new");

            if (editingAlert) {
                const updatedAlert = await alertService.updateAlert(
                    editingAlert.id,
                    formData
                );

                setAlerts((currentAlerts) =>
                    currentAlerts.map((item) =>
                        item.id === editingAlert.id ? updatedAlert : item
                    )
                );

                notify("Alert updated successfully.");
            } else {
                const createdAlert = await alertService.createAlert(formData);
                setAlerts((currentAlerts) => [createdAlert, ...currentAlerts]);
                notify("Alert added successfully.");
            }

            closeAlertForm();
        } catch (error) {
            console.error("Failed to save alert:", error);
            notify(error?.message || "Unable to save the alert.");
        } finally {
            setActionBusyId(null);
        }
    };

    const handleSaveSettings = async (newSettings) => {
        try {
            setActionBusyId("settings");

            const savedSettings = await alertService.updateSettings(newSettings);
            setAlertSettings(savedSettings);
            setAlertSettingsOpen(false);
            notify("Alert settings saved successfully.");
        } catch (error) {
            console.error("Failed to save alert settings:", error);
            notify(error?.message || "Unable to save alert settings.");
        } finally {
            setActionBusyId(null);
        }
    };

    const toggleAlertStatus = async (selectedAlert) => {
        if (selectedAlert.isAutomatic) return;

        const nextStatus =
            selectedAlert.status === "Active" ? "Disabled" : "Active";

        try {
            setActionBusyId(selectedAlert.id);

            const updatedAlert = await alertService.updateAlert(selectedAlert.id, {
                status: nextStatus,
            });

            setAlerts((currentAlerts) =>
                currentAlerts.map((item) =>
                    item.id === selectedAlert.id ? updatedAlert : item
                )
            );

            if (viewingAlert?.id === selectedAlert.id) {
                setViewingAlert(updatedAlert);
            }
        } catch (error) {
            console.error("Failed to update alert status:", error);
            notify(error?.message || "Unable to update alert status.");
        } finally {
            setActionBusyId(null);
        }
    };

    const triggerAlert = async (selectedAlert) => {
        if (selectedAlert.isAutomatic) return;

        try {
            setActionBusyId(selectedAlert.id);

            const triggeredAlert = await alertService.triggerAlert(selectedAlert.id);

            setAlerts((currentAlerts) =>
                currentAlerts.map((item) =>
                    item.id === selectedAlert.id ? triggeredAlert : item
                )
            );

            if (viewingAlert?.id === selectedAlert.id) {
                setViewingAlert(triggeredAlert);
            }

            notify("Alert test triggered successfully.");
        } catch (error) {
            console.error("Failed to trigger alert:", error);
            notify(error?.message || "Unable to trigger the alert.");
        } finally {
            setActionBusyId(null);
        }
    };

    const deleteAlert = async (selectedAlert) => {
        if (selectedAlert.isAutomatic) return;

        const confirmed = await confirmAction({
            title: "Delete Alert",
            message: `Delete "${selectedAlert.alertName}"?`,
            type: "error",
            confirmText: "Delete",
            cancelText: "Cancel",
        });

        if (!confirmed) return;

        try {
            setActionBusyId(selectedAlert.id);
            await alertService.deleteAlert(selectedAlert.id);

            setAlerts((currentAlerts) =>
                currentAlerts.filter((item) => item.id !== selectedAlert.id)
            );

            if (viewingAlert?.id === selectedAlert.id) {
                setViewingAlert(null);
            }

            notify(`${selectedAlert.alertName} was deleted successfully.`);
        } catch (error) {
            console.error("Failed to delete alert:", error);
            notify(error?.message || "Unable to delete the alert.");
        } finally {
            setActionBusyId(null);
        }
    };

    const clearFilters = () => {
        setSearchText("");
        setCategoryFilter("All");
        setStatusFilter("All");
    };

    return {
        alerts,
        alertsLoading,
        alertsError,
        actionBusyId,
        alertSettings,
        activeTab,
        setActiveTab,
        searchText,
        setSearchText,
        categoryFilter,
        setCategoryFilter,
        statusFilter,
        setStatusFilter,
        filteredAlerts,
        alertFormOpen,
        alertSettingsOpen,
        setAlertSettingsOpen,
        editingAlert,
        viewingAlert,
        openAddAlert,
        closeAlertForm,
        openViewAlert,
        closeViewAlert,
        openEditAlert,
        handleSaveAlert,
        handleSaveSettings,
        toggleAlertStatus,
        triggerAlert,
        deleteAlert,
        clearFilters,
    };
}
