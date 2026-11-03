"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useCallback,
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import { eventCreatePath } from "../../components/FarmEvents/eventView.js";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";

import { confirmAction } from "../../context/NotificationContext.jsx";

import { alertService } from "../../services/alertService.js";
import { cropService } from "../../services/cropService.js";
import { livestockService } from "../../services/livestockService.js";
import { inventoryService } from "../../services/inventoryService.js";

import AlertSettingsModal, {
    DEFAULT_ALERT_SETTINGS,
} from "../../components/AlertSettingsModal/AlertSettingsModal.jsx";

import "./Alerts.css";

const categories = [
    "Crop",
    "Livestock",
    "Inventory",
    "Production & Sales",
    "Weather",
    "System",
];

const priorities = [
    "Low",
    "Medium",
    "High",
    "Critical",
];

const repeatOptions = [
    "None",
    "Daily",
    "Weekly",
    "Monthly",
];

const alertTypes = {
    Crop: [
        "Planting Reminder",
        "Growth Check",
        "Harvest Reminder",
        "Pest Detection",
    ],

    Livestock: [
        "Feeding Reminder",
        "Vaccination Reminder",
        "Health Check",
        "Weight Check",
        "Production Check",
    ],

    Inventory: [
        "Restock Reminder",
        "Stock Check",
        "Expiration Reminder",
        "Feed Stock Reminder",
    ],

    "Production & Sales": [
        "Outstanding Receivable",
        "Production Follow-up",
        "Sales Follow-up",
    ],

    Weather: [
        "Heavy Rain",
        "High Temperature",
        "Strong Wind",
        "Thunderstorm",
    ],

    System: [
        "Backup Reminder",
        "Low Inventory",
        "Low Storage",
        "Failed Login",
        "System Maintenance",
    ],
};

function cloneSettings(settings) {
    return JSON.parse(
        JSON.stringify(settings)
    );
}

function formatDateTime(value) {
    if (!value) {
        return "Not triggered";
    }

    const date = new Date(value);

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return "Not triggered";
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


function formatManualSchedule(alert = {}) {
    const dateValue = alert.scheduleDate || "";
    const timeValue = alert.scheduleTime || "";

    if (!dateValue || !timeValue) {
        return "Schedule not set";
    }

    const date = new Date(`${dateValue}T${timeValue}:00`);
    if (Number.isNaN(date.getTime())) {
        return "Schedule not set";
    }

    const formatted = date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });

    return alert.repeat && alert.repeat !== "None"
        ? `${alert.repeat} • ${date.toLocaleTimeString("en-US", {
              hour: "numeric",
              minute: "2-digit",
          })} • starts ${date.toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
              year: "numeric",
          })}`
        : formatted;
}

function getScheduleOrCondition(alert = {}) {
    if (!alert.isAutomatic && alert.condition === "Scheduled") {
        return formatManualSchedule(alert);
    }

    return [alert.condition, alert.threshold, alert.unit]
        .filter(Boolean)
        .join(" ");
}

function getClassName(value = "") {
    return String(value)
        .toLowerCase()
        .replaceAll(" ", "-")
        .replaceAll("/", "-");
}

function getCategoryIcon(category) {
    const icons = {
        Crop: "grass",
        Livestock: "pets",
        Inventory: "inventory_2",
        "Production & Sales": "point_of_sale",
        Weather:
            "partly_cloudy_day",
        System: "settings",
    };

    return (
        icons[category] ||
        "notifications"
    );
}

const HISTORY_STATUSES = [
    "Resolved",
    "Completed",
    "Disabled",
];

function getHistoryReason(alert = {}) {
    if (alert.status === "Completed") {
        return "One-time scheduled alert triggered and finished.";
    }

    if (alert.status === "Disabled") {
        return alert.isAutomatic
            ? "Older automatic alert that is no longer active."
            : "Disabled manually by a user.";
    }

    const sourceType = String(alert.sourceType || "").toLowerCase();

    if (sourceType === "activity_task") {
        return "Task completed, cancelled, archived, rescheduled, or is no longer due.";
    }
    if (sourceType === "inventory_low_stock") {
        return "Inventory stock returned above its reorder level.";
    }
    if (sourceType === "production_sale_receivable") {
        return "The sale balance was fully paid or the sale was voided.";
    }
    if (sourceType === "crop_pest_disease") {
        return "The pest or disease record is no longer active.";
    }
    if (sourceType === "crop_harvest") {
        return "The crop no longer meets the harvest-alert condition.";
    }
    if (sourceType === "livestock_vaccination") {
        return "The vaccination schedule was updated or is no longer due.";
    }
    if (sourceType === "livestock_health") {
        return "Livestock health no longer meets the alert condition.";
    }
    if (sourceType === "livestock_health_check") {
        return "The livestock health-check schedule was updated.";
    }
    if (sourceType.startsWith("weather_")) {
        return "The monitored weather condition cleared.";
    }
    if (sourceType === "system_failed_login") {
        return "The failed-login alert condition cleared.";
    }
    if (sourceType === "system_low_storage") {
        return "Available server storage returned above the threshold.";
    }

    return "The monitored condition is no longer active.";
}

function historyDateMatches(value, period) {
    if (period === "All") {
        return true;
    }

    const date = value ? new Date(value) : null;
    if (!date || Number.isNaN(date.getTime())) {
        return false;
    }

    const now = new Date();
    const startToday = new Date(
        now.getFullYear(),
        now.getMonth(),
        now.getDate()
    );
    const endToday = new Date(startToday);
    endToday.setHours(23, 59, 59, 999);

    if (period === "Today") {
        return date >= startToday && date <= endToday;
    }

    if (period === "This Week") {
        const day = startToday.getDay();
        const mondayOffset = day === 0 ? -6 : 1 - day;
        const startWeek = new Date(startToday);
        startWeek.setDate(startWeek.getDate() + mondayOffset);
        const endWeek = new Date(startWeek);
        endWeek.setDate(endWeek.getDate() + 6);
        endWeek.setHours(23, 59, 59, 999);
        return date >= startWeek && date <= endWeek;
    }

    if (period === "This Month") {
        return (
            date.getFullYear() === now.getFullYear() &&
            date.getMonth() === now.getMonth()
        );
    }

    return true;
}

function createEmptyAlertForm() {
    return {
        alertName: "",
        category: "Crop",
        subject: "",
        sourceType: "crop",
        sourceId: "",
        alertType: alertTypes.Crop[0],
        scheduleDate: "",
        scheduleTime: "",
        repeat: "None",
        priority: "Medium",
        status: "Active",
        description: "",
    };
}

function AlertFormModal({
    open,
    selectedAlert,
    onClose,
    onSave,
}) {
    const [form, setForm] =
        useState(
            createEmptyAlertForm
        );

    const [recordOptions, setRecordOptions] =
        useState([]);
    const [recordOptionsLoading, setRecordOptionsLoading] =
        useState(false);
    const [recordOptionsError, setRecordOptionsError] =
        useState("");

    const isEditing =
        Boolean(selectedAlert);

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        if (selectedAlert) {
            setForm({
                alertName: selectedAlert.alertName || "",
                category: selectedAlert.category || "Crop",
                subject: selectedAlert.subject || "",
                sourceType:
                    selectedAlert.sourceType ||
                    String(selectedAlert.category || "crop").toLowerCase(),
                sourceId:
                    selectedAlert.sourceId
                        ? String(selectedAlert.sourceId)
                        : "",
                alertType:
                    selectedAlert.alertType ||
                    alertTypes.Crop[0],
                scheduleDate: selectedAlert.scheduleDate || "",
                scheduleTime: selectedAlert.scheduleTime || "",
                repeat: selectedAlert.repeat || "None",
                priority: selectedAlert.priority || "Medium",
                status: selectedAlert.status || "Active",
                description: selectedAlert.description || "",
            });
        } else {
            setForm(createEmptyAlertForm());
        }

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, selectedAlert]);

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        const category = form.category;
        const supported = ["Crop", "Livestock", "Inventory"].includes(category);

        if (!supported) {
            setRecordOptions([]);
            setRecordOptionsError("");
            return undefined;
        }

        let cancelled = false;

        const loadOptions = async () => {
            try {
                setRecordOptionsLoading(true);
                setRecordOptionsError("");

                let options = [];

                if (category === "Crop") {
                    const records = await cropService.getCrops();
                    options = records.map((record) => ({
                        id: record.id,
                        label: `${record.name}${record.field ? ` — ${record.field}` : ""}`,
                        subject: record.name,
                    }));
                } else if (category === "Livestock") {
                    const records = await livestockService.getLivestock();
                    options = records.map((record) => ({
                        id: record.id,
                        label: `${record.recordName}${record.animalId ? ` — ${record.animalId}` : ""}`,
                        subject: record.recordName,
                    }));
                } else {
                    const records = await inventoryService.getInventory();
                    options = records.map((record) => ({
                        id: record.id,
                        label: `${record.itemCode ? `${record.itemCode} — ` : ""}${record.name}`,
                        subject: record.name,
                    }));
                }

                if (cancelled) {
                    return;
                }

                setRecordOptions(options);

                setForm((currentForm) => {
                    if (currentForm.category !== category) {
                        return currentForm;
                    }

                    if (currentForm.sourceId) {
                        return currentForm;
                    }

                    const subjectMatch = options.find(
                        (option) => option.subject === currentForm.subject
                    );

                    if (!subjectMatch) {
                        return currentForm;
                    }

                    return {
                        ...currentForm,
                        sourceId: String(subjectMatch.id),
                        sourceType: category.toLowerCase(),
                    };
                });
            } catch (error) {
                if (!cancelled) {
                    console.error("Failed to load alert subjects:", error);
                    setRecordOptions([]);
                    setRecordOptionsError(
                        error?.message || "Unable to load farm records."
                    );
                }
            } finally {
                if (!cancelled) {
                    setRecordOptionsLoading(false);
                }
            }
        };

        loadOptions();

        return () => {
            cancelled = true;
        };
    }, [open, form.category]);

    if (!open) {
        return null;
    }

    const availableTypes =
        alertTypes[
            form.category
        ] || [];

    const handleChange = (
        event
    ) => {
        const {
            name,
            value,
        } = event.target;

        if (
            name === "category"
        ) {
            setForm(
                (currentForm) => ({
                    ...currentForm,

                    category: value,
                    subject: "",
                    sourceType: value.toLowerCase(),
                    sourceId: "",

                    alertType:
                        alertTypes[
                            value
                        ]?.[0] || "",
                })
            );

            return;
        }

        if (name === "sourceId") {
            const selectedOption = recordOptions.find(
                (option) => String(option.id) === value
            );

            setForm((currentForm) => ({
                ...currentForm,
                sourceId: value,
                sourceType: currentForm.category.toLowerCase(),
                subject: selectedOption?.subject || "",
            }));
            return;
        }

        setForm(
            (currentForm) => ({
                ...currentForm,
                [name]: value,
            })
        );
    };

    const handleSubmit = (event) => {
        event.preventDefault();

        const requiresFarmRecord = [
            "Crop",
            "Livestock",
            "Inventory",
        ].includes(form.category);

        if (
            !form.alertName.trim() ||
            !form.subject.trim() ||
            (requiresFarmRecord && !form.sourceId) ||
            !form.alertType ||
            !form.scheduleDate ||
            !form.scheduleTime
        ) {
            notify(
                "Please complete the alert name, subject, date, and time."
            );
            return;
        }

        const scheduledDate = new Date(
            `${form.scheduleDate}T${form.scheduleTime}:00`
        );

        if (Number.isNaN(scheduledDate.getTime())) {
            notify("Please enter a valid alert date and time.");
            return;
        }

        onSave({
            alertName: form.alertName.trim(),
            category: form.category,
            subject: form.subject.trim(),
            sourceType:
                ["Crop", "Livestock", "Inventory"].includes(form.category)
                    ? form.category.toLowerCase()
                    : null,
            sourceId:
                form.sourceId
                    ? Number(form.sourceId)
                    : null,
            alertType: form.alertType,
            scheduleDate: form.scheduleDate,
            scheduleTime: form.scheduleTime,
            repeat: form.repeat,
            priority: form.priority,
            status: form.status,
            description:
                form.description.trim() ||
                "No alert description provided.",
        });
    };

    return (
        <div
            className="alerts-page-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="alerts-page-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="alerts-page-modal-header">
                    <div>
                        <h2>
                            {isEditing
                                ? "Edit Alert"
                                : "Add Alert"}
                        </h2>

                        <p>
                            {isEditing
                                ? `Update ${selectedAlert.alertName} and save the changes.`
                                : "Create a manual reminder for crops, livestock, inventory, Production & Sales, weather, or system activity."}
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close alert form"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="alerts-page-modal-form"
                    onSubmit={
                        handleSubmit
                    }
                >
                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                notifications
                            </span>

                            <div>
                                <h3>
                                    Alert Information
                                </h3>

                                <p>
                                    Enter the name,
                                    category, and
                                    subject of the
                                    alert.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-form-grid">
                            <div className="alerts-page-form-group">
                                <label htmlFor="alertName">
                                    Alert Name
                                    <span>*</span>
                                </label>

                                <input
                                    id="alertName"
                                    name="alertName"
                                    type="text"
                                    placeholder="Example: Harvest Reminder"
                                    value={
                                        form.alertName
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertCategory">
                                    Category
                                    <span>*</span>
                                </label>

                                <select
                                    id="alertCategory"
                                    name="category"
                                    value={
                                        form.category
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {categories.map(
                                        (category) => (
                                            <option
                                                key={
                                                    category
                                                }
                                                value={
                                                    category
                                                }
                                            >
                                                {
                                                    category
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertSubject">
                                    Subject
                                    <span>*</span>
                                </label>

                                {["Crop", "Livestock", "Inventory"].includes(
                                    form.category
                                ) ? (
                                    <>
                                        <select
                                            id="alertSubject"
                                            name="sourceId"
                                            value={form.sourceId}
                                            onChange={handleChange}
                                            disabled={recordOptionsLoading}
                                            required
                                        >
                                            <option value="">
                                                {recordOptionsLoading
                                                    ? "Loading farm records..."
                                                    : `Select ${form.category.toLowerCase()} record`}
                                            </option>

                                            {recordOptions.map((option) => (
                                                <option
                                                    key={option.id}
                                                    value={option.id}
                                                >
                                                    {option.label}
                                                </option>
                                            ))}
                                        </select>

                                        {recordOptionsError && (
                                            <small className="alerts-page-form-error">
                                                {recordOptionsError}
                                            </small>
                                        )}
                                    </>
                                ) : (
                                    <input
                                        id="alertSubject"
                                        name="subject"
                                        type="text"
                                        placeholder="Enter the alert subject"
                                        value={form.subject}
                                        onChange={handleChange}
                                        required
                                    />
                                )}
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertType">
                                    Alert Type
                                    <span>*</span>
                                </label>

                                <select
                                    id="alertType"
                                    name="alertType"
                                    value={
                                        form.alertType
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {availableTypes.map(
                                        (type) => (
                                            <option
                                                key={
                                                    type
                                                }
                                                value={
                                                    type
                                                }
                                            >
                                                {
                                                    type
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>
                        </div>
                    </section>

                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                event
                            </span>

                            <div>
                                <h3>Manual Schedule</h3>
                                <p>
                                    Choose the exact date and time for this
                                    reminder. Repeat is optional.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-form-condition-grid">
                            <div className="alerts-page-form-group">
                                <label htmlFor="alertScheduleDate">
                                    Alert Date
                                    <span>*</span>
                                </label>

                                <input
                                    id="alertScheduleDate"
                                    name="scheduleDate"
                                    type="date"
                                    value={form.scheduleDate}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertScheduleTime">
                                    Alert Time
                                    <span>*</span>
                                </label>

                                <input
                                    id="alertScheduleTime"
                                    name="scheduleTime"
                                    type="time"
                                    value={form.scheduleTime}
                                    onChange={handleChange}
                                    required
                                />
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertRepeat">Repeat</label>
                                <select
                                    id="alertRepeat"
                                    name="repeat"
                                    value={form.repeat}
                                    onChange={handleChange}
                                >
                                    {repeatOptions.map((option) => (
                                        <option key={option} value={option}>
                                            {option}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="alerts-page-manual-note">
                            <span className="material-symbols-outlined">
                                person
                            </span>
                            <span>
                                This alert will be saved as a Manual alert.
                                System alerts continue to use automatic conditions.
                            </span>
                        </div>
                    </section>

                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                priority_high
                            </span>

                            <div>
                                <h3>
                                    Status and
                                    Priority
                                </h3>

                                <p>
                                    Select the
                                    importance and
                                    current alert
                                    status.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-form-grid">
                            <div className="alerts-page-form-group">
                                <label htmlFor="alertPriority">
                                    Priority
                                </label>

                                <select
                                    id="alertPriority"
                                    name="priority"
                                    value={
                                        form.priority
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {priorities.map(
                                        (priority) => (
                                            <option
                                                key={
                                                    priority
                                                }
                                                value={
                                                    priority
                                                }
                                            >
                                                {
                                                    priority
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertStatus">
                                    Status
                                </label>

                                <select
                                    id="alertStatus"
                                    name="status"
                                    value={
                                        form.status
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="Active">
                                        Active
                                    </option>

                                    <option value="Disabled">
                                        Disabled
                                    </option>
                                </select>
                            </div>
                        </div>

                        <div className="alerts-page-form-group">
                            <label htmlFor="alertDescription">
                                Description
                            </label>

                            <textarea
                                id="alertDescription"
                                name="description"
                                rows="4"
                                placeholder="Explain what the alert monitors..."
                                value={
                                    form.description
                                }
                                onChange={
                                    handleChange
                                }
                            />
                        </div>
                    </section>

                    <footer className="alerts-page-form-footer">
                        <button
                            type="button"
                            className="alerts-page-cancel-button"
                            onClick={onClose}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            className="alerts-page-save-button"
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            {isEditing
                                ? "Save Changes"
                                : "Save Alert"}
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}


function AlertDetailsModal({
    open,
    alert,
    onClose,
}) {
    useEffect(() => {
        if (!open) {
            return undefined;
        }

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open]);

    if (!open || !alert) {
        return null;
    }

    const conditionText = getScheduleOrCondition(alert);

    return (
        <div
            className="alerts-page-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="alerts-page-modal alerts-page-details-modal"
                onMouseDown={(event) =>
                    event.stopPropagation()
                }
            >
                <header className="alerts-page-modal-header">
                    <div>
                        <h2>
                            Alert Details
                        </h2>

                        <p>
                            View the complete information for {alert.alertName}.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close alert details"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="alerts-page-modal-form">
                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                notifications
                            </span>

                            <div>
                                <h3>
                                    Alert Information
                                </h3>

                                <p>
                                    Complete alert configuration and current status.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-details-grid">
                            <div className="alerts-page-detail-item">
                                <span>
                                    Alert Name
                                </span>

                                <strong>
                                    {alert.alertName || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Category
                                </span>

                                <strong>
                                    {alert.category || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Subject
                                </span>

                                <strong>
                                    {alert.subject || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Alert Type
                                </span>

                                <strong>
                                    {alert.alertType || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    {alert.isAutomatic ? "Condition" : "Schedule"}
                                </span>

                                <strong className="alerts-page-threshold">
                                    {conditionText || "—"}
                                </strong>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Priority
                                </span>

                                <span
                                    className={`alerts-page-priority ${getClassName(
                                        alert.priority
                                    )}`}
                                >
                                    {alert.priority || "—"}
                                </span>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Status
                                </span>

                                <span
                                    className={`alerts-page-status ${getClassName(
                                        alert.status
                                    )}`}
                                >
                                    {alert.status || "—"}
                                </span>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>Source</span>
                                <span
                                    className={`alerts-page-source ${
                                        alert.isAutomatic ? "system" : "manual"
                                    }`}
                                >
                                    {alert.isAutomatic ? "System" : "Manual"}
                                </span>
                            </div>

                            <div className="alerts-page-detail-item">
                                <span>
                                    Last Triggered
                                </span>

                                <strong>
                                    {formatDateTime(
                                        alert.lastTriggered
                                    )}
                                </strong>
                            </div>
                        </div>
                    </section>

                    <section className="alerts-page-form-section">
                        <div className="alerts-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                description
                            </span>

                            <div>
                                <h3>
                                    Description
                                </h3>

                                <p>
                                    Purpose and monitoring details for this alert.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-detail-description">
                            {alert.description ||
                                "No alert description provided."}
                        </div>
                    </section>

                    <footer className="alerts-page-form-footer">
                        <button
                            type="button"
                            className="alerts-page-save-button"
                            onClick={onClose}
                        >
                            Close
                        </button>
                    </footer>
                </div>
            </div>
        </div>
    );
}

function AlertHistoryModal({
    open,
    alerts,
    total,
    loading,
    onLoadMore,
    onClose,
    onView,
    onEnable,
    actionBusyId,
}) {
    const [searchText, setSearchText] = useState("");
    const [statusFilter, setStatusFilter] = useState("All");
    const [sourceFilter, setSourceFilter] = useState("All");
    const [dateFilter, setDateFilter] = useState("All");

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        document.body.style.overflow = "hidden";
        return () => {
            document.body.style.overflow = "";
        };
    }, [open]);

    const historyAlerts = useMemo(() => {
        const search = searchText.trim().toLowerCase();

        return alerts
            .filter((item) => item.status !== "Active")
            .filter((item) => {
                const source = item.isAutomatic ? "System" : "Manual";
                const matchesSearch =
                    !search ||
                    item.alertName.toLowerCase().includes(search) ||
                    item.subject.toLowerCase().includes(search) ||
                    item.category.toLowerCase().includes(search) ||
                    item.alertType.toLowerCase().includes(search) ||
                    getHistoryReason(item).toLowerCase().includes(search);

                const matchesStatus =
                    statusFilter === "All" || item.status === statusFilter;
                const matchesSource =
                    sourceFilter === "All" || source === sourceFilter;
                const matchesDate = historyDateMatches(
                    item.updatedAt || item.lastTriggered || item.createdAt,
                    dateFilter
                );

                return (
                    matchesSearch &&
                    matchesStatus &&
                    matchesSource &&
                    matchesDate
                );
            })
            .sort((first, second) => {
                const firstTime = new Date(
                    first.updatedAt || first.lastTriggered || first.createdAt || 0
                ).getTime();
                const secondTime = new Date(
                    second.updatedAt || second.lastTriggered || second.createdAt || 0
                ).getTime();
                return secondTime - firstTime;
            });
    }, [alerts, searchText, statusFilter, sourceFilter, dateFilter]);

    if (!open) {
        return null;
    }

    return (
        <div
            className="alerts-page-modal-overlay"
            onMouseDown={onClose}
        >
            <div
                className="alerts-page-modal alerts-page-history-modal"
                onMouseDown={(event) => event.stopPropagation()}
            >
                <header className="alerts-page-modal-header">
                    <div>
                        <h2>Alert History</h2>
                        <p>
                            Review resolved, completed, and manually disabled alerts.
                            Records remain available for monitoring and audit history.
                            Filters search loaded history; load more to inspect older records.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={onClose}
                        aria-label="Close alert history"
                    >
                        <span className="material-symbols-outlined">close</span>
                    </button>
                </header>

                <div className="alerts-page-history-body">
                    <div className="alerts-page-history-filters">
                        <div className="alerts-page-search-box">
                            <span className="material-symbols-outlined">search</span>
                            <input
                                type="text"
                                placeholder="Search loaded alert history..."
                                value={searchText}
                                onChange={(event) => setSearchText(event.target.value)}
                            />
                        </div>

                        <select
                            value={statusFilter}
                            onChange={(event) => setStatusFilter(event.target.value)}
                        >
                            <option value="All">All Status</option>
                            {HISTORY_STATUSES.map((status) => (
                                <option key={status} value={status}>
                                    {status}
                                </option>
                            ))}
                        </select>

                        <select
                            value={sourceFilter}
                            onChange={(event) => setSourceFilter(event.target.value)}
                        >
                            <option value="All">All Sources</option>
                            <option value="System">System</option>
                            <option value="Manual">Manual</option>
                        </select>

                        <select
                            value={dateFilter}
                            onChange={(event) => setDateFilter(event.target.value)}
                        >
                            <option value="All">All Dates</option>
                            <option value="Today">Today</option>
                            <option value="This Week">This Week</option>
                            <option value="This Month">This Month</option>
                        </select>
                    </div>

                    <div className="alerts-page-history-table-wrapper">
                        <table className="alerts-page-history-table">
                            <thead>
                                <tr>
                                    <th>Alert</th>
                                    <th>Subject</th>
                                    <th>Status</th>
                                    <th>Source</th>
                                    <th>Reason</th>
                                    <th>Resolved / Updated</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {loading && alerts.length === 0 ? (
                                    <tr><td colSpan="7" className="alerts-page-empty-table">Loading alert history...</td></tr>
                                ) : historyAlerts.length > 0 ? (
                                    historyAlerts.map((item) => (
                                        <tr key={item.id}>
                                            <td>
                                                <strong>{item.alertName}</strong>
                                                <small>{item.category}</small>
                                            </td>
                                            <td>{item.subject}</td>
                                            <td>
                                                <span
                                                    className={`alerts-page-status ${getClassName(
                                                        item.status
                                                    )}`}
                                                >
                                                    {item.status}
                                                </span>
                                            </td>
                                            <td>
                                                <span
                                                    className={`alerts-page-source ${
                                                        item.isAutomatic ? "system" : "manual"
                                                    }`}
                                                >
                                                    {item.isAutomatic ? "System" : "Manual"}
                                                </span>
                                            </td>
                                            <td className="alerts-page-history-reason">
                                                {getHistoryReason(item)}
                                            </td>
                                            <td>
                                                {formatDateTime(
                                                    item.updatedAt ||
                                                        item.lastTriggered ||
                                                        item.createdAt
                                                )}
                                            </td>
                                            <td>
                                                <div className="alerts-page-history-actions">
                                                    <button
                                                        type="button"
                                                        title="View alert details"
                                                        onClick={() => onView(item)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            visibility
                                                        </span>
                                                    </button>

                                                    {!item.isAutomatic &&
                                                        item.status === "Disabled" && (
                                                            <button
                                                                type="button"
                                                                className="enable"
                                                                title="Enable this alert"
                                                                disabled={actionBusyId === item.id}
                                                                onClick={() => onEnable(item)}
                                                            >
                                                                <span className="material-symbols-outlined">
                                                                    notifications_active
                                                                </span>
                                                            </button>
                                                        )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))
                                ) : (
                                    <tr>
                                        <td colSpan="7" className="alerts-page-empty-table">
                                            <span className="material-symbols-outlined">
                                                history
                                            </span>
                                            <p>No alert history matches the selected filters.</p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="alerts-page-history-footer">
                        {historyAlerts.length} loaded matches • {total} history record(s) total
                        {alerts.length < total && <button type="button" disabled={loading}
                            onClick={onLoadMore}>{loading ? "Loading..." : "Load 50 more"}</button>}
                    </div>
                </div>
            </div>
        </div>
    );
}


function getAlertSourcePath(alert = {}) {
    const sourceType = String(alert.sourceType || "").toLowerCase();

    if (
        sourceType.startsWith("crop_") ||
        alert.category === "Crop"
    ) {
        return "/crops";
    }

    if (
        sourceType.startsWith("livestock_") ||
        alert.category === "Livestock"
    ) {
        return "/livestock";
    }

    if (
        sourceType === "inventory_low_stock" ||
        alert.category === "Inventory"
    ) {
        return "/inventory";
    }

    if (
        sourceType === "production_sale_receivable" ||
        alert.category === "Production & Sales"
    ) {
        return "/production-sales";
    }

    if (sourceType === "activity_task") {
        if (alert.category === "Crop") return "/crops";
        if (alert.category === "Livestock") return "/livestock";
        if (alert.category === "Inventory") return "/inventory";
        if (alert.category === "Production & Sales") return "/production-sales";
        return "/dashboard";
    }

    if (sourceType.startsWith("weather_")) {
        return "/dashboard";
    }

    if (sourceType.startsWith("system_")) {
        return "/settings";
    }

    return "/dashboard";
}

function Alerts() {
    const { hasPermission } = useAuth();
    const [
        alerts,
        setAlerts,
    ] = useState([]);

    const [
        alertsLoading,
        setAlertsLoading,
    ] = useState(true);

    const [
        alertsError,
        setAlertsError,
    ] = useState("");

    const [
        actionBusyId,
        setActionBusyId,
    ] = useState(null);

    const [
        alertSettings,
        setAlertSettings,
    ] = useState(() =>
        cloneSettings(
            DEFAULT_ALERT_SETTINGS
        )
    );

    const [
        activeTab,
        setActiveTab,
    ] = useState(
        "Active Alerts"
    );

    const [
        searchText,
        setSearchText,
    ] = useState("");

    const [
        categoryFilter,
        setCategoryFilter,
    ] = useState("All");

    const [
        statusFilter,
        setStatusFilter,
    ] = useState("All");

    const [
        alertFormOpen,
        setAlertFormOpen,
    ] = useState(false);

    const [
        alertSettingsOpen,
        setAlertSettingsOpen,
    ] = useState(false);

    const [
        alertHistoryOpen,
        setAlertHistoryOpen,
    ] = useState(false);

    const [
        editingAlert,
        setEditingAlert,
    ] = useState(null);

    const [
        viewingAlert,
        setViewingAlert,
    ] = useState(null);

    const [
        profileOpen,
        setProfileOpen,
    ] = useState(false);

    const [summaryData, setSummaryData] = useState(null);
    const [activeTotal, setActiveTotal] = useState(0);
    const [loadingMore, setLoadingMore] = useState(false);
    const [historyRecords, setHistoryRecords] = useState([]);
    const [historyTotal, setHistoryTotal] = useState(0);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [debouncedSearch, setDebouncedSearch] = useState("");
    const requestIdRef = useRef(0);

    useEffect(() => {
        const timer = window.setTimeout(() => setDebouncedSearch(searchText.trim()), 300);
        return () => window.clearTimeout(timer);
    }, [searchText]);

    const loadAlerts = useCallback(async (offset = 0) => {
        const requestId = ++requestIdRef.current;
        const append = offset > 0;
        if (append) setLoadingMore(true);
        else { setAlertsLoading(true); setLoadingMore(false); }
        setAlertsError("");
        try {
            const page = await alertService.getAlertPage({
                view: "active", offset, limit: 50, search: debouncedSearch,
                category: categoryFilter === "All" ? undefined : categoryFilter,
                priority: activeTab === "High Priority" ? "high" : undefined,
                source_type: activeTab === "Task Alerts" ? "task" : undefined,
            });
            if (requestId !== requestIdRef.current) return;
            setAlerts((current) => append
                ? [...current, ...page.items.filter((item) => !current.some((row) => row.id === item.id))]
                : page.items);
            setActiveTotal(page.total);
        } catch (error) {
            if (requestId !== requestIdRef.current) return;
            setAlertsError(error?.message || "Unable to load alert records.");
        } finally {
            if (requestId === requestIdRef.current) {
                if (append) setLoadingMore(false);
                else setAlertsLoading(false);
            }
        }
    }, [debouncedSearch, categoryFilter, activeTab]);

    const loadAlertSummary = useCallback(async () => {
        try { setSummaryData(await alertService.getAlertSummary()); }
        catch (error) { console.error("Failed to load alert counts:", error); }
    }, []);

    const loadHistory = useCallback(async (offset = 0) => {
        setHistoryLoading(true);
        try {
            const page = await alertService.getAlertPage({ view: "history", offset, limit: 50 });
            setHistoryRecords((current) => offset
                ? [...current, ...page.items.filter((item) => !current.some((row) => row.id === item.id))]
                : page.items);
            setHistoryTotal(page.total);
        } catch (error) { notify(error?.message || "Unable to load alert history."); }
        finally { setHistoryLoading(false); }
    }, []);

    useEffect(() => { void loadAlerts(); }, [loadAlerts]);
    useEffect(() => {
        void loadAlertSummary();
        void alertService.getSettings().then(setAlertSettings).catch((error) =>
            console.error("Failed to load alert settings:", error));
    }, [loadAlertSummary]);
    useEffect(() => {
        const onUpdate = () => {
            void loadAlerts();
            void loadAlertSummary();
            if (alertHistoryOpen) void loadHistory();
        };
        window.addEventListener("joross:alerts-updated", onUpdate);
        return () => window.removeEventListener("joross:alerts-updated", onUpdate);
    }, [loadAlerts, loadAlertSummary, loadHistory, alertHistoryOpen]);

    const refreshAlertViews = () => {
        void loadAlerts();
        void loadAlertSummary();
        if (alertHistoryOpen) void loadHistory();
    };

    const summaryCards = useMemo(() => [
        { title: "Active Alerts", value: summaryData?.active ?? 0, label: "Needs attention now",
          icon: "notification_important", className: "total" },
        { title: "High / Critical", value: summaryData?.high_priority ?? 0, label: "Needs urgent attention",
          icon: "priority_high", className: "active" },
        { title: "Overdue Tasks", value: summaryData?.overdue_tasks ?? 0, label: "Open tasks past due",
          icon: "assignment_late", className: "configured" },
        { title: "Alert History", value: summaryData?.history ?? 0, label: "Resolved or inactive",
          icon: "history", className: "disabled" },
    ], [summaryData]);

    const filteredAlerts = alerts;

    const openAddAlert = () => {
        setEditingAlert(null);
        setAlertFormOpen(true);
    };

    const openViewAlert = (
        selectedAlert
    ) => {
        setViewingAlert(
            selectedAlert
        );
    };

    const openEditAlert = (
        selectedAlert
    ) => {
        // System-generated alerts are managed automatically.
        if (selectedAlert?.isAutomatic) {
            return;
        }

        setEditingAlert(
            selectedAlert
        );

        setAlertFormOpen(true);
    };

    const openAlertSource = (selectedAlert) => {
        if (!selectedAlert) {
            return;
        }

        window.location.assign(
            getAlertSourcePath(selectedAlert)
        );
    };

    const completeManualAlert = async (selectedAlert) => {
        if (!selectedAlert || selectedAlert.isAutomatic) {
            return;
        }

        try {
            setActionBusyId(selectedAlert.id);

            const updatedAlert = await alertService.updateAlert(
                selectedAlert.id,
                {
                    status: "Completed",
                }
            );

            setAlerts((currentAlerts) =>
                currentAlerts.map((item) =>
                    item.id === selectedAlert.id
                        ? updatedAlert
                        : item
                )
            );

            if (viewingAlert?.id === selectedAlert.id) {
                setViewingAlert(updatedAlert);
            }
        } catch (error) {
            console.error("Failed to complete alert:", error);
            notify(
                error?.message ||
                    "Unable to complete the alert."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const handleSaveAlert = async (
        formData
    ) => {
        try {
            setActionBusyId(
                editingAlert?.id ??
                    "new"
            );

            if (editingAlert) {
                const updatedAlert =
                    await alertService.updateAlert(
                        editingAlert.id,
                        formData
                    );

                setAlerts(
                    (currentAlerts) =>
                        currentAlerts.map(
                            (item) =>
                                item.id ===
                                editingAlert.id
                                    ? updatedAlert
                                    : item
                        )
                );

                notify(
                    "Alert updated successfully."
                );
            } else {
                const createdAlert =
                    await alertService.createAlert(
                        formData
                    );

                setAlerts(
                    (currentAlerts) => [
                        createdAlert,
                        ...currentAlerts,
                    ]
                );

                notify(
                    "Alert added successfully."
                );
            }

            setAlertFormOpen(false);
            setEditingAlert(null);
        } catch (error) {
            console.error(
                "Failed to save alert:",
                error
            );

            notify(
                error?.message ||
                    "Unable to save the alert."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const handleSaveSettings = async (
        newSettings
    ) => {
        try {
            setActionBusyId(
                "settings"
            );

            const savedSettings =
                await alertService.updateSettings(
                    newSettings
                );

            setAlertSettings(
                savedSettings
            );

            setAlertSettingsOpen(
                false
            );

            notify(
                "Alert settings saved successfully."
            );
        } catch (error) {
            console.error(
                "Failed to save alert settings:",
                error
            );

            notify(
                error?.message ||
                    "Unable to save alert settings."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const toggleAlertStatus = async (
        selectedAlert
    ) => {
        // Automatic alerts follow system conditions and cannot be toggled here.
        if (selectedAlert?.isAutomatic) {
            return;
        }

        const nextStatus =
            selectedAlert.status ===
            "Active"
                ? "Disabled"
                : "Active";

        try {
            setActionBusyId(
                selectedAlert.id
            );

            // Status toggles should only update the status field.
            const updatedAlert =
                await alertService.updateAlert(
                    selectedAlert.id,
                    {
                        status: nextStatus,
                    }
                );

            setAlerts(
                (currentAlerts) =>
                    currentAlerts.map(
                        (item) =>
                            item.id ===
                            selectedAlert.id
                                ? updatedAlert
                                : item
                    )
            );

            if (
                viewingAlert?.id ===
                selectedAlert.id
            ) {
                setViewingAlert(
                    updatedAlert
                );
            }
        } catch (error) {
            console.error(
                "Failed to update alert status:",
                error
            );

            notify(
                error?.message ||
                    "Unable to update alert status."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const triggerAlert = async (
        selectedAlert
    ) => {
        if (selectedAlert?.isAutomatic) {
            return;
        }

        try {
            setActionBusyId(
                selectedAlert.id
            );

            const triggeredAlert =
                await alertService.triggerAlert(
                    selectedAlert.id
                );

            setAlerts(
                (currentAlerts) =>
                    currentAlerts.map(
                        (item) =>
                            item.id ===
                            selectedAlert.id
                                ? triggeredAlert
                                : item
                    )
            );

            if (
                viewingAlert?.id ===
                selectedAlert.id
            ) {
                setViewingAlert(
                    triggeredAlert
                );
            }

            notify(
                "Alert test triggered successfully."
            );
        } catch (error) {
            console.error(
                "Failed to trigger alert:",
                error
            );

            notify(
                error?.message ||
                    "Unable to trigger the alert."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const deleteAlert = async (
        selectedAlert
    ) => {
        if (selectedAlert?.isAutomatic) {
            return;
        }

        const confirmed =
            await confirmAction({
                title: "Delete Alert",
                message:
                    `Delete "${selectedAlert.alertName}"?`,
                type: "error",
                confirmText: "Delete",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            setActionBusyId(
                selectedAlert.id
            );

            await alertService.deleteAlert(
                selectedAlert.id
            );

            setAlerts(
                (currentAlerts) =>
                    currentAlerts.filter(
                        (item) =>
                            item.id !==
                            selectedAlert.id
                    )
            );

            if (
                viewingAlert?.id ===
                selectedAlert.id
            ) {
                setViewingAlert(null);
            }

            notify(
                `${selectedAlert.alertName} was deleted successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to delete alert:",
                error
            );

            notify(
                error?.message ||
                    "Unable to delete the alert."
            );
        } finally {
            setActionBusyId(null);
            refreshAlertViews();
        }
    };

    const clearFilters = () => {
        setSearchText("");
        setCategoryFilter("All");
        setStatusFilter("All");
    };

    return (
        <div className="alerts-page-layout">
            <Sidebar />

            <main className="alerts-page-content">
                <header className="alerts-page-header">
                    <div className="alerts-page-heading">
                        <h1>
                            Farm Alerts
                        </h1>

                        <p>
                            Monitor and
                            manage crop,
                            livestock,
                            inventory,
                            Production & Sales,
                            weather, and system alerts.
                        </p>
                    </div>

                    <AppHeaderActions />
                </header>

                <section className="alerts-page-summary-grid">
                    {summaryCards.map(
                        (card) => (
                            <article
                                key={
                                    card.title
                                }
                                className={`alerts-page-summary-card ${card.className}`}
                            >
                                <span className="alerts-page-summary-icon">
                                    <span className="material-symbols-outlined">
                                        {
                                            card.icon
                                        }
                                    </span>
                                </span>

                                <div>
                                    <p>
                                        {
                                            card.title
                                        }
                                    </p>

                                    <h2>
                                        {
                                            card.value
                                        }
                                    </h2>

                                    <small>
                                        {
                                            card.label
                                        }
                                    </small>
                                </div>
                            </article>
                        )
                    )}
                </section>

                <section className="alerts-page-management-card">
                    <div className="alerts-page-tabs-row">
                        <div className="alerts-page-tabs">
                            {[
                                "Active Alerts",
                                "High Priority",
                                "Task Alerts",
                            ].map(
                                (tab) => (
                                    <button
                                        type="button"
                                        key={
                                            tab
                                        }
                                        className={
                                            activeTab ===
                                            tab
                                                ? "active"
                                                : ""
                                        }
                                        onClick={() =>
                                            setActiveTab(
                                                tab
                                            )
                                        }
                                    >
                                        {tab}
                                    </button>
                                )
                            )}
                        </div>

                        <div className="alerts-page-top-buttons">
                            <button
                                type="button"
                                className="alerts-page-history-button"
                                onClick={() => { setAlertHistoryOpen(true); void loadHistory(); }}
                            >
                                <span className="material-symbols-outlined">
                                    history
                                </span>

                                Alert History
                            </button>

                            <button
                                type="button"
                                className="alerts-page-settings-button"
                                onClick={() =>
                                    setAlertSettingsOpen(
                                        true
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    settings
                                </span>

                                Alert Settings
                            </button>

                            <button
                                type="button"
                                className="alerts-page-add-button"
                                onClick={
                                    openAddAlert
                                }
                            >
                                <span className="material-symbols-outlined">
                                    add
                                </span>

                                Add Alert
                            </button>
                        </div>
                    </div>

                    <div className="alerts-page-filter-row">
                        <div className="alerts-page-search-box">
                            <span className="material-symbols-outlined">
                                search
                            </span>

                            <input
                                type="text"
                                placeholder="Search alerts..."
                                value={
                                    searchText
                                }
                                onChange={(
                                    event
                                ) =>
                                    setSearchText(
                                        event
                                            .target
                                            .value
                                    )
                                }
                            />
                        </div>

                        <select
                            value={
                                categoryFilter
                            }
                            onChange={(
                                event
                            ) =>
                                setCategoryFilter(
                                    event.target
                                        .value
                                )
                            }
                        >
                            <option value="All">
                                All Categories
                            </option>

                            {categories.map(
                                (category) => (
                                    <option
                                        key={
                                            category
                                        }
                                        value={
                                            category
                                        }
                                    >
                                        {
                                            category
                                        }
                                    </option>
                                )
                            )}
                        </select>

                        <button
                            type="button"
                            className="alerts-page-reset-button"
                            onClick={
                                clearFilters
                            }
                        >
                            <span className="material-symbols-outlined">
                                restart_alt
                            </span>

                            Reset
                        </button>
                    </div>

                    <div className="alerts-page-record-heading">
                        <div>
                            <h2>
                                Active Alert Records
                            </h2>

                            <p>
                                {
                                    activeTotal
                                }{" "}
                                records found
                            </p>
                        </div>
                    </div>

                    <div className="alerts-page-table-wrapper">
                        <table className="alerts-page-table">
                            <thead>
                                <tr>
                                    <th>
                                        Alert Name
                                    </th>

                                    <th>
                                        Subject
                                    </th>

                                    <th>
                                        Schedule / Condition
                                    </th>

                                    <th>
                                        Priority
                                    </th>

                                    <th>
                                        Status
                                    </th>

                                    <th>
                                        Source
                                    </th>

                                    <th>
                                        Actions
                                    </th>
                                </tr>
                            </thead>

                            <tbody>
                                {alertsLoading ? (
                                    <tr>
                                        <td
                                            colSpan="7"
                                            className="alerts-page-empty-table"
                                        >
                                            <span className="material-symbols-outlined">
                                                progress_activity
                                            </span>

                                            <p>
                                                Loading alert records...
                                            </p>
                                        </td>
                                    </tr>
                                ) : alertsError ? (
                                    <tr>
                                        <td
                                            colSpan="7"
                                            className="alerts-page-empty-table"
                                        >
                                            <span className="material-symbols-outlined">
                                                error
                                            </span>

                                            <p>
                                                {alertsError}
                                            </p>
                                        </td>
                                    </tr>
                                ) : filteredAlerts.length >
                                0 ? (
                                    filteredAlerts.map(
                                        (item) => (
                                            <tr
                                                key={
                                                    item.id
                                                }
                                            >
                                                <td>
                                                    <div className="alerts-page-name-cell">
                                                        <span
                                                            className={`alerts-page-category-icon ${getClassName(
                                                                item.category
                                                            )}`}
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                {getCategoryIcon(
                                                                    item.category
                                                                )}
                                                            </span>
                                                        </span>

                                                        <div>
                                                            <strong>
                                                                {
                                                                    item.alertName
                                                                }
                                                            </strong>
                                                        </div>
                                                    </div>
                                                </td>

                                                <td>
                                                    {
                                                        item.subject
                                                    }
                                                </td>

                                                <td>
                                                    <strong className="alerts-page-threshold">
                                                        {getScheduleOrCondition(item)}
                                                    </strong>
                                                </td>

                                                <td>
                                                    <span
                                                        className={`alerts-page-priority ${getClassName(
                                                            item.priority
                                                        )}`}
                                                    >
                                                        {
                                                            item.priority
                                                        }
                                                    </span>
                                                </td>

                                                <td>
                                                    <span
                                                        className={`alerts-page-status ${getClassName(
                                                            item.status
                                                        )}`}
                                                    >
                                                        {
                                                            item.status
                                                        }
                                                    </span>
                                                </td>

                                                <td>
                                                    <span
                                                        className={`alerts-page-source ${
                                                            item.isAutomatic ? "system" : "manual"
                                                        }`}
                                                    >
                                                        {item.isAutomatic ? "System" : "Manual"}
                                                    </span>
                                                </td>

                                                <td>
                                                    <div className="alerts-page-row-actions">
                                                        {item.category === "Weather" && hasPermission("workforce:manage") && <a className="alerts-page-source-button" title="Review affected farm work" aria-label={`Review work for ${item.alertName}`} href={eventCreatePath({ kind: "Emergency Suspension", title: `Review: ${item.alertName}`, reason: item.description || item.alertName, source: "Weather alert" })}><span className="material-symbols-outlined" aria-hidden="true">event_note</span></a>}
                                                        <button
                                                            type="button"
                                                            className="alerts-page-view-button"
                                                            title="View alert details"
                                                            aria-label={`View ${item.alertName}`}
                                                            onClick={() =>
                                                                openViewAlert(
                                                                    item
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                visibility
                                                            </span>
                                                        </button>

                                                        {item.isAutomatic ? (
                                                            <button
                                                                type="button"
                                                                className="alerts-page-source-button"
                                                                title="Open the source record"
                                                                aria-label={`Open source for ${item.alertName}`}
                                                                onClick={() =>
                                                                    openAlertSource(item)
                                                                }
                                                            >
                                                                <span className="material-symbols-outlined">
                                                                    open_in_new
                                                                </span>
                                                            </button>
                                                        ) : (
                                                            <>
                                                                <button
                                                                    type="button"
                                                                    title="Edit alert"
                                                                    onClick={() =>
                                                                        openEditAlert(item)
                                                                    }
                                                                    disabled={
                                                                        actionBusyId === item.id
                                                                    }
                                                                >
                                                                    <span className="material-symbols-outlined">
                                                                        edit
                                                                    </span>
                                                                </button>

                                                                <button
                                                                    type="button"
                                                                    title="Complete alert"
                                                                    onClick={() =>
                                                                        completeManualAlert(item)
                                                                    }
                                                                    disabled={
                                                                        actionBusyId === item.id
                                                                    }
                                                                >
                                                                    <span className="material-symbols-outlined">
                                                                        check_circle
                                                                    </span>
                                                                </button>

                                                                <button
                                                                    type="button"
                                                                    className={`alerts-page-toggle-button ${
                                                                        item.status === "Active"
                                                                            ? "enabled"
                                                                            : ""
                                                                    }`}
                                                                    title="Enable or disable alert"
                                                                    onClick={() =>
                                                                        toggleAlertStatus(item)
                                                                    }
                                                                    disabled={
                                                                        actionBusyId === item.id
                                                                    }
                                                                >
                                                                    <span className="alerts-page-toggle-circle" />
                                                                </button>

                                                                <button
                                                                    type="button"
                                                                    className="delete"
                                                                    title="Delete alert"
                                                                    onClick={() =>
                                                                        deleteAlert(item)
                                                                    }
                                                                    disabled={
                                                                        actionBusyId === item.id
                                                                    }
                                                                >
                                                                    <span className="material-symbols-outlined">
                                                                        delete
                                                                    </span>
                                                                </button>
                                                            </>
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
                                            className="alerts-page-empty-table"
                                        >
                                            <span className="material-symbols-outlined">
                                                notifications_off
                                            </span>

                                            <p>
                                                No alert
                                                records
                                                match the
                                                filters.
                                            </p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="alerts-page-table-footer">
                        Showing{" "}
                        {
                            filteredAlerts.length
                        }{" "}
                        of {activeTotal}{" "}
                        active alert records
                    </div>
                    {alerts.length < activeTotal && <div className="alerts-page-table-footer">
                        <button type="button" className="alerts-page-reset-button"
                            disabled={loadingMore || alertsLoading}
                            onClick={() => void loadAlerts(alerts.length)}>
                            {loadingMore ? "Loading..." : "Load 50 more alerts"}
                        </button>
                    </div>}
                </section>
            </main>

            <AlertHistoryModal
                open={alertHistoryOpen}
                alerts={historyRecords}
                total={historyTotal}
                loading={historyLoading}
                onLoadMore={() => void loadHistory(historyRecords.length)}
                actionBusyId={actionBusyId}
                onClose={() => setAlertHistoryOpen(false)}
                onView={(item) => {
                    setAlertHistoryOpen(false);
                    openViewAlert(item);
                }}
                onEnable={toggleAlertStatus}
            />

            <AlertDetailsModal
                open={
                    Boolean(
                        viewingAlert
                    )
                }
                alert={
                    viewingAlert
                }
                onClose={() =>
                    setViewingAlert(
                        null
                    )
                }
            />

            <AlertFormModal
                open={
                    alertFormOpen
                }
                selectedAlert={
                    editingAlert
                }
                onClose={() => {
                    setAlertFormOpen(
                        false
                    );

                    setEditingAlert(
                        null
                    );
                }}
                onSave={
                    handleSaveAlert
                }
            />

            <AlertSettingsModal
                open={
                    alertSettingsOpen
                }
                settings={
                    alertSettings
                }
                onClose={() =>
                    setAlertSettingsOpen(
                        false
                    )
                }
                onSave={
                    handleSaveSettings
                }
            />
        </div>
    );
}

export default Alerts;
