"use client";

import { useEffect, useState } from "react";

import "./DashboardPeriodControl.css";

const periodOptions = [
    { value: "today", label: "Today" },
    { value: "week", label: "This Week" },
    { value: "month", label: "This Month" },
    { value: "last30", label: "Last 30 Days" },
    { value: "year", label: "This Year" },
    { value: "custom", label: "Custom Range" },
];

function DashboardPeriodControl({
    value,
    customRange,
    onChange,
    onCustomRangeChange,
}) {
    const [draftRange, setDraftRange] = useState(() => ({
        startDate: customRange?.startDate || "",
        endDate: customRange?.endDate || "",
    }));

    useEffect(() => {
        setDraftRange({
            startDate: customRange?.startDate || "",
            endDate: customRange?.endDate || "",
        });
    }, [customRange?.startDate, customRange?.endDate]);

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

        onCustomRangeChange?.({ startDate, endDate });
    };

    return (
        <div className="dashboard-period-wrap">
            <div className="dashboard-period-control">
                <span className="material-symbols-outlined">date_range</span>

                <select
                    aria-label="Dashboard date period"
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                >
                    {periodOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                            {option.label}
                        </option>
                    ))}
                </select>
            </div>

            {value === "custom" && (
                <form
                    className="dashboard-period-custom"
                    onSubmit={applyCustomRange}
                >
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

                    <button type="submit">Apply</button>
                </form>
            )}
        </div>
    );
}

export default DashboardPeriodControl;
