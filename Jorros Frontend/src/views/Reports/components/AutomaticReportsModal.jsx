"use client";

import { useEffect, useState } from "react";

// Schedule choices
const WEEK_DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
];

const FULL_MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
];


export default function AutomaticReportsModal({
    open,
    settings,
    defaultPreparedBy = "Farm Personnel",
    loading,
    onClose,
    onSave,
    onRunNow,
}) {
    const [
        form,
        setForm,
    ] = useState(
        settings
    );

    // Keep the form in sync when the modal opens
    useEffect(() => {
        if (
            open &&
            settings
        ) {
            setForm({
                ...settings,
                preparedBy: defaultPreparedBy || settings.preparedBy || "Farm Personnel",
            });
        }
    }, [
        open,
        settings,
        defaultPreparedBy,
    ]);

    if (!open) {
        return null;
    }

    if (
        loading ||
        !form
    ) {
        return (
            <div className="reports-page-modal-overlay">
                <div className="reports-page-form-modal">
                    <header className="reports-page-modal-header">
                        <div>
                            <h2>
                                Automatic Reports
                            </h2>

                            <p>
                                Loading report schedule...
                            </p>
                        </div>
                    </header>
                </div>
            </div>
        );
    }

    // Update text, number, and toggle fields
    const handleChange =
        (event) => {
            const {
                name,
                value,
            } = event.target;

            const booleans =
                new Set([
                    "dailyEnabled",
                    "weeklyEnabled",
                    "monthlyEnabled",
                    "yearlyEnabled",
                    "autoGeneratePdf",
                ]);

            const numbers =
                new Set([
                    "weeklyDay",
                    "monthlyDay",
                    "yearlyMonth",
                    "yearlyDay",
                ]);

            setForm(
                (current) => ({
                    ...current,
                    [name]:
                        booleans.has(
                            name
                        )
                            ? value ===
                              "true"
                            : numbers.has(
                                  name
                              )
                            ? Number(
                                  value
                              )
                            : value,
                })
            );
        };

    // Shared row used by the schedule options
    const frequencyRow =
        (
            enabledName,
            enabledValue,
            label,
            timeName,
            timeValue
        ) => (
            <>
                <div className="reports-page-form-group">
                    <label>
                        {label}
                    </label>

                    <select
                        name={
                            enabledName
                        }
                        value={
                            String(
                                enabledValue
                            )
                        }
                        onChange={
                            handleChange
                        }
                    >
                        <option value="true">
                            Enabled
                        </option>
                        <option value="false">
                            Disabled
                        </option>
                    </select>
                </div>

                <div className="reports-page-form-group">
                    <label>
                        Generation Time
                    </label>

                    <input
                        type="time"
                        name={
                            timeName
                        }
                        value={
                            timeValue
                        }
                        onChange={
                            handleChange
                        }
                    />
                </div>
            </>
        );

    return (
        <div
            className="reports-page-modal-overlay"
            onMouseDown={
                onClose
            }
        >
            <div
                className="reports-page-form-modal"
                onMouseDown={(
                    event
                ) =>
                    event.stopPropagation()
                }
            >
                <header className="reports-page-modal-header">
                    <div>
                        <h2>
                            Automatic Report Schedule
                        </h2>

                        <p>
                            Automatically create factual attendance, task, coverage, inventory, livestock,
                            production/sales, crop, and care-compliance reports for completed periods.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={
                            onClose
                        }
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="reports-page-modal-form">
                    <section className="reports-page-form-section">
                        <div className="reports-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                schedule
                            </span>

                            <div>
                                <h3>
                                    Frequencies
                                </h3>

                                <p>
                                    Daily uses the previous completed day. Weekly uses Monday-Sunday.
                                    Monthly uses the previous completed month. Seasonal reports use the
                                    previous completed quarter. Repeated scheduler runs are idempotent.
                                </p>
                            </div>
                        </div>

                        <div className="reports-page-form-grid">
                            {frequencyRow(
                                "dailyEnabled",
                                form.dailyEnabled,
                                "Daily Reports",
                                "dailyTime",
                                form.dailyTime
                            )}

                            <div className="reports-page-form-group">
                                <label>
                                    Weekly Reports
                                </label>

                                <select
                                    name="weeklyEnabled"
                                    value={
                                        String(
                                            form.weeklyEnabled
                                        )
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="true">
                                        Enabled
                                    </option>
                                    <option value="false">
                                        Disabled
                                    </option>
                                </select>
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Weekly Day
                                </label>

                                <select
                                    name="weeklyDay"
                                    value={
                                        form.weeklyDay
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {WEEK_DAYS.map(
                                        (
                                            day,
                                            index
                                        ) => (
                                            <option
                                                key={
                                                    day
                                                }
                                                value={
                                                    index
                                                }
                                            >
                                                {
                                                    day
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Weekly Time
                                </label>

                                <input
                                    type="time"
                                    name="weeklyTime"
                                    value={
                                        form.weeklyTime
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Monthly Reports
                                </label>

                                <select
                                    name="monthlyEnabled"
                                    value={
                                        String(
                                            form.monthlyEnabled
                                        )
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="true">
                                        Enabled
                                    </option>
                                    <option value="false">
                                        Disabled
                                    </option>
                                </select>
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Monthly Day
                                </label>

                                <input
                                    type="number"
                                    min="1"
                                    max="28"
                                    name="monthlyDay"
                                    value={
                                        form.monthlyDay
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Monthly Time
                                </label>

                                <input
                                    type="time"
                                    name="monthlyTime"
                                    value={
                                        form.monthlyTime
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Seasonal Reports
                                </label>

                                <select
                                    name="yearlyEnabled"
                                    value={
                                        String(
                                            form.yearlyEnabled
                                        )
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="true">
                                        Enabled
                                    </option>
                                    <option value="false">
                                        Disabled
                                    </option>
                                </select>
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Seasonal Generation Time
                                </label>

                                <input
                                    type="time"
                                    name="yearlyTime"
                                    value={
                                        form.yearlyTime
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>
                        </div>
                    </section>

                    <section className="reports-page-form-section">
                        <div className="reports-page-form-grid">
                            <div className="reports-page-form-group">
                                <label>
                                    Prepared By
                                </label>

                                <input
                                    type="text"
                                    name="preparedBy"
                                    value={
                                        form.preparedBy
                                    }
                                    readOnly
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Automatic PDF
                                </label>

                                <select
                                    name="autoGeneratePdf"
                                    value={
                                        String(
                                            form.autoGeneratePdf
                                        )
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    <option value="true">
                                        Generate PDF Automatically
                                    </option>
                                    <option value="false">
                                        Generate PDF When Opened
                                    </option>
                                </select>
                            </div>
                        </div>
                    </section>

                    <footer className="reports-page-form-footer">
                        <button
                            type="button"
                            className="reports-page-cancel-button"
                            onClick={
                                onClose
                            }
                        >
                            Cancel
                        </button>

                        <button
                            type="button"
                            className="reports-page-secondary-button"
                            onClick={() =>
                                onRunNow(
                                    form
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                play_arrow
                            </span>

                            Generate Due Reports Now
                        </button>

                        <button
                            type="button"
                            className="reports-page-save-button"
                            onClick={() =>
                                onSave(
                                    form
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                save
                            </span>

                            Save Schedule
                        </button>
                    </footer>
                </div>
            </div>
        </div>
    );
}
