"use client";

import { useEffect, useRef, useState } from "react";

import "./DashboardPeriodControl.css";

const periodOptions = [
    { value: "today", label: "Today" },
    { value: "week", label: "This Week" },
    { value: "month", label: "This Month" },
    { value: "last30", label: "Last 30 Days" },
    { value: "year", label: "This Year" },
    { value: "custom", label: "Custom Range" },
];

function formatDateShort(dateStr) {
    if (!dateStr) return "";
    const [y, m, d] = dateStr.split("-").map(Number);
    if (!y || !m || !d) return dateStr;
    const date = new Date(y, m - 1, d);
    return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function DashboardPeriodControl({
    value,
    customRange,
    onChange,
    onCustomRangeChange,
}) {
    const wrapRef = useRef(null);
    const [showCustomForm, setShowCustomForm] = useState(false);
    const [draftRange, setDraftRange] = useState(() => ({
        startDate: customRange?.startDate || (value?.includes(" to ") ? value.split(" to ")[0] : ""),
        endDate: customRange?.endDate || (value?.includes(" to ") ? value.split(" to ")[1] : ""),
    }));

    useEffect(() => {
        if (customRange?.startDate || customRange?.endDate) {
            setDraftRange({
                startDate: customRange?.startDate || "",
                endDate: customRange?.endDate || "",
            });
        } else if (value?.includes(" to ")) {
            const [start, end] = value.split(" to ");
            setDraftRange({
                startDate: start || "",
                endDate: end || "",
            });
        }
    }, [customRange?.startDate, customRange?.endDate, value]);

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (wrapRef.current && !wrapRef.current.contains(event.target)) {
                setShowCustomForm(false);
            }
        };

        const handleKeyDown = (event) => {
            if (event.key === "Escape") {
                setShowCustomForm(false);
            }
        };

        document.addEventListener("mousedown", handleClickOutside);
        document.addEventListener("keydown", handleKeyDown);
        return () => {
            document.removeEventListener("mousedown", handleClickOutside);
            document.removeEventListener("keydown", handleKeyDown);
        };
    }, []);

    const handleSelectChange = (event) => {
        const selected = event.target.value;
        if (selected === "custom") {
            setShowCustomForm(true);
        } else {
            setShowCustomForm(false);
            if (onChange) {
                onChange(selected);
            }
        }
    };

    const applyCustomRange = (event) => {
        event.preventDefault();

        if (!draftRange.startDate || !draftRange.endDate) {
            return;
        }

        const startDate =
            draftRange.startDate <= draftRange.endDate
                ? draftRange.startDate
                : draftRange.endDate;
        const endDate =
            draftRange.startDate <= draftRange.endDate
                ? draftRange.endDate
                : draftRange.startDate;

        const customValue = `${startDate} to ${endDate}`;
        if (onChange) {
            onChange(customValue);
        }
        if (onCustomRangeChange) {
            onCustomRangeChange({ startDate, endDate });
        }
        setShowCustomForm(false);
    };

    const isCustomValue = typeof value === "string" && value.includes(" to ");
    const isCustom = value === "custom" || isCustomValue;

    let customLabel = "Custom Range";
    if (isCustomValue) {
        const [s, e] = value.split(" to ");
        if (s && e) {
            customLabel = `Custom (${formatDateShort(s)} - ${formatDateShort(e)})`;
        }
    }

    return (
        <div className="dashboard-period-wrap" ref={wrapRef}>
            <div className="dashboard-period-control">
                <span className="material-symbols-outlined">date_range</span>

                <select
                    aria-label="Dashboard date period"
                    value={isCustom ? "custom" : value}
                    onChange={handleSelectChange}
                >
                    {periodOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.value === "custom" && isCustomValue ? customLabel : option.label}
                        </option>
                    ))}
                </select>

                {isCustom && (
                    <button
                        type="button"
                        className="dashboard-period-edit-btn"
                        onClick={() => setShowCustomForm((prev) => !prev)}
                        title="Edit custom date range"
                        aria-label="Edit custom date range"
                    >
                        <span className="material-symbols-outlined">edit_calendar</span>
                    </button>
                )}
            </div>

            {showCustomForm && (
                <form
                    className="dashboard-period-custom"
                    onSubmit={applyCustomRange}
                >
                    <div className="dashboard-period-custom-header">
                        <span>Custom Date Range</span>
                        <button
                            type="button"
                            className="close-btn"
                            onClick={() => setShowCustomForm(false)}
                            aria-label="Close date picker"
                        >
                            <span className="material-symbols-outlined">close</span>
                        </button>
                    </div>

                    <label>
                        <span>From</span>
                        <input
                            type="date"
                            value={draftRange.startDate}
                            onChange={(event) =>
                                setDraftRange((current) => ({
                                    ...current,
                                    startDate: event.target.value,
                                }))
                            }
                            required
                        />
                    </label>

                    <label>
                        <span>To</span>
                        <input
                            type="date"
                            value={draftRange.endDate}
                            onChange={(event) =>
                                setDraftRange((current) => ({
                                    ...current,
                                    endDate: event.target.value,
                                }))
                            }
                            required
                        />
                    </label>

                    <div className="dashboard-period-actions">
                        <button
                            type="button"
                            className="cancel-btn"
                            onClick={() => setShowCustomForm(false)}
                        >
                            Cancel
                        </button>
                        <button type="submit" className="apply-btn">
                            Apply
                        </button>
                    </div>
                </form>
            )}
        </div>
    );
}

export default DashboardPeriodControl;
