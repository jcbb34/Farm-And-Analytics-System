"use client";

import { notify } from "../../../context/NotificationContext.jsx";

import { useEffect, useState } from "react";

import { workforceService } from "../../../services/workforceService.js";
import { cropService } from "../../../services/cropService.js";
import { livestockService } from "../../../services/livestockService.js";
import { inventoryService } from "../../../services/inventoryService.js";

// Choices used by the create report form
const reportTypes = {
    Workforce: ["Daily Attendance Report", "Weekly Attendance Summary"],
    Tasks: ["Task Completion and Employee Performance", "Task Coverage and Reassignment"],
    "Care Compliance": ["Care Protocol Compliance"],
    Audit: ["Generated Report History and Audit Trail"],
    Farm: ["Farm Performance Report", "Farm Summary"],
    Crop: [
        "Crop Yield and Input Usage",
        "Crop Production",
        "Harvest Summary",
        "Yield Performance",
        "Crop Growth",
        "Pest and Disease",
        "Resource Usage",
    ],
    Livestock: [
        "Livestock Feeding, Growth, and Health",
        "Livestock Production",
        "Growth Summary",
        "Health Summary",
        "Vaccination Summary",
        "Feeding Consumption",
        "Resource Usage",
    ],
    "Production & Sales": [
        "Production and Sales Summary",
        "Production Summary",
        "Sales Summary",
        "Crop Production & Sales",
        "Livestock Production & Sales",
        "Processing Report",
        "Receivables Report",
    ],
    "Trend & Seasonal": [
        "Trend & Seasonal Analysis",
    ],
    Inventory: [
        "Inventory Movement and Resource Usage",
        "Inventory Summary",
        "Stock Movement",
        "Low Stock",
        "Expiring Items",
        "Consumption Summary",
        "Resource Usage",
        "Inventory Valuation",
    ],
};

const categories = Object.keys(reportTypes);
const operationalReportTypes = new Set([
    "Daily Attendance Report",
    "Weekly Attendance Summary",
    "Task Completion and Employee Performance",
    "Task Coverage and Reassignment",
    "Care Protocol Compliance",
    "Crop Yield and Input Usage",
    "Livestock Feeding, Growth, and Health",
    "Inventory Movement and Resource Usage",
    "Production and Sales Summary",
    "Generated Report History and Audit Trail",
]);
const creationStatuses = ["Draft", "For Review"];

const reportSections = [
    { key: "executive_summary", label: "Executive Summary", description: "Management overview of the selected period." },
    { key: "kpi_overview", label: "KPI Overview", description: "Key crop, livestock, sales, and inventory indicators." },
    { key: "period_comparison", label: "Previous-Period Comparison", description: "Current results versus the previous equivalent period." },
    { key: "performance_variance", label: "Performance & Variance", description: "Actual values versus recorded plans, capacity, or schedule references." },
    { key: "detailed_analysis", label: "Detailed Analysis", description: "Report-specific charts, metrics, and operational tables." },
    { key: "findings", label: "Key Findings", description: "Important observations derived from recorded data." },
    { key: "risks", label: "Risks & Issues", description: "Operational risk flags that need attention." },
    { key: "recommendations", label: "Recommended Actions", description: "Actions based on the findings and risk flags." },
    { key: "data_quality", label: "Data Quality", description: "Coverage and interpretation limitations." },
    { key: "appendix", label: "Supporting Appendix", description: "Detailed source records behind the report." },
];

const allReportSections = reportSections.map((section) => section.key);
const managementSummarySections = [
    "executive_summary",
    "kpi_overview",
    "period_comparison",
    "performance_variance",
    "findings",
    "risks",
    "recommendations",
    "data_quality",
];

function getTodayDate() {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");

    return `${year}-${month}-${day}`;
}

function getInitialReportSelection(initialTab) {
    if (initialTab === "Workforce Reports") {
        return { category: "Workforce", reportType: "Daily Attendance Report" };
    }

    if (initialTab === "Task Reports") {
        return { category: "Tasks", reportType: "Task Completion and Employee Performance" };
    }

    if (initialTab === "Care Compliance") {
        return { category: "Care Compliance", reportType: "Care Protocol Compliance" };
    }

    if (initialTab === "Audit Trail") {
        return { category: "Audit", reportType: "Generated Report History and Audit Trail" };
    }

    if (initialTab === "Crop Reports") {
        return { category: "Crop", reportType: "Crop Production" };
    }

    if (initialTab === "Livestock Reports") {
        return { category: "Livestock", reportType: "Growth Summary" };
    }

    if (initialTab === "Production & Sales") {
        return { category: "Production & Sales", reportType: "Production Summary" };
    }

    if (initialTab === "Trend & Seasonal Analysis") {
        return { category: "Trend & Seasonal", reportType: "Trend & Seasonal Analysis" };
    }

    if (initialTab === "Inventory Reports") {
        return { category: "Inventory", reportType: "Inventory Summary" };
    }

    if (initialTab === "Farm Performance") {
        return { category: "Farm", reportType: "Farm Performance Report" };
    }

    return { category: "Farm", reportType: "Farm Performance Report" };
}

function createEmptyReportForm(initialTab, defaultPreparedBy) {
    const selection = getInitialReportSelection(initialTab);

    return {
        title: "",
        category: selection.category,
        reportType: selection.reportType,
        startDate: getTodayDate(),
        endDate: getTodayDate(),
        preparedBy: defaultPreparedBy || "Farm Personnel",
        status: "Draft",
        summary: "",
        filters: { employee_id: "", crop_id: "", field: "", livestock_id: "", pen_id: "", inventory_item_id: "", status: "", source: "" },
        includedSections: [...allReportSections],
    };
}

function ReportFormModal({
    open,
    initialTab = "All Reports",
    defaultPreparedBy = "Farm Personnel",
    onClose,
    onSave,
}) {
    const [
        form,
        setForm,
    ] = useState(() =>
        createEmptyReportForm(initialTab, defaultPreparedBy)
    );
    const [filterOptions, setFilterOptions] = useState({ employees: [], crops: [], livestock: [], pens: [], inventory: [] });

    useEffect(() => {
        if (!open) {
            return undefined;
        }

        setForm(
            createEmptyReportForm(initialTab, defaultPreparedBy)
        );

        let active = true;
        Promise.all([
            workforceService.getEmployees(false),
            cropService.getCrops(false, false),
            livestockService.getLivestock(false),
            livestockService.getPens(false),
            inventoryService.getInventory(false, false),
        ]).then(([employees, crops, livestock, pens, inventory]) => {
            if (!active) return;
            setFilterOptions({
                employees: Array.isArray(employees) ? employees : employees?.data || [],
                crops: Array.isArray(crops) ? crops : [],
                livestock: Array.isArray(livestock) ? livestock : [],
                pens: Array.isArray(pens) ? pens : [],
                inventory: Array.isArray(inventory) ? inventory : [],
            });
        }).catch(() => {
            if (active) setFilterOptions({ employees: [], crops: [], livestock: [], pens: [], inventory: [] });
        });

        document.body.style.overflow =
            "hidden";

        return () => {
            active = false;
            document.body.style.overflow =
                "";
        };
    }, [open, initialTab, defaultPreparedBy]);

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
                    includedSections: operationalReportTypes.has(reportTypes[value]?.[0])
                        ? allReportSections.filter((section) => section !== "recommendations")
                        : [...allReportSections],
                })
            );

            return;
        }

        if (name === "reportType") {
            setForm((currentForm) => ({
                ...currentForm,
                reportType: value,
                includedSections: operationalReportTypes.has(value)
                    ? currentForm.includedSections.filter((section) => section !== "recommendations")
                    : currentForm.includedSections,
            }));
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

    const handleFilterChange = (event) => {
        const { name, value } = event.target;
        setForm((currentForm) => ({
            ...currentForm,
            filters: { ...currentForm.filters, [name]: value },
        }));
    };

    const toggleSection = (sectionKey) => {
        setForm((currentForm) => {
            const selected = new Set(currentForm.includedSections);
            if (selected.has(sectionKey)) {
                selected.delete(sectionKey);
            } else {
                selected.add(sectionKey);
            }

            return {
                ...currentForm,
                includedSections: reportSections
                    .map((section) => section.key)
                    .filter((key) => selected.has(key)),
            };
        });
    };

    const applySectionPreset = (sections) => {
        setForm((currentForm) => ({
            ...currentForm,
            includedSections: [...sections],
        }));
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
            notify(
                "Please complete all required report fields."
            );

            return;
        }

        if (
            form.endDate <
            form.startDate
        ) {
            notify(
                "The end date cannot be earlier than the start date."
            );

            return;
        }

        if (form.includedSections.length === 0) {
            notify("Select at least one report section.");
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
                form.summary.trim(),

            includedSections:
                form.includedSections,

            filters: Object.fromEntries(
                Object.entries(form.filters || {}).filter(([, value]) => value !== "" && value !== null && value !== undefined)
            ),
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
                            Create a factual report from attendance, tasks, crop, livestock,
                            inventory, production and sales, audit, or existing farm records
                            for a selected period.
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
                                    readOnly
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

                    {operationalReportTypes.has(form.reportType) && (
                        <section className="reports-page-form-section">
                            <div className="reports-page-form-section-heading">
                                <span className="material-symbols-outlined">filter_alt</span>
                                <div>
                                    <h3>Optional Source Filters</h3>
                                    <p>Filters are applied on the server before the factual report snapshot is saved.</p>
                                </div>
                            </div>
                            <div className="reports-page-form-grid">
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportEmployeeFilter">Employee</label>
                                    <select id="reportEmployeeFilter" name="employee_id" value={form.filters.employee_id} onChange={handleFilterChange}>
                                        <option value="">All employees</option>
                                        {filterOptions.employees.map((item) => <option key={item.id} value={item.id}>{item.full_name || item.fullName || item.employee_code || `Employee ${item.id}`}</option>)}
                                    </select>
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportCropFilter">Crop</label>
                                    <select id="reportCropFilter" name="crop_id" value={form.filters.crop_id} onChange={handleFilterChange}>
                                        <option value="">All crops</option>
                                        {filterOptions.crops.map((item) => <option key={item.id} value={item.id}>{item.name || item.cropCode || `Crop ${item.id}`}</option>)}
                                    </select>
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportFieldFilter">Field</label>
                                    <input id="reportFieldFilter" name="field" type="text" placeholder="All fields" value={form.filters.field} onChange={handleFilterChange} />
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportLivestockFilter">Livestock</label>
                                    <select id="reportLivestockFilter" name="livestock_id" value={form.filters.livestock_id} onChange={handleFilterChange}>
                                        <option value="">All livestock</option>
                                        {filterOptions.livestock.map((item) => <option key={item.id} value={item.id}>{item.recordName || item.record_name || item.animalCode || `Livestock ${item.id}`}</option>)}
                                    </select>
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportPenFilter">Pen</label>
                                    <select id="reportPenFilter" name="pen_id" value={form.filters.pen_id} onChange={handleFilterChange}>
                                        <option value="">All pens</option>
                                        {filterOptions.pens.map((item) => <option key={item.id} value={item.id}>{item.name || `Pen ${item.id}`}</option>)}
                                    </select>
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportInventoryFilter">Inventory Item</label>
                                    <select id="reportInventoryFilter" name="inventory_item_id" value={form.filters.inventory_item_id} onChange={handleFilterChange}>
                                        <option value="">All inventory items</option>
                                        {filterOptions.inventory.map((item) => <option key={item.id} value={item.id}>{item.name || item.itemCode || `Item ${item.id}`}</option>)}
                                    </select>
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportStatusFilter">Status</label>
                                    <input id="reportStatusFilter" name="status" type="text" placeholder="All statuses" value={form.filters.status} onChange={handleFilterChange} />
                                </div>
                                <div className="reports-page-form-group">
                                    <label htmlFor="reportSourceFilter">Manual / System Source</label>
                                    <select id="reportSourceFilter" name="source" value={form.filters.source} onChange={handleFilterChange}>
                                        <option value="">Manual and System</option>
                                        <option value="Manual">Manual</option>
                                        <option value="System">System</option>
                                    </select>
                                </div>
                            </div>
                        </section>
                    )}

                    <section className="reports-page-form-section">
                        <div className="reports-page-form-section-heading reports-page-form-section-heading-actions">
                            <span className="material-symbols-outlined">view_week</span>
                            <div>
                                <h3>Report Sections</h3>
                                <p>Choose what will appear in the generated PDF.</p>
                            </div>
                            <div className="reports-page-section-presets">
                                <button type="button" onClick={() => applySectionPreset(allReportSections)}>Select All</button>
                                <button type="button" onClick={() => applySectionPreset(managementSummarySections)}>Management Summary</button>
                            </div>
                        </div>

                        <div className="reports-page-section-selector">
                            {reportSections.filter((section) => !operationalReportTypes.has(form.reportType) || section.key !== "recommendations").map((section) => (
                                <label
                                    key={section.key}
                                    className={`reports-page-section-option ${
                                        form.includedSections.includes(section.key) ? "selected" : ""
                                    }`}
                                >
                                    <input
                                        type="checkbox"
                                        checked={form.includedSections.includes(section.key)}
                                        onChange={() => toggleSection(section.key)}
                                    />
                                    <span className="material-symbols-outlined">
                                        {form.includedSections.includes(section.key) ? "check_circle" : "circle"}
                                    </span>
                                    <span>
                                        <strong>{section.label}</strong>
                                        <small>{section.description}</small>
                                    </span>
                                </label>
                            ))}
                        </div>
                    </section>

                    <section className="reports-page-form-section">
                        <div className="reports-page-form-group">
                            <label htmlFor="reportSummary">
                                Report Summary <small>(Optional)</small>
                            </label>

                            <textarea
                                id="reportSummary"
                                name="summary"
                                rows="5"
                                placeholder="Leave blank to let the system generate the executive summary from the report data."
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

export default ReportFormModal;
