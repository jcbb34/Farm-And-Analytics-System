"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useState } from "react";

// Add and edit manual alerts.

const categories = [
    "Crop",
    "Livestock",
    "Inventory",
    "Task",
    "Weather",
    "Report",
    "System",
];

const priorities = [
    "Low",
    "Medium",
    "High",
];

const conditions = [
    "Below",
    "Above",
    "Equals",
    "Within",
    "Every",
    "Older than",
    "At least",
];

const alertTypes = {
    Crop: [
        "Planting Reminder",
        "Growth Check",
        "Harvest Reminder",
        "Pest Detection",
        "Soil Moisture",
    ],
    Livestock: [
        "Feeding Reminder",
        "Vaccination Reminder",
        "Health Check",
        "Reproduction Reminder",
        "Weight Check",
        "Production Check",
    ],
    Inventory: [
        "Low Inventory",
        "Inventory Expiration",
    ],
    Task: [
        "Overdue Task",
    ],
    Weather: [
        "Heavy Rain",
        "High Temperature",
        "Strong Wind",
        "Thunderstorm",
    ],
    Report: [
        "Report Ready for Review",
    ],
    System: [
        "Backup Reminder",
        "Low Storage",
        "Failed Login",
        "System Maintenance",
    ],
};

function createEmptyAlertForm() {
    return {
        alertName: "",
        category: "Crop",
        subject: "",
        alertType: alertTypes.Crop[0],
        condition: "Within",
        threshold: "",
        unit: "days",
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

    const isEditing =
        Boolean(selectedAlert);

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        if (selectedAlert) {
            setForm({
                alertName:
                    selectedAlert.alertName ||
                    "",

                category:
                    selectedAlert.category ||
                    "Crop",

                subject:
                    selectedAlert.subject ||
                    "",

                alertType:
                    selectedAlert.alertType ||
                    alertTypes.Crop[0],

                condition:
                    selectedAlert.condition ||
                    "Within",

                threshold: String(
                    selectedAlert.threshold ??
                        ""
                ),

                unit:
                    selectedAlert.unit ||
                    "",

                priority:
                    selectedAlert.priority ||
                    "Medium",

                status:
                    selectedAlert.status ||
                    "Active",

                description:
                    selectedAlert.description ||
                    "",
            });
        } else {
            setForm(
                createEmptyAlertForm()
            );
        }

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open, selectedAlert]);

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

                    alertType:
                        alertTypes[
                            value
                        ]?.[0] || "",
                })
            );

            return;
        }

        setForm(
            (currentForm) => ({
                ...currentForm,
                [name]: value,
            })
        );
    };

    const handleSubmit = (
        event
    ) => {
        event.preventDefault();

        if (
            !form.alertName.trim() ||
            !form.subject.trim() ||
            !form.alertType ||
            !form.condition ||
            !String(
                form.threshold
            ).trim()
        ) {
            notify(
                "Please complete all required alert fields."
            );

            return;
        }

        onSave({
            alertName:
                form.alertName.trim(),

            category:
                form.category,

            subject:
                form.subject.trim(),

            alertType:
                form.alertType,

            condition:
                form.condition,

            threshold:
                form.threshold.trim(),

            unit:
                form.unit.trim(),

            priority:
                form.priority,

            status:
                form.status,

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
                                : "Create a farm alert for crops, livestock, weather, inventory, or system activity."}
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

                                <input
                                    id="alertSubject"
                                    name="subject"
                                    type="text"
                                    placeholder="Example: Yellow Corn"
                                    value={
                                        form.subject
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
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
                                tune
                            </span>

                            <div>
                                <h3>
                                    Alert Condition
                                </h3>

                                <p>
                                    Configure when this
                                    alert should be
                                    triggered.
                                </p>
                            </div>
                        </div>

                        <div className="alerts-page-form-condition-grid">
                            <div className="alerts-page-form-group">
                                <label htmlFor="alertCondition">
                                    Condition
                                    <span>*</span>
                                </label>

                                <select
                                    id="alertCondition"
                                    name="condition"
                                    value={
                                        form.condition
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {conditions.map(
                                        (condition) => (
                                            <option
                                                key={
                                                    condition
                                                }
                                                value={
                                                    condition
                                                }
                                            >
                                                {
                                                    condition
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertThreshold">
                                    Threshold
                                    <span>*</span>
                                </label>

                                <input
                                    id="alertThreshold"
                                    name="threshold"
                                    type="text"
                                    placeholder="Example: 7"
                                    value={
                                        form.threshold
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="alerts-page-form-group">
                                <label htmlFor="alertUnit">
                                    Unit
                                </label>

                                <input
                                    id="alertUnit"
                                    name="unit"
                                    type="text"
                                    placeholder="Example: days"
                                    value={
                                        form.unit
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
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

export default AlertFormModal;
