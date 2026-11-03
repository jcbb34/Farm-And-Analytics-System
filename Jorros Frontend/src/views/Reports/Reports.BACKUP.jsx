"use client";

import {
    useCallback,
    useEffect,
    useMemo,
    useState,
} from "react";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import AppHeaderActions from "../../components/AppHeaderActions/AppHeaderActions.jsx";

import { confirmAction } from "../../context/NotificationContext.jsx";
import {
    isAdministratorRole,
    useAuth,
} from "../../context/AuthContext.jsx";

import {
    addTimelineEntry,
    logAudit,
} from "../../services/farmIntelligenceService.js";

import { reportService } from "../../services/reportService.js";
import { resourceUsageService } from "../../services/resourceUsageService.js";

import "./Reports.css";

const categories = [
    "Farm",
    "Crop",
    "Livestock",
    "Inventory",
];

const statuses = [
    "Draft",
    "For Review",
    "Approved",
];

const reportTypes = {
    Farm: [
        "Farm Summary",
    ],

    Crop: [
        "Crop Production",
        "Harvest Summary",
        "Yield Performance",
        "Crop Growth",
        "Pest and Disease",
        "Resource Usage",
    ],

    Livestock: [
        "Livestock Production",
        "Growth Summary",
        "Health Summary",
        "Vaccination Summary",
        "Feeding Consumption",
        "Resource Usage",
    ],

    Inventory: [
        "Inventory Summary",
        "Stock Movement",
        "Low Stock",
        "Expiring Items",
        "Consumption Summary",
        "Resource Usage",
        "Inventory Valuation",
    ],
};

const creationStatuses = [
    "Draft",
    "For Review",
];

const chartColors = [
    "#16a34a",
    "#3b82f6",
    "#f59e0b",
    "#8b5cf6",
    "#ef4444",
    "#6b7280",
    "#0ea5e9",
    "#84cc16",
];

function colorizeData(items = []) {
    return items.map(
        (item, index) => ({
            ...item,
            color:
                item.color ||
                chartColors[
                    index %
                    chartColors.length
                ],
        })
    );
}

function formatMonthLabel(value) {
    if (!value) {
        return "";
    }

    const [
        year,
        month,
    ] = String(value)
        .split("-")
        .map(Number);

    if (
        !year ||
        !month
    ) {
        return String(value);
    }

    return new Date(
        year,
        month - 1,
        1
    ).toLocaleDateString(
        "en-US",
        {
            month: "short",
            year: "2-digit",
        }
    );
}

function formatMetricLabel(value) {
    return String(value || "")
        .replaceAll(
            "_",
            " "
        )
        .replace(
            /([A-Z])/g,
            " $1"
        )
        .replace(
            /\s+/g,
            " "
        )
        .trim()
        .replace(/^./, (character) =>
            character.toUpperCase()
        );
}

function formatMetricValue(value) {
    if (
        typeof value ===
        "number"
    ) {
        return Number.isInteger(
            value
        )
            ? String(value)
            : value.toLocaleString(
                  "en-US",
                  {
                      maximumFractionDigits:
                          2,
                  }
              );
    }

    return String(
        value ?? "0"
    );
}

function getTodayDate() {
    const date = new Date();

    const year =
        date.getFullYear();

    const month = String(
        date.getMonth() + 1
    ).padStart(2, "0");

    const day = String(
        date.getDate()
    ).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function formatDate(value) {
    if (!value) {
        return "Not specified";
    }

    const [
        year,
        month,
        day,
    ] = value
        .split("-")
        .map(Number);

    return new Date(
        year,
        month - 1,
        day
    ).toLocaleDateString(
        "en-US",
        {
            month: "short",
            day: "numeric",
            year: "numeric",
        }
    );
}

function formatDateTime(value) {
    if (!value) {
        return "Not scheduled";
    }

    const date =
        new Date(
            value
        );

    if (
        Number.isNaN(
            date.getTime()
        )
    ) {
        return String(
            value
        );
    }

    return date.toLocaleString(
        "en-US",
        {
            month:
                "short",
            day:
                "numeric",
            year:
                "numeric",
            hour:
                "numeric",
            minute:
                "2-digit",
        }
    );
}


function getClassName(
    value = ""
) {
    return String(value)
        .toLowerCase()
        .replaceAll(" ", "-")
        .replaceAll("/", "-");
}

function getCategoryIcon(
    category
) {
    const icons = {
        Farm: "analytics",
        Crop: "grass",
        Livestock: "pets",
        Inventory:
            "inventory_2",
    };

    return (
        icons[category] ||
        "description"
    );
}

function createEmptyReportForm() {
    return {
        title: "",
        category: "Farm",
        reportType:
            reportTypes.Farm[0],
        startDate: getTodayDate(),
        endDate: getTodayDate(),
        preparedBy:
            "Juan Dela Cruz",
        status: "Draft",
        summary: "",
    };
}

function buildPieGradient(
    items
) {
    const total =
        items.reduce(
            (
                currentTotal,
                item
            ) =>
                currentTotal +
                Number(item.value),
            0
        ) || 1;

    let previousPercentage = 0;

    const sections =
        items.map((item) => {
            const percentage =
                (Number(
                    item.value
                ) /
                    total) *
                100;

            const start =
                previousPercentage;

            const end =
                start +
                percentage;

            previousPercentage =
                end;

            return `${item.color} ${start}% ${end}%`;
        });

    return `conic-gradient(${sections.join(
        ", "
    )})`;
}

function BarChart({
    data,
    unit,
}) {
    const safeData =
        Array.isArray(data)
            ? data.filter(
                  (item) =>
                      Number.isFinite(
                          Number(
                              item.value
                          )
                      )
              )
            : [];

    if (safeData.length === 0) {
        return (
            <div className="reports-page-empty-table">
                <span className="material-symbols-outlined">
                    bar_chart
                </span>

                <p>
                    No report data is
                    available yet.
                </p>
            </div>
        );
    }

    const maximumValue =
        Math.max(
            ...safeData.map(
                (item) =>
                    Number(
                        item.value
                    )
            ),
            1
        );

    return (
        <div className="reports-page-bar-chart">
            <div className="reports-page-bar-area">
                {safeData.map(
                    (item) => (
                        <div
                            className="reports-page-bar-column"
                            key={
                                item.label
                            }
                        >
                            <div className="reports-page-bar-value">
                                {
                                    item.value
                                }
                                {unit}
                            </div>

                            <div className="reports-page-bar-track">
                                <div
                                    className="reports-page-bar-fill"
                                    style={{
                                        height: `${
                                            (Number(
                                                item.value
                                            ) /
                                                maximumValue) *
                                            100
                                        }%`,
                                    }}
                                />
                            </div>

                            <span>
                                {
                                    item.label
                                }
                            </span>
                        </div>
                    )
                )}
            </div>
        </div>
    );
}

function PieChart({
    data,
}) {
    const safeData =
        Array.isArray(data)
            ? data.filter(
                  (item) =>
                      Number(
                          item.value
                      ) > 0
              )
            : [];

    if (safeData.length === 0) {
        return (
            <div className="reports-page-empty-table">
                <span className="material-symbols-outlined">
                    pie_chart
                </span>

                <p>
                    No report data is
                    available yet.
                </p>
            </div>
        );
    }

    const coloredData =
        colorizeData(
            safeData
        );

    const total =
        coloredData.reduce(
            (
                currentTotal,
                item
            ) =>
                currentTotal +
                Number(item.value),
            0
        );

    return (
        <div className="reports-page-pie-layout">
            <div
                className="reports-page-pie-chart"
                style={{
                    background:
                        buildPieGradient(
                            coloredData
                        ),
                }}
            >
                <div className="reports-page-pie-center">
                    <strong>
                        {total}
                    </strong>

                    <span>
                        Total
                    </span>
                </div>
            </div>

            <div className="reports-page-pie-legend">
                {coloredData.map(
                    (item) => (
                        <div
                            key={
                                item.label
                            }
                        >
                            <span
                                className="reports-page-legend-color"
                                style={{
                                    background:
                                        item.color,
                                }}
                            />

                            <p>
                                {
                                    item.label
                                }
                            </p>

                            <strong>
                                {
                                    item.value
                                }
                            </strong>
                        </div>
                    )
                )}
            </div>
        </div>
    );
}

function ReportFormModal({
    open,
    onClose,
    onSave,
}) {
    const [
        form,
        setForm,
    ] = useState(
        createEmptyReportForm
    );

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        setForm(
            createEmptyReportForm()
        );

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open]);

    if (!open) {
        return null;
    }

    const availableTypes =
        reportTypes[
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
                (
                    currentForm
                ) => ({
                    ...currentForm,
                    category: value,
                    reportType:
                        reportTypes[
                            value
                        ]?.[0] || "",
                })
            );

            return;
        }

        setForm(
            (
                currentForm
            ) => ({
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
            !form.title.trim() ||
            !form.category ||
            !form.reportType ||
            !form.startDate ||
            !form.endDate ||
            !form.preparedBy.trim()
        ) {
            window.alert(
                "Please complete all required report fields."
            );

            return;
        }

        if (
            form.endDate <
            form.startDate
        ) {
            window.alert(
                "The end date cannot be earlier than the start date."
            );

            return;
        }

        onSave({
            title:
                form.title.trim(),

            category:
                form.category,

            reportType:
                form.reportType,

            startDate:
                form.startDate,

            endDate:
                form.endDate,

            preparedBy:
                form.preparedBy.trim(),

            status:
                form.status,

            summary:
                form.summary.trim() ||
                "No report summary provided.",
        });
    };

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
                            Generate Custom Report
                        </h2>

                        <p>
                            Create a crop,
                            livestock, or
                            inventory report
                            for a selected
                            period.
                        </p>
                    </div>

                    <button
                        type="button"
                        onClick={
                            onClose
                        }
                        aria-label="Close report form"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <form
                    className="reports-page-modal-form"
                    onSubmit={
                        handleSubmit
                    }
                >
                    <section className="reports-page-form-section">
                        <div className="reports-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                description
                            </span>

                            <div>
                                <h3>
                                    Report
                                    Information
                                </h3>

                                <p>
                                    Enter the
                                    report title,
                                    category, and
                                    type.
                                </p>
                            </div>
                        </div>

                        <div className="reports-page-form-grid">
                            <div className="reports-page-form-group full-width">
                                <label htmlFor="reportTitle">
                                    Report Title
                                    <span>
                                        *
                                    </span>
                                </label>

                                <input
                                    id="reportTitle"
                                    name="title"
                                    type="text"
                                    placeholder="Example: August Crop Production Report"
                                    value={
                                        form.title
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label htmlFor="reportCategory">
                                    Category
                                    <span>
                                        *
                                    </span>
                                </label>

                                <select
                                    id="reportCategory"
                                    name="category"
                                    value={
                                        form.category
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {categories.map(
                                        (
                                            category
                                        ) => (
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

                            <div className="reports-page-form-group">
                                <label htmlFor="reportType">
                                    Report Type
                                    <span>
                                        *
                                    </span>
                                </label>

                                <select
                                    id="reportType"
                                    name="reportType"
                                    value={
                                        form.reportType
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {availableTypes.map(
                                        (
                                            type
                                        ) => (
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

                    <section className="reports-page-form-section">
                        <div className="reports-page-form-section-heading">
                            <span className="material-symbols-outlined">
                                date_range
                            </span>

                            <div>
                                <h3>
                                    Report Period
                                </h3>

                                <p>
                                    Select the
                                    period covered
                                    by the report.
                                </p>
                            </div>
                        </div>

                        <div className="reports-page-form-grid">
                            <div className="reports-page-form-group">
                                <label htmlFor="reportStartDate">
                                    Start Date
                                    <span>
                                        *
                                    </span>
                                </label>

                                <input
                                    id="reportStartDate"
                                    name="startDate"
                                    type="date"
                                    value={
                                        form.startDate
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label htmlFor="reportEndDate">
                                    End Date
                                    <span>
                                        *
                                    </span>
                                </label>

                                <input
                                    id="reportEndDate"
                                    name="endDate"
                                    type="date"
                                    value={
                                        form.endDate
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label htmlFor="reportPreparedBy">
                                    Prepared By
                                    <span>
                                        *
                                    </span>
                                </label>

                                <input
                                    id="reportPreparedBy"
                                    name="preparedBy"
                                    type="text"
                                    value={
                                        form.preparedBy
                                    }
                                    onChange={
                                        handleChange
                                    }
                                    required
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label htmlFor="reportStatus">
                                    Status
                                </label>

                                <select
                                    id="reportStatus"
                                    name="status"
                                    value={
                                        form.status
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {creationStatuses.map(
                                        (
                                            status
                                        ) => (
                                            <option
                                                key={
                                                    status
                                                }
                                                value={
                                                    status
                                                }
                                            >
                                                {
                                                    status
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>
                        </div>
                    </section>

                    <section className="reports-page-form-section">
                        <div className="reports-page-form-group">
                            <label htmlFor="reportSummary">
                                Report Summary
                            </label>

                            <textarea
                                id="reportSummary"
                                name="summary"
                                rows="5"
                                placeholder="Enter a short description of the report..."
                                value={
                                    form.summary
                                }
                                onChange={
                                    handleChange
                                }
                            />
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
                            type="submit"
                            className="reports-page-save-button"
                        >
                            <span className="material-symbols-outlined">
                                description
                            </span>

                            Generate Custom Report
                        </button>
                    </footer>
                </form>
            </div>
        </div>
    );
}

function ReportDetailsModal({
    report,
    onClose,
    onExport,
    onDataExport,
    onSubmit,
    onApprove,
    onRevision,
    canApprove,
}) {
    const [
        versions,
        setVersions,
    ] = useState([]);

    const [
        versionsLoading,
        setVersionsLoading,
    ] = useState(false);

    useEffect(() => {
        if (!report) {
            setVersions([]);
            return undefined;
        }

        document.body.style.overflow =
            "hidden";

        let cancelled =
            false;

        const loadVersions =
            async () => {
                try {
                    setVersionsLoading(
                        true
                    );

                    const result =
                        await reportService.getVersions(
                            report.id
                        );

                    if (
                        !cancelled
                    ) {
                        setVersions(
                            result.versions
                        );
                    }
                } catch (error) {
                    console.error(
                        "Failed to load report version history:",
                        error
                    );

                    if (
                        !cancelled
                    ) {
                        setVersions(
                            []
                        );
                    }
                } finally {
                    if (
                        !cancelled
                    ) {
                        setVersionsLoading(
                            false
                        );
                    }
                }
            };

        loadVersions();

        return () => {
            cancelled =
                true;

            document.body.style.overflow =
                "";
        };
    }, [
        report,
    ]);

    if (!report) {
        return null;
    }

    const comparisonRows =
        report.comparison?.metrics ??
        [];

    const previousPeriod =
        report.comparison
            ?.previousPeriod ??
        {};

    return (
        <div
            className="reports-page-modal-overlay"
            onMouseDown={
                onClose
            }
        >
            <div
                className="reports-page-details-modal reports-page-details-modal-wide"
                onMouseDown={(
                    event
                ) =>
                    event.stopPropagation()
                }
            >
                <header className="reports-page-details-header">
                    <div className="reports-page-details-title">
                        <span
                            className={`reports-page-details-icon ${getClassName(
                                report.category
                            )}`}
                        >
                            <span className="material-symbols-outlined">
                                {getCategoryIcon(
                                    report.category
                                )}
                            </span>
                        </span>

                        <div>
                            <div className="reports-page-details-code">
                                <h2>
                                    {
                                        report.title
                                    }
                                </h2>

                                <span>
                                    {
                                        report.reportCode
                                    }
                                </span>
                            </div>

                            <p>
                                {
                                    report.reportType
                                }
                                {" • "}
                                Revision{" "}
                                {
                                    report.revisionNumber
                                }
                                {" • "}
                                {
                                    report.isAutomatic
                                        ? `${report.frequency} Automatic Report`
                                        : "Custom Report"
                                }
                            </p>
                        </div>
                    </div>

                    <button
                        type="button"
                        onClick={
                            onClose
                        }
                        aria-label="Close report details"
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="reports-page-details-body">
                    <section className="reports-page-details-grid">
                        <div>
                            <small>
                                Category
                            </small>

                            <strong>
                                {
                                    report.category
                                }
                            </strong>
                        </div>

                        <div>
                            <small>
                                Report Type
                            </small>

                            <strong>
                                {
                                    report.reportType
                                }
                            </strong>
                        </div>

                        <div>
                            <small>
                                Start Date
                            </small>

                            <strong>
                                {formatDate(
                                    report.startDate
                                )}
                            </strong>
                        </div>

                        <div>
                            <small>
                                End Date
                            </small>

                            <strong>
                                {formatDate(
                                    report.endDate
                                )}
                            </strong>
                        </div>

                        <div>
                            <small>
                                Prepared By
                            </small>

                            <strong>
                                {
                                    report.preparedBy
                                }
                            </strong>
                        </div>

                        <div>
                            <small>
                                Status
                            </small>

                            <span
                                className={`reports-page-status ${getClassName(
                                    report.status
                                )}`}
                            >
                                {
                                    report.status
                                }
                            </span>
                        </div>

                        <div>
                            <small>
                                Report Series
                            </small>

                            <strong>
                                {
                                    report.revisionGroupCode
                                }
                            </strong>
                        </div>

                        <div>
                            <small>
                                Revision
                            </small>

                            <strong>
                                Rev{" "}
                                {
                                    report.revisionNumber
                                }
                            </strong>
                        </div>

                        <div>
                            <small>
                                Submitted
                            </small>

                            <strong>
                                {formatDateTime(
                                    report.submittedAt
                                )}
                            </strong>
                        </div>

                        <div>
                            <small>
                                Approved
                            </small>

                            <strong>
                                {report.approvedAt
                                    ? formatDateTime(
                                          report.approvedAt
                                      )
                                    : "Pending"}
                            </strong>
                        </div>

                        <div>
                            <small>
                                Reviewed By
                            </small>

                            <strong>
                                {report.reviewedByName ||
                                    "Pending"}
                            </strong>
                        </div>

                        <div>
                            <small>
                                Editing
                            </small>

                            <strong>
                                {report.isLocked
                                    ? "Locked"
                                    : "Editable Draft"}
                            </strong>
                        </div>
                    </section>

                    <section className="reports-page-details-section">
                        <h3>
                            Executive Summary
                        </h3>

                        <p>
                            {
                                report.summary
                            }
                        </p>
                    </section>

                    <section className="reports-page-details-section">
                        <div className="reports-page-section-heading-row">
                            <div>
                                <h3>
                                    Previous Period Comparison
                                </h3>

                                <p>
                                    {previousPeriod.startDate &&
                                    previousPeriod.endDate
                                        ? `${formatDate(
                                              previousPeriod.startDate
                                          )} to ${formatDate(
                                              previousPeriod.endDate
                                          )}`
                                        : "No previous period comparison is available."}
                                </p>
                            </div>
                        </div>

                        {comparisonRows.length >
                        0 ? (
                            <div className="reports-page-comparison-table-wrap">
                                <table className="reports-page-comparison-table">
                                    <thead>
                                        <tr>
                                            <th>
                                                Metric
                                            </th>
                                            <th>
                                                Current
                                            </th>
                                            <th>
                                                Previous
                                            </th>
                                            <th>
                                                Difference
                                            </th>
                                            <th>
                                                Change
                                            </th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {comparisonRows
                                            .slice(
                                                0,
                                                12
                                            )
                                            .map(
                                                (
                                                    item
                                                ) => (
                                                    <tr
                                                        key={
                                                            item.metric
                                                        }
                                                    >
                                                        <td>
                                                            {formatMetricLabel(
                                                                item.metric
                                                            )}
                                                        </td>

                                                        <td>
                                                            {formatMetricValue(
                                                                item.current
                                                            )}
                                                        </td>

                                                        <td>
                                                            {formatMetricValue(
                                                                item.previous
                                                            )}
                                                        </td>

                                                        <td
                                                            className={`reports-page-change ${item.assessment || "neutral"}`}
                                                        >
                                                            {Number(
                                                                item.difference ||
                                                                    0
                                                            ) >
                                                            0
                                                                ? "+"
                                                                : ""}
                                                            {formatMetricValue(
                                                                item.difference
                                                            )}
                                                        </td>

                                                        <td>
                                                            {item.percentChange ===
                                                            null
                                                                ? "N/A"
                                                                : `${
                                                                      Number(
                                                                          item.percentChange
                                                                      ) >
                                                                      0
                                                                          ? "+"
                                                                          : ""
                                                                  }${formatMetricValue(
                                                                      item.percentChange
                                                                  )}%`}
                                                        </td>
                                                    </tr>
                                                )
                                            )}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <p className="reports-page-muted-copy">
                                Comparison information is not available for this report.
                            </p>
                        )}
                    </section>

                    <section className="reports-page-details-two-column">
                        <div className="reports-page-insight-panel">
                            <div className="reports-page-insight-title">
                                <span className="material-symbols-outlined">
                                    fact_check
                                </span>

                                <h3>
                                    Key Findings
                                </h3>
                            </div>

                            <ul>
                                {(report.findings ||
                                    []).map(
                                    (
                                        finding,
                                        index
                                    ) => (
                                        <li
                                            key={`${report.id}-finding-${index}`}
                                        >
                                            {
                                                finding
                                            }
                                        </li>
                                    )
                                )}
                            </ul>
                        </div>

                        <div className="reports-page-insight-panel recommendation">
                            <div className="reports-page-insight-title">
                                <span className="material-symbols-outlined">
                                    lightbulb
                                </span>

                                <h3>
                                    Recommendations
                                </h3>
                            </div>

                            <ul>
                                {(report.recommendations ||
                                    []).map(
                                    (
                                        recommendation,
                                        index
                                    ) => (
                                        <li
                                            key={`${report.id}-recommendation-${index}`}
                                        >
                                            {
                                                recommendation
                                            }
                                        </li>
                                    )
                                )}
                            </ul>
                        </div>
                    </section>

                    <section className="reports-page-details-section">
                        <h3>
                            Data Quality Notes
                        </h3>

                        <div className="reports-page-quality-list">
                            {(report.dataQuality ||
                                []).map(
                                (
                                    notice,
                                    index
                                ) => (
                                    <div
                                        className={`reports-page-quality-item ${getClassName(
                                            notice.level
                                        )}`}
                                        key={`${report.id}-quality-${index}`}
                                    >
                                        <span className="material-symbols-outlined">
                                            {notice.level ===
                                            "Warning"
                                                ? "warning"
                                                : notice.level ===
                                                  "Good"
                                                ? "verified"
                                                : "info"}
                                        </span>

                                        <div>
                                            <strong>
                                                {
                                                    notice.level
                                                }
                                            </strong>

                                            <p>
                                                {
                                                    notice.message
                                                }
                                            </p>
                                        </div>
                                    </div>
                                )
                            )}
                        </div>
                    </section>

                    <section className="reports-page-details-section">
                        <h3>
                            Version History
                        </h3>

                        {versionsLoading ? (
                            <p className="reports-page-muted-copy">
                                Loading version history...
                            </p>
                        ) : versions.length >
                          0 ? (
                            <div className="reports-page-version-list">
                                {versions.map(
                                    (
                                        version
                                    ) => (
                                        <div
                                            className={`reports-page-version-item ${
                                                version.id ===
                                                report.id
                                                    ? "current"
                                                    : ""
                                            }`}
                                            key={
                                                version.id
                                            }
                                        >
                                            <div>
                                                <strong>
                                                    Revision{" "}
                                                    {
                                                        version.revisionNumber
                                                    }
                                                </strong>

                                                <small>
                                                    {
                                                        version.reportCode
                                                    }
                                                </small>
                                            </div>

                                            <span
                                                className={`reports-page-status ${getClassName(
                                                    version.status
                                                )}`}
                                            >
                                                {
                                                    version.status
                                                }
                                            </span>
                                        </div>
                                    )
                                )}
                            </div>
                        ) : (
                            <p className="reports-page-muted-copy">
                                This is the only version of the report.
                            </p>
                        )}
                    </section>
                </div>

                <footer className="reports-page-details-footer reports-page-details-footer-wrap">
                    <button
                        type="button"
                        className="reports-page-secondary-button"
                        onClick={
                            onClose
                        }
                    >
                        Close
                    </button>

                    <button
                        type="button"
                        className="reports-page-secondary-button"
                        onClick={() =>
                            onDataExport(
                                report
                            )
                        }
                    >
                        <span className="material-symbols-outlined">
                            table_view
                        </span>

                        Supporting Data
                    </button>

                    {report.status ===
                        "Draft" && (
                        <button
                            type="button"
                            className="reports-page-workflow-button"
                            onClick={() =>
                                onSubmit(
                                    report
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                send
                            </span>

                            Submit for Review
                        </button>
                    )}

                    {report.status ===
                        "For Review" &&
                        canApprove && (
                            <button
                                type="button"
                                className="reports-page-workflow-button approve"
                                onClick={() =>
                                    onApprove(
                                        report
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    verified
                                </span>

                                Approve Report
                            </button>
                        )}

                    {report.status ===
                        "Approved" && (
                        <button
                            type="button"
                            className="reports-page-workflow-button revision"
                            onClick={() =>
                                onRevision(
                                    report
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                history
                            </span>

                            Create Revision
                        </button>
                    )}

                    <button
                        type="button"
                        className="reports-page-primary-button"
                        onClick={() =>
                            onExport(
                                report
                            )
                        }
                    >
                        <span className="material-symbols-outlined">
                            picture_as_pdf
                        </span>

                        Download PDF
                    </button>
                </footer>
            </div>
        </div>
    );
}

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


function AutomaticReportsModal({
    open,
    settings,
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

    useEffect(() => {
        if (
            open &&
            settings
        ) {
            setForm(
                settings
            );
        }
    }, [
        open,
        settings,
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
                            Automatically create a formal Farm Summary for
                            completed daily, weekly, monthly, and yearly periods.
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
                                    Daily covers the previous day. Weekly covers
                                    the previous seven-day week. Monthly and
                                    yearly cover the previous completed calendar
                                    period.
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
                                    Yearly Reports
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
                                    Yearly Month
                                </label>

                                <select
                                    name="yearlyMonth"
                                    value={
                                        form.yearlyMonth
                                    }
                                    onChange={
                                        handleChange
                                    }
                                >
                                    {FULL_MONTHS.map(
                                        (
                                            month,
                                            index
                                        ) => (
                                            <option
                                                key={
                                                    month
                                                }
                                                value={
                                                    index +
                                                    1
                                                }
                                            >
                                                {
                                                    month
                                                }
                                            </option>
                                        )
                                    )}
                                </select>
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Yearly Day
                                </label>

                                <input
                                    type="number"
                                    min="1"
                                    max="28"
                                    name="yearlyDay"
                                    value={
                                        form.yearlyDay
                                    }
                                    onChange={
                                        handleChange
                                    }
                                />
                            </div>

                            <div className="reports-page-form-group">
                                <label>
                                    Yearly Time
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
                                    onChange={
                                        handleChange
                                    }
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

function Reports() {
    const {
        user,
    } = useAuth();

    const canApprove =
        isAdministratorRole(
            user?.role
        );

    const [
        reports,
        setReports,
    ] = useState([]);

    const [
        activeTab,
        setActiveTab,
    ] = useState(
        "All Reports"
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
        startDateFilter,
        setStartDateFilter,
    ] = useState("");

    const [
        endDateFilter,
        setEndDateFilter,
    ] = useState("");

    const [
        reportFormOpen,
        setReportFormOpen,
    ] = useState(false);

    const [
        selectedReport,
        setSelectedReport,
    ] = useState(null);

    const [
        profileOpen,
        setProfileOpen,
    ] = useState(false);

    const [
        reportsLoading,
        setReportsLoading,
    ] = useState(true);

    const [
        reportsError,
        setReportsError,
    ] = useState("");

    const [
        automationOpen,
        setAutomationOpen,
    ] = useState(false);

    const [
        automationSettings,
        setAutomationSettings,
    ] = useState(null);

    const [
        automationLoading,
        setAutomationLoading,
    ] = useState(false);

    const [
        automationStatus,
        setAutomationStatus,
    ] = useState([]);

    const loadReports =
        useCallback(
            async () => {
                try {
                    setReportsLoading(
                        true
                    );
                    setReportsError(
                        ""
                    );

                    const records =
                        await reportService.getReports(
                            false
                        );

                    setReports(
                        records
                    );
                } catch (error) {
                    console.error(
                        "Failed to load reports:",
                        error
                    );

                    setReportsError(
                        error?.message ||
                            "Unable to load report records."
                    );
                } finally {
                    setReportsLoading(
                        false
                    );
                }
            },
            []
        );

    useEffect(() => {
        loadReports();
    }, [loadReports]);

    const loadAutomationSettings =
        useCallback(
            async () => {
                try {
                    setAutomationLoading(
                        true
                    );

                    const settings =
                        await reportService.getAutomationSettings();

                    setAutomationSettings(
                        settings
                    );
                } catch (error) {
                    console.error(
                        "Failed to load automatic report settings:",
                        error
                    );
                } finally {
                    setAutomationLoading(
                        false
                    );
                }
            },
            []
        );

    useEffect(() => {
        loadAutomationSettings();
    }, [loadAutomationSettings]);

    const loadAutomationStatus =
        useCallback(
            async () => {
                try {
                    const items =
                        await reportService.getAutomationStatus();

                    setAutomationStatus(
                        items
                    );
                } catch (error) {
                    console.error(
                        "Failed to load automatic report status:",
                        error
                    );

                    setAutomationStatus(
                        []
                    );
                }
            },
            []
        );

    useEffect(() => {
        loadAutomationStatus();
    }, [loadAutomationStatus]);

    const summaryCards =
        useMemo(() => {
            const approved =
                reports.filter(
                    (report) =>
                        report.status ===
                        "Approved"
                ).length;

            const forReview =
                reports.filter(
                    (report) =>
                        report.status ===
                        "For Review"
                ).length;

            const automatic =
                reports.filter(
                    (report) =>
                        report.isAutomatic
                ).length;

            const custom =
                reports.filter(
                    (report) =>
                        !report.isAutomatic
                ).length;

            return [
                {
                    title:
                        "Approved Reports",
                    value:
                        approved,
                    description:
                        "Official locked reports",
                    icon:
                        "verified",
                    className:
                        "completed",
                },
                {
                    title:
                        "For Review",
                    value:
                        forReview,
                    description:
                        "Waiting for approval",
                    icon:
                        "rate_review",
                    className:
                        "crop",
                },
                {
                    title:
                        "Automatic Reports",
                    value:
                        automatic,
                    description:
                        "Scheduled generation",
                    icon:
                        "schedule",
                    className:
                        "livestock",
                },
                {
                    title:
                        "Custom Reports",
                    value:
                        custom,
                    description:
                        "On-demand reports",
                    icon:
                        "description",
                    className:
                        "inventory",
                },
            ];
        }, [reports]);

    const categoryDistribution =
        useMemo(() => {
            return [
                {
                    label: "Farm",
                    value:
                        reports.filter(
                            (report) =>
                                report.category ===
                                "Farm"
                        ).length,
                    color: "#166534",
                },
                {
                    label: "Crop",
                    value:
                        reports.filter(
                            (report) =>
                                report.category ===
                                "Crop"
                        ).length,
                    color: "#16a34a",
                },
                {
                    label:
                        "Livestock",
                    value:
                        reports.filter(
                            (report) =>
                                report.category ===
                                "Livestock"
                        ).length,
                    color: "#f59e0b",
                },
                {
                    label:
                        "Inventory",
                    value:
                        reports.filter(
                            (report) =>
                                report.category ===
                                "Inventory"
                        ).length,
                    color: "#3b82f6",
                },
            ];
        }, [reports]);

    const filteredReports =
        useMemo(() => {
            const search =
                searchText
                    .trim()
                    .toLowerCase();

            return reports.filter(
                (report) => {
                    const tabCategory =
                        activeTab ===
                        "Crop Reports"
                            ? "Crop"
                            : activeTab ===
                              "Livestock Reports"
                            ? "Livestock"
                            : activeTab ===
                              "Inventory Reports"
                            ? "Inventory"
                            : null;

                    const matchesTab =
                        !tabCategory ||
                        report.category ===
                            tabCategory;

                    const matchesSearch =
                        !search ||
                        String(
                            report.reportCode ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        String(
                            report.title ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        String(
                            report.reportType ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        String(
                            report.preparedBy ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        String(
                            report.frequency ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            ) ||
                        String(
                            report.revisionGroupCode ||
                                ""
                        )
                            .toLowerCase()
                            .includes(
                                search
                            );

                    const matchesCategory =
                        categoryFilter ===
                            "All" ||
                        report.category ===
                            categoryFilter;

                    const matchesStatus =
                        statusFilter ===
                            "All" ||
                        report.status ===
                            statusFilter;

                    const matchesStartDate =
                        !startDateFilter ||
                        report.startDate >=
                            startDateFilter;

                    const matchesEndDate =
                        !endDateFilter ||
                        report.endDate <=
                            endDateFilter;

                    return (
                        matchesTab &&
                        matchesSearch &&
                        matchesCategory &&
                        matchesStatus &&
                        matchesStartDate &&
                        matchesEndDate
                    );
                }
            );
        }, [
            reports,
            activeTab,
            searchText,
            categoryFilter,
            statusFilter,
            startDateFilter,
            endDateFilter,
        ]);

    const handleSaveReport =
        async (formData) => {
            try {
                const newReport =
                    await reportService.generateReport(
                        formData
                    );

                setReports(
                    (
                        currentReports
                    ) => [
                        newReport,
                        ...currentReports.filter(
                            (report) =>
                                report.id !==
                                newReport.id
                        ),
                    ]
                );

                setReportFormOpen(
                    false
                );

                logAudit({
                    action:
                        "Generated farm report",
                    module: "Report",
                    recordName:
                        newReport.title,
                    entityId:
                        newReport.reportCode,
                    details: `${newReport.category} • ${newReport.reportType}`,
                });

                addTimelineEntry({
                    module: "Report",
                    recordName:
                        newReport.title,
                    entityId:
                        newReport.reportCode,
                    title:
                        "Report generated",
                    details: `${newReport.startDate} to ${newReport.endDate}`,
                    icon: "description",
                });

                window.alert(
                    "Report generated successfully."
                );
            } catch (error) {
                console.error(
                    "Failed to generate report:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to generate the report."
                );
            }
        };

    const clearFilters = () => {
        setSearchText("");
        setCategoryFilter("All");
        setStatusFilter("All");
        setStartDateFilter("");
        setEndDateFilter("");
    };

    const createCsvContent = (
        reportList
    ) => {
        const headers = [
            "Report Code",
            "Title",
            "Category",
            "Report Type",
            "Start Date",
            "End Date",
            "Generated Date",
            "Prepared By",
            "Status",
            "Summary",
        ];

        const rows =
            reportList.map(
                (report) => [
                    report.reportCode,
                    report.title,
                    report.category,
                    report.reportType,
                    report.startDate,
                    report.endDate,
                    report.generatedDate,
                    report.preparedBy,
                    report.status,
                    report.summary,
                ]
            );

        return [
            headers,
            ...rows,
        ]
            .map((row) =>
                row
                    .map(
                        (value) =>
                            `"${String(
                                value ?? ""
                            ).replaceAll(
                                '"',
                                '""'
                            )}"`
                    )
                    .join(",")
            )
            .join("\n");
    };

    const downloadCsv = (
        content,
        filename
    ) => {
        const blob =
            new Blob(
                [content],
                {
                    type:
                        "text/csv;charset=utf-8;",
                }
            );

        const url =
            URL.createObjectURL(
                blob
            );

        const link =
            document.createElement(
                "a"
            );

        link.href = url;
        link.download =
            filename;

        document.body.appendChild(
            link
        );

        link.click();
        link.remove();

        URL.revokeObjectURL(
            url
        );
    };

    const exportAllReports = () => {
        if (
            filteredReports.length ===
            0
        ) {
            window.alert(
                "There are no report records to export."
            );

            return;
        }

        downloadCsv(
            createCsvContent(
                filteredReports
            ),
            "joross-farm-reports.csv"
        );
    };

    const previewReportPdf =
        async (report) => {
            try {
                await reportService.previewPdf(
                    report
                );
            } catch (error) {
                console.error(
                    "Failed to preview report PDF:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to open the report PDF."
                );
            }
        };

    const exportSingleReport =
        async (report) => {
            try {
                await reportService.downloadPdf(
                    report
                );
            } catch (error) {
                console.error(
                    "Failed to download report PDF:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to download the report PDF."
                );
            }
        };

    const downloadSupportingData =
        async (report) => {
            try {
                await reportService.downloadSupportingData(
                    report
                );
            } catch (error) {
                console.error(
                    "Failed to download supporting report data:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to download the supporting report data."
                );
            }
        };

    const replaceReportInState =
        (
            updatedReport
        ) => {
            setReports(
                (
                    currentReports
                ) =>
                    currentReports.map(
                        (item) =>
                            item.id ===
                            updatedReport.id
                                ? updatedReport
                                : item
                    )
            );

            setSelectedReport(
                (
                    current
                ) =>
                    current?.id ===
                    updatedReport.id
                        ? updatedReport
                        : current
            );
        };

    const submitReportForReview =
        async (report) => {
            try {
                const updated =
                    await reportService.submitReport(
                        report.id
                    );

                replaceReportInState(
                    updated
                );

                window.alert(
                    `${updated.title} was submitted for review.`
                );
            } catch (error) {
                console.error(
                    "Failed to submit report:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to submit the report for review."
                );
            }
        };

    const approveReport =
        async (report) => {
            const confirmed =
                await confirmAction({
                    title:
                        "Approve Report",
                    message:
                        `Approve "${report.title}" as an official locked report?`,
                    type:
                        "success",
                    confirmText:
                        "Approve",
                    cancelText:
                        "Cancel",
                });

            if (!confirmed) {
                return;
            }

            try {
                const updated =
                    await reportService.approveReport(
                        report.id
                    );

                replaceReportInState(
                    updated
                );

                window.alert(
                    `${updated.title} was approved successfully.`
                );
            } catch (error) {
                console.error(
                    "Failed to approve report:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to approve the report."
                );
            }
        };

    const createReportRevision =
        async (report) => {
            const confirmed =
                await confirmAction({
                    title:
                        "Create Report Revision",
                    message:
                        `Create a new editable revision of "${report.title}"? The approved version will remain unchanged.`,
                    type:
                        "info",
                    confirmText:
                        "Create Revision",
                    cancelText:
                        "Cancel",
                });

            if (!confirmed) {
                return;
            }

            try {
                const revision =
                    await reportService.createRevision(
                        report.id
                    );

                setReports(
                    (
                        currentReports
                    ) => [
                        revision,
                        ...currentReports,
                    ]
                );

                setSelectedReport(
                    revision
                );

                window.alert(
                    `Revision ${revision.revisionNumber} was created as a Draft.`
                );
            } catch (error) {
                console.error(
                    "Failed to create report revision:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to create the report revision."
                );
            }
        };

    const saveAutomationSettings =
        async (
            settings,
            closeAfterSave =
                true
        ) => {
            try {
                setAutomationLoading(
                    true
                );

                const saved =
                    await reportService.updateAutomationSettings(
                        settings
                    );

                setAutomationSettings(
                    saved
                );

                if (
                    closeAfterSave
                ) {
                    setAutomationOpen(
                        false
                    );
                }

                return saved;
            } catch (error) {
                console.error(
                    "Failed to save automatic report settings:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to save automatic report settings."
                );

                return null;
            } finally {
                setAutomationLoading(
                    false
                );
            }
        };

    const runAutomaticReportsNow =
        async (settings) => {
            const saved =
                await saveAutomationSettings(
                    settings,
                    false
                );

            if (!saved) {
                return;
            }

            try {
                setAutomationLoading(
                    true
                );

                const result =
                    await reportService.runAutomationNow();

                await loadReports();
                await loadAutomationSettings();
                await loadAutomationStatus();

                window.alert(
                    result.message ||
                        `${result.generatedCount} automatic report(s) generated.`
                );
            } catch (error) {
                console.error(
                    "Failed to run automatic reports:",
                    error
                );

                window.alert(
                    error?.message ||
                        "Unable to run automatic reports."
                );
            } finally {
                setAutomationLoading(
                    false
                );
            }
        };

    const archiveReport = async (
        report
    ) => {
        const confirmed =
            await confirmAction({
                title: "Archive Report",
                message:
                    `Archive "${report.title}"?`,
                type: "warning",
                confirmText: "Archive",
                cancelText: "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            const archivedReport =
                await reportService.archiveReport(
                    report.id
                );

            setReports(
                (
                    currentReports
                ) =>
                    currentReports.filter(
                        (item) =>
                            item.id !==
                            archivedReport.id
                    )
            );

            if (
                selectedReport?.id ===
                archivedReport.id
            ) {
                setSelectedReport(
                    null
                );
            }

            logAudit({
                action:
                    "Archived farm report",
                module: "Report",
                recordName:
                    report.title,
                entityId:
                    report.reportCode,
                details:
                    report.reportType,
            });

            addTimelineEntry({
                module: "Report",
                recordName:
                    report.title,
                entityId:
                    report.reportCode,
                title:
                    "Report archived",
                details:
                    report.reportType,
                icon: "archive",
            });

            window.alert(
                `${report.title} was archived successfully.`
            );
        } catch (error) {
            console.error(
                "Failed to archive report:",
                error
            );

            window.alert(
                error?.message ||
                    "Unable to archive the report."
            );
        }
    };

    const latestSnapshot =
        (category) => {
            const report =
                reports.find(
                    (item) =>
                        item.category ===
                            category &&
                        item.snapshot &&
                        Object.keys(
                            item.snapshot
                        ).length > 0
                );

            return (
                report?.snapshot ||
                {}
            );
        };

    const renderAnalytics =
        () => {
            const cropSnapshot =
                latestSnapshot(
                    "Crop"
                );

            const livestockSnapshot =
                latestSnapshot(
                    "Livestock"
                );

            const inventorySnapshot =
                latestSnapshot(
                    "Inventory"
                );

            const cropHarvestData =
                (
                    cropSnapshot.monthlyHarvest ||
                    []
                ).map(
                    (item) => ({
                        label:
                            formatMonthLabel(
                                item.label
                            ),
                        value: Number(
                            (
                                Number(
                                    item.value ||
                                        0
                                ) /
                                1000
                            ).toFixed(
                                2
                            )
                        ),
                    })
                );

            const cropPerformanceData =
                (
                    cropSnapshot.cropPerformance ||
                    []
                ).map(
                    (item) => ({
                        crop:
                            item.crop,
                        area:
                            Number(
                                item.areaHa ||
                                    0
                            ),
                        harvest:
                            Number(
                                (
                                    Number(
                                        item.harvestKg ||
                                            0
                                    ) /
                                    1000
                                ).toFixed(
                                    2
                                )
                            ),
                        yield:
                            Number(
                                (
                                    Number(
                                        item.yieldKgPerHa ||
                                            0
                                    ) /
                                    1000
                                ).toFixed(
                                    2
                                )
                            ),
                    })
                );

            const livestockTypeData =
                colorizeData(
                    (
                        livestockSnapshot.typeDistribution ||
                        []
                    ).map(
                        (item) => ({
                            label:
                                item.label,
                            value:
                                Number(
                                    item.value ||
                                        0
                                ),
                        })
                    )
                );

            const livestockHealthData =
                colorizeData(
                    (
                        livestockSnapshot.healthDistribution ||
                        []
                    ).map(
                        (item) => ({
                            label:
                                item.label,
                            value:
                                Number(
                                    item.value ||
                                        0
                                ),
                        })
                    )
                );

            const inventoryMovementData =
                (
                    inventorySnapshot.movementDistribution ||
                    []
                ).map(
                    (item) => ({
                        label:
                            item.label,
                        value:
                            Number(
                                item.value ||
                                    0
                            ),
                    })
                );

            const inventoryCategoryData =
                colorizeData(
                    (
                        inventorySnapshot.categoryDistribution ||
                        []
                    ).map(
                        (item) => ({
                            label:
                                item.label,
                            value:
                                Number(
                                    item.value ||
                                        0
                                ),
                        })
                    )
                );

            if (
                activeTab ===
                "Crop Reports"
            ) {
                return (
                    <>
                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Monthly Harvest
                                    </h3>

                                    <p>
                                        Recorded crop
                                        harvest from
                                        the latest
                                        generated crop
                                        report.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    agriculture
                                </span>
                            </div>

                            <BarChart
                                data={
                                    cropHarvestData
                                }
                                unit="t"
                            />
                        </article>

                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Yield vs Area
                                    </h3>

                                    <p>
                                        Real crop area,
                                        harvest, and
                                        yield from the
                                        report snapshot.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    monitoring
                                </span>
                            </div>

                            <div className="reports-page-performance-table-wrapper">
                                <table className="reports-page-performance-table">
                                    <thead>
                                        <tr>
                                            <th>
                                                Crop
                                            </th>

                                            <th>
                                                Area
                                            </th>

                                            <th>
                                                Harvest
                                            </th>

                                            <th>
                                                Yield
                                            </th>
                                        </tr>
                                    </thead>

                                    <tbody>
                                        {cropPerformanceData.length >
                                        0 ? (
                                            cropPerformanceData.map(
                                                (
                                                    item
                                                ) => (
                                                    <tr
                                                        key={`${item.crop}-${item.area}`}
                                                    >
                                                        <td>
                                                            {
                                                                item.crop
                                                            }
                                                        </td>

                                                        <td>
                                                            {
                                                                item.area
                                                            }{" "}
                                                            ha
                                                        </td>

                                                        <td>
                                                            {
                                                                item.harvest
                                                            }{" "}
                                                            t
                                                        </td>

                                                        <td>
                                                            {
                                                                item.yield
                                                            }{" "}
                                                            t/ha
                                                        </td>
                                                    </tr>
                                                )
                                            )
                                        ) : (
                                            <tr>
                                                <td
                                                    colSpan="4"
                                                    className="reports-page-empty-table"
                                                >
                                                    No crop
                                                    performance
                                                    data yet.
                                                </td>
                                            </tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </article>
                    </>
                );
            }

            if (
                activeTab ===
                "Livestock Reports"
            ) {
                return (
                    <>
                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Livestock by Type
                                    </h3>

                                    <p>
                                        Current head
                                        count captured
                                        by the latest
                                        livestock report.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    pets
                                </span>
                            </div>

                            <BarChart
                                data={
                                    livestockTypeData
                                }
                                unit=""
                            />
                        </article>

                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Health Status
                                    </h3>

                                    <p>
                                        Real livestock
                                        health
                                        distribution
                                        from the report
                                        snapshot.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    health_and_safety
                                </span>
                            </div>

                            <PieChart
                                data={
                                    livestockHealthData
                                }
                            />
                        </article>
                    </>
                );
            }

            if (
                activeTab ===
                "Inventory Reports"
            ) {
                return (
                    <>
                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Stock Movements
                                    </h3>

                                    <p>
                                        Real stock
                                        adjustments by
                                        movement type
                                        for the latest
                                        inventory report.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    inventory
                                </span>
                            </div>

                            <BarChart
                                data={
                                    inventoryMovementData
                                }
                                unit=""
                            />
                        </article>

                        <article className="reports-page-chart-card">
                            <div className="reports-page-chart-heading">
                                <div>
                                    <h3>
                                        Stock by Category
                                    </h3>

                                    <p>
                                        Current
                                        inventory item
                                        distribution by
                                        category.
                                    </p>
                                </div>

                                <span className="material-symbols-outlined">
                                    inventory_2
                                </span>
                            </div>

                            <PieChart
                                data={
                                    inventoryCategoryData
                                }
                            />
                        </article>
                    </>
                );
            }

            return (
                <>
                    <article className="reports-page-chart-card">
                        <div className="reports-page-chart-heading">
                            <div>
                                <h3>
                                    Monthly Crop Harvest
                                </h3>

                                <p>
                                    Real harvest data
                                    from the latest
                                    generated crop
                                    report.
                                </p>
                            </div>

                            <span className="material-symbols-outlined">
                                monitoring
                            </span>
                        </div>

                        <BarChart
                            data={
                                cropHarvestData
                            }
                            unit="t"
                        />
                    </article>

                    <article className="reports-page-chart-card">
                        <div className="reports-page-chart-heading">
                            <div>
                                <h3>
                                    Reports by Category
                                </h3>

                                <p>
                                    Distribution of
                                    generated database
                                    reports.
                                </p>
                            </div>

                            <span className="material-symbols-outlined">
                                pie_chart
                            </span>
                        </div>

                        <PieChart
                            data={
                                categoryDistribution
                            }
                        />
                    </article>
                </>
            );
        };

    const downloadResourceUsageCsv = async () => {
        try {
            const csv = await resourceUsageService.exportCsv();
            const blob = new Blob([csv || ""], {
                type: "text/csv;charset=utf-8;",
            });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `joross-resource-usage-${getTodayDate()}.csv`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error("Failed to export resource usage:", error);
            window.alert(error?.message || "Unable to export resource usage report.");
        }
    };

    return (
        <div className="reports-page-layout">
            <Sidebar />

            <main className="reports-page-content">
                <header className="reports-page-header">
                    <div className="reports-page-heading">
                        <h1>
                            Reports Management
                        </h1>

                        <p>
                            Generate, preview, download,
                            and automatically schedule
                            professional farm reports.
                        </p>
                    </div>

                    <div className="reports-page-header-actions">
                        <button
                            type="button"
                            className="reports-page-secondary-button reports-page-resource-export"
                            onClick={downloadResourceUsageCsv}
                        >
                            <span className="material-symbols-outlined">inventory_2</span>
                            Resource Usage CSV
                        </button>
                        <AppHeaderActions />
                    </div>
                </header>

                <section className="reports-page-summary-grid">
                    {summaryCards.map(
                        (card) => (
                            <article
                                className={`reports-page-summary-card ${card.className}`}
                                key={
                                    card.title
                                }
                            >
                                <span className="reports-page-summary-icon">
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
                                            card.description
                                        }
                                    </small>
                                </div>
                            </article>
                        )
                    )}
                </section>

                <section className="reports-page-automation-overview">
                    <div className="reports-page-automation-overview-header">
                        <div>
                            <h2>
                                Automatic Report Schedule
                            </h2>

                            <p>
                                Live status for daily, weekly, monthly, and yearly report generation.
                            </p>
                        </div>


                    </div>

                    <div className="reports-page-automation-status-grid">
                        {automationStatus.length >
                        0 ? (
                            automationStatus.map(
                                (
                                    item
                                ) => (
                                    <article
                                        className={`reports-page-automation-status-card ${
                                            item.enabled
                                                ? "enabled"
                                                : "disabled"
                                        }`}
                                        key={
                                            item.frequency
                                        }
                                    >
                                        <div className="reports-page-automation-status-title">
                                            <span className="material-symbols-outlined">
                                                {item.frequency ===
                                                "Daily"
                                                    ? "today"
                                                    : item.frequency ===
                                                      "Weekly"
                                                    ? "date_range"
                                                    : item.frequency ===
                                                      "Monthly"
                                                    ? "calendar_month"
                                                    : "calendar_today"}
                                            </span>

                                            <div>
                                                <strong>
                                                    {
                                                        item.frequency
                                                    }
                                                </strong>

                                                <small>
                                                    {item.enabled
                                                        ? "Enabled"
                                                        : "Disabled"}
                                                </small>
                                            </div>
                                        </div>

                                        <div className="reports-page-automation-status-detail">
                                            <span>
                                                Last Report
                                            </span>

                                            <strong>
                                                {item.lastReportCode ||
                                                    "None yet"}
                                            </strong>

                                            <small>
                                                {item.lastPeriodStart &&
                                                item.lastPeriodEnd
                                                    ? `${formatDate(
                                                          item.lastPeriodStart
                                                      )} – ${formatDate(
                                                          item.lastPeriodEnd
                                                      )}`
                                                    : "No completed period generated yet"}
                                            </small>
                                        </div>

                                        <div className="reports-page-automation-status-detail">
                                            <span>
                                                Next Generation
                                            </span>

                                            <strong>
                                                {item.enabled
                                                    ? formatDateTime(
                                                          item.nextRunAt
                                                      )
                                                    : "Disabled"}
                                            </strong>
                                        </div>
                                    </article>
                                )
                            )
                        ) : (
                            <p className="reports-page-muted-copy">
                                Automatic report status is loading or unavailable.
                            </p>
                        )}
                    </div>
                </section>

                <section className="reports-page-management-card">
                    <div className="reports-page-tabs-row">
                        <div className="reports-page-tabs">
                            {[
                                "All Reports",
                                "Crop Reports",
                                "Livestock Reports",
                                "Inventory Reports",
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
                                        {
                                            tab
                                        }
                                    </button>
                                )
                            )}
                        </div>

                        <div className="reports-page-top-buttons">
                            <button
                                type="button"
                                className="reports-page-print-button"
                                onClick={() =>
                                    setAutomationOpen(
                                        true
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    schedule
                                </span>

                                Automatic Reports
                            </button>

                            <button
                                type="button"
                                className="reports-page-generate-button"
                                onClick={() =>
                                    setReportFormOpen(
                                        true
                                    )
                                }
                            >
                                <span className="material-symbols-outlined">
                                    add
                                </span>

                                Generate Custom Report
                            </button>
                        </div>
                    </div>

                    <div className="reports-page-filter-row">
                        <div className="reports-page-search-box">
                            <span className="material-symbols-outlined">
                                search
                            </span>

                            <input
                                type="text"
                                placeholder="Search reports..."
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
                                    event
                                        .target
                                        .value
                                )
                            }
                        >
                            <option value="All">
                                All Categories
                            </option>

                            {categories.map(
                                (
                                    category
                                ) => (
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

                        <select
                            value={
                                statusFilter
                            }
                            onChange={(
                                event
                            ) =>
                                setStatusFilter(
                                    event
                                        .target
                                        .value
                                )
                            }
                        >
                            <option value="All">
                                All Status
                            </option>

                            {statuses.map(
                                (status) => (
                                    <option
                                        key={
                                            status
                                        }
                                        value={
                                            status
                                        }
                                    >
                                        {
                                            status
                                        }
                                    </option>
                                )
                            )}
                        </select>

                        <input
                            type="date"
                            title="Start date"
                            value={
                                startDateFilter
                            }
                            onChange={(
                                event
                            ) =>
                                setStartDateFilter(
                                    event
                                        .target
                                        .value
                                )
                            }
                        />

                        <input
                            type="date"
                            title="End date"
                            value={
                                endDateFilter
                            }
                            onChange={(
                                event
                            ) =>
                                setEndDateFilter(
                                    event
                                        .target
                                        .value
                                )
                            }
                        />

                        <button
                            type="button"
                            className="reports-page-reset-button"
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
                </section>

                <section className="reports-page-analytics-grid">
                    {renderAnalytics()}
                </section>

                <section className="reports-page-table-card">
                    <div className="reports-page-table-heading">
                        <div>
                            <h2>
                                Generated Reports
                            </h2>

                            <p>
                                {
                                    filteredReports.length
                                }{" "}
                                report records found
                            </p>
                        </div>
                    </div>

                    <div className="reports-page-table-wrapper">
                        <table className="reports-page-table">
                            <thead>
                                <tr>
                                    <th>
                                        Report
                                    </th>

                                    <th>
                                        Category
                                    </th>

                                    <th>
                                        Report Type
                                    </th>

                                    <th>
                                        Period
                                    </th>

                                    <th>
                                        Generated
                                    </th>

                                    <th>
                                        Prepared By
                                    </th>

                                    <th>
                                        Status
                                    </th>

                                    <th>
                                        Actions
                                    </th>
                                </tr>
                            </thead>

                            <tbody>
                                {filteredReports.length >
                                0 ? (
                                    filteredReports.map(
                                        (
                                            report
                                        ) => (
                                            <tr
                                                key={
                                                    report.id
                                                }
                                            >
                                                <td>
                                                    <div className="reports-page-name-cell">
                                                        <span
                                                            className={`reports-page-category-icon ${getClassName(
                                                                report.category
                                                            )}`}
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                {getCategoryIcon(
                                                                    report.category
                                                                )}
                                                            </span>
                                                        </span>

                                                        <div>
                                                            <strong>
                                                                {
                                                                    report.title
                                                                }
                                                            </strong>

                                                            <small>
                                                                {
                                                                    report.reportCode
                                                                }
                                                                {report.isAutomatic
                                                                    ? ` • ${report.frequency}`
                                                                    : " • Custom"}
                                                                {` • Rev ${report.revisionNumber}`}
                                                            </small>
                                                        </div>
                                                    </div>
                                                </td>

                                                <td>
                                                    <span
                                                        className={`reports-page-category-badge ${getClassName(
                                                            report.category
                                                        )}`}
                                                    >
                                                        {
                                                            report.category
                                                        }
                                                    </span>
                                                </td>

                                                <td>
                                                    {
                                                        report.reportType
                                                    }
                                                </td>

                                                <td>
                                                    <strong className="reports-page-period">
                                                        {formatDate(
                                                            report.startDate
                                                        )}
                                                    </strong>

                                                    <small className="reports-page-period-end">
                                                        to{" "}
                                                        {formatDate(
                                                            report.endDate
                                                        )}
                                                    </small>
                                                </td>

                                                <td>
                                                    {formatDate(
                                                        report.generatedDate
                                                    )}
                                                </td>

                                                <td>
                                                    {
                                                        report.preparedBy
                                                    }
                                                </td>

                                                <td>
                                                    <span
                                                        className={`reports-page-status ${getClassName(
                                                            report.status
                                                        )}`}
                                                    >
                                                        {
                                                            report.status
                                                        }
                                                    </span>
                                                </td>

                                                <td>
                                                    <div className="reports-page-row-actions">
                                                        <button
                                                            type="button"
                                                            title="Preview professional PDF"
                                                            onClick={() =>
                                                                previewReportPdf(
                                                                    report
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                visibility
                                                            </span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            title="View report details"
                                                            onClick={() =>
                                                                setSelectedReport(
                                                                    report
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                info
                                                            </span>
                                                        </button>

                                                        <button
                                                            type="button"
                                                            title="Download PDF"
                                                            onClick={() =>
                                                                exportSingleReport(
                                                                    report
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                picture_as_pdf
                                                            </span>
                                                        </button>

                                                        {report.status ===
                                                            "Draft" && (
                                                            <button
                                                                type="button"
                                                                className="workflow"
                                                                title="Submit for review"
                                                                onClick={() =>
                                                                    submitReportForReview(
                                                                        report
                                                                    )
                                                                }
                                                            >
                                                                <span className="material-symbols-outlined">
                                                                    send
                                                                </span>
                                                            </button>
                                                        )}

                                                        {report.status ===
                                                            "For Review" &&
                                                            canApprove && (
                                                                <button
                                                                    type="button"
                                                                    className="workflow approve"
                                                                    title="Approve report"
                                                                    onClick={() =>
                                                                        approveReport(
                                                                            report
                                                                        )
                                                                    }
                                                                >
                                                                    <span className="material-symbols-outlined">
                                                                        verified
                                                                    </span>
                                                                </button>
                                                            )}

                                                        {report.status ===
                                                            "Approved" && (
                                                            <button
                                                                type="button"
                                                                className="workflow revision"
                                                                title="Create revision"
                                                                onClick={() =>
                                                                    createReportRevision(
                                                                        report
                                                                    )
                                                                }
                                                            >
                                                                <span className="material-symbols-outlined">
                                                                    history
                                                                </span>
                                                            </button>
                                                        )}

                                                        <button
                                                            type="button"
                                                            className="archive"
                                                            title="Archive report"
                                                            onClick={() =>
                                                                archiveReport(
                                                                    report
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                archive
                                                            </span>
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    )
                                ) : (
                                    <tr>
                                        <td
                                            colSpan="8"
                                            className="reports-page-empty-table"
                                        >
                                            <span className="material-symbols-outlined">
                                                description
                                            </span>

                                            <p>
                                                {reportsLoading
                                                    ? "Loading report records..."
                                                    : reportsError ||
                                                      "No report records match the selected filters."}
                                            </p>
                                        </td>
                                    </tr>
                                )}
                            </tbody>
                        </table>
                    </div>

                    <div className="reports-page-table-footer">
                        Showing{" "}
                        {
                            filteredReports.length
                        }{" "}
                        of {reports.length}{" "}
                        report records
                    </div>
                </section>
            </main>

            <AutomaticReportsModal
                open={
                    automationOpen
                }
                settings={
                    automationSettings
                }
                loading={
                    automationLoading
                }
                onClose={() =>
                    setAutomationOpen(
                        false
                    )
                }
                onSave={
                    saveAutomationSettings
                }
                onRunNow={
                    runAutomaticReportsNow
                }
            />

            <ReportFormModal
                open={
                    reportFormOpen
                }
                onClose={() =>
                    setReportFormOpen(
                        false
                    )
                }
                onSave={
                    handleSaveReport
                }
            />

            <ReportDetailsModal
                report={
                    selectedReport
                }
                onClose={() =>
                    setSelectedReport(
                        null
                    )
                }
                onExport={
                    exportSingleReport
                }
                onDataExport={
                    downloadSupportingData
                }
                onSubmit={
                    submitReportForReview
                }
                onApprove={
                    approveReport
                }
                onRevision={
                    createReportRevision
                }
                canApprove={
                    canApprove
                }
            />
        </div>
    );
}

export default Reports;