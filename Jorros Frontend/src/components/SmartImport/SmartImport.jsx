"use client";

import { notify } from "../../context/NotificationContext.jsx";

import {
    useEffect,
    useMemo,
    useRef,
    useState,
} from "react";

import {
    confirmAction,
    notifyError,
    notifySuccess,
    notifyWarning,
} from "../../context/NotificationContext.jsx";
import { importService } from "../../services/importService.js";

import "./SmartImport.css";


const TARGET_OPTIONS = [
    "Livestock Pen",
    "Crop",
    "Livestock",
    "Livestock Growth",
    "Livestock Feeding",
    "Resource Usage",
    "Inventory",
    "Crop Yield",
    "Vaccination",
    "Livestock Reproduction",
    "Livestock Production",
    "Livestock Processing",
    "Sales",
    "Report",
];


function formatDateTime(value) {
    if (!value) {
        return "—";
    }

    const parsed =
        new Date(value);

    if (
        Number.isNaN(
            parsed.getTime()
        )
    ) {
        return String(value);
    }

    return parsed.toLocaleString(
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


function formatBytes(value) {
    const bytes =
        Number(value || 0);

    if (bytes < 1024) {
        return `${bytes} B`;
    }

    if (bytes < 1024 ** 2) {
        return `${(
            bytes / 1024
        ).toFixed(1)} KB`;
    }

    return `${(
        bytes /
        1024 ** 2
    ).toFixed(1)} MB`;
}


function getRowLabel(row) {
    const mapped =
        row.mapped || {};

    return (
        mapped.cropCode ||
        mapped.animalCode ||
        mapped.itemCode ||
        mapped.recordName ||
        mapped.name ||
        mapped.cropName ||
        `Row ${row.rowNumber}`
    );
}


function ImportSummaryCard({
    icon,
    label,
    value,
    className = "",
}) {
    return (
        <article
            className={`smart-import-summary-card ${className}`}
        >
            <span className="material-symbols-outlined">
                {icon}
            </span>

            <div>
                <strong>
                    {value}
                </strong>

                <small>
                    {label}
                </small>
            </div>
        </article>
    );
}


function WorkbookOverview({ sheets }) {
    const selectedCount = sheets.filter(
        (sheet) => sheet.included !== false
    ).length;

    return (
        <section className="smart-import-workbook-overview">
            <div className="smart-import-workbook-heading">
                <div>
                    <strong>Workbook Sheets</strong>
                    <small>
                        {sheets.length} sheet(s) detected • {selectedCount} selected for import
                    </small>
                </div>

                <span className="material-symbols-outlined">
                    dataset
                </span>
            </div>

            <div className="smart-import-workbook-sheets">
                {sheets.map((sheet) => (
                    <div
                        className={`smart-import-workbook-sheet ${
                            sheet.included === false ? "excluded" : ""
                        }`}
                        key={`workbook-${sheet.sheetName}`}
                    >
                        <span className="material-symbols-outlined">
                            table_chart
                        </span>

                        <div>
                            <strong>{sheet.sheetName}</strong>
                            <small>
                                {sheet.targetType} • {sheet.validRows} valid / {sheet.rowCount} row(s)
                            </small>
                        </div>

                        <em>
                            {sheet.included === false ? "Skipped" : "Included"}
                        </em>
                    </div>
                ))}
            </div>
        </section>
    );
}


function SheetReviewCard({
    sheet,
    catalog,
    rowActions,
    setRowAction,
    onChange,
    isAdministrator,
}) {
    const fieldInfo =
        catalog?.[
            sheet.targetType
        ]?.fields || [];

    const duplicateRows =
        (sheet.rows || []).filter(
            (row) =>
                row.duplicateStatus !==
                "New"
        );

    return (
        <article className="smart-import-sheet-card">
            <div className="smart-import-sheet-header">
                <div className="smart-import-sheet-title">
                    <span className="material-symbols-outlined">
                        table_chart
                    </span>

                    <div>
                        <h3>
                            {sheet.sheetName}
                        </h3>

                        <p>
                            Detected as{" "}
                            <strong>
                                {
                                    sheet.detectedType
                                }
                            </strong>
                            {" • "}
                            {sheet.rowCount}{" "}
                            row(s)
                        </p>
                    </div>
                </div>

                <div className="smart-import-sheet-controls">
                    <span
                        className={`smart-import-confidence ${
                            sheet.confidence >=
                            80
                                ? "high"
                                : sheet.confidence >=
                                  60
                                ? "medium"
                                : "low"
                        }`}
                    >
                        {sheet.confidence}%
                        confidence
                    </span>

                    <label className="smart-import-check">
                        <input
                            type="checkbox"
                            checked={
                                sheet.included !==
                                false
                            }
                            onChange={(
                                event
                            ) =>
                                onChange({
                                    ...sheet,
                                    included:
                                        event
                                            .target
                                            .checked,
                                })
                            }
                        />

                        Import sheet
                    </label>
                </div>
            </div>

            <div className="smart-import-type-row">
                <label>
                    Data Type

                    <select
                        value={
                            sheet.targetType
                        }
                        onChange={(
                            event
                        ) =>
                            onChange({
                                ...sheet,
                                targetType:
                                    event
                                        .target
                                        .value,
                                columnMapping:
                                    {},
                            })
                        }
                    >
                        {TARGET_OPTIONS.map(
                            (target) => (
                                <option
                                    key={
                                        target
                                    }
                                    value={
                                        target
                                    }
                                >
                                    {
                                        target
                                    }
                                </option>
                            )
                        )}
                    </select>
                </label>

                <div className="smart-import-sheet-counts">
                    <span className="valid">
                        {
                            sheet.validRows
                        }{" "}
                        valid
                    </span>

                    <span className="invalid">
                        {
                            sheet.invalidRows
                        }{" "}
                        invalid
                    </span>

                    <span className="duplicate">
                        {
                            sheet.duplicateRows
                        }{" "}
                        duplicate
                    </span>

                    <span>
                        {
                            sheet.generatedCodeRows
                        }{" "}
                        generated IDs
                    </span>
                </div>
            </div>

            {sheet.targetType ===
            "Report" ? (
                <div className="smart-import-report-warning">
                    <span className="material-symbols-outlined">
                        description
                    </span>

                    <div>
                        <strong>
                            Report file detected
                        </strong>

                        <p>
                            Report-shaped data is
                            detected, but it is not
                            inserted as production
                            data. Official reports
                            are generated from the
                            Reports module.
                        </p>
                    </div>
                </div>
            ) : (
                <>
                    <details className="smart-import-mapping-details">
                        <summary>
                            Review Column Mapping
                        </summary>

                        <div className="smart-import-mapping-grid">
                            {fieldInfo.map(
                                (field) => (
                                    <label
                                        key={
                                            field.key
                                        }
                                    >
                                        <span>
                                            {
                                                field.label
                                            }
                                            {field.required && (
                                                <em>
                                                    *
                                                </em>
                                            )}
                                        </span>

                                        <select
                                            value={
                                                sheet
                                                    .columnMapping?.[
                                                    field
                                                        .key
                                                ] ||
                                                ""
                                            }
                                            onChange={(
                                                event
                                            ) =>
                                                onChange({
                                                    ...sheet,
                                                    columnMapping:
                                                        {
                                                            ...(sheet.columnMapping ||
                                                                {}),
                                                            [field.key]:
                                                                event
                                                                    .target
                                                                    .value ||
                                                                null,
                                                        },
                                                })
                                            }
                                        >
                                            <option value="">
                                                Not mapped
                                            </option>

                                            {(sheet.sourceColumns || []).map(
                                                (
                                                    column
                                                ) => (
                                                    <option
                                                        value={
                                                            column
                                                        }
                                                        key={
                                                            column
                                                        }
                                                    >
                                                        {
                                                            column
                                                        }
                                                    </option>
                                                )
                                            )}
                                        </select>
                                    </label>
                                )
                            )}
                        </div>
                    </details>

                    <div className="smart-import-row-preview">
                        <div className="smart-import-row-preview-heading">
                            <strong>
                                Record Preview
                            </strong>

                            <small>
                                IDs marked as
                                generated will be
                                created automatically.
                            </small>
                        </div>

                        <div className="smart-import-preview-table-wrap">
                            <table className="smart-import-preview-table">
                                <thead>
                                    <tr>
                                        <th>
                                            Row
                                        </th>
                                        <th>
                                            Record
                                        </th>
                                        <th>
                                            Result
                                        </th>
                                        <th>
                                            Notes
                                        </th>
                                        <th>
                                            Duplicate Action
                                        </th>
                                    </tr>
                                </thead>

                                <tbody>
                                    {(sheet.rows || []).map(
                                        (row) => (
                                            <tr
                                                key={
                                                    row.id
                                                }
                                            >
                                                <td>
                                                    {
                                                        row.rowNumber
                                                    }
                                                </td>

                                                <td>
                                                    <strong>
                                                        {getRowLabel(
                                                            row
                                                        )}
                                                    </strong>

                                                    {row.generatedCode && (
                                                        <small className="smart-import-generated-code">
                                                            Generated:{" "}
                                                            {
                                                                row.generatedCode
                                                            }
                                                        </small>
                                                    )}
                                                </td>

                                                <td>
                                                    <span
                                                        className={`smart-import-row-status ${row.status.toLowerCase().replaceAll(
                                                            " ",
                                                            "-"
                                                        )}`}
                                                    >
                                                        {
                                                            row.status
                                                        }
                                                    </span>

                                                    {row.duplicateStatus !==
                                                        "New" && (
                                                        <small className="smart-import-duplicate-label">
                                                            {
                                                                row.duplicateStatus
                                                            }
                                                        </small>
                                                    )}
                                                </td>

                                                <td>
                                                    {(row.validationErrors || []).length >
                                                    0 ? (
                                                        <ul className="smart-import-error-list">
                                                            {row.validationErrors.map(
                                                                (
                                                                    error,
                                                                    index
                                                                ) => (
                                                                    <li
                                                                        key={`${row.id}-error-${index}`}
                                                                    >
                                                                        {
                                                                            error
                                                                        }
                                                                    </li>
                                                                )
                                                            )}
                                                        </ul>
                                                    ) : (row.warnings || []).length >
                                                      0 ? (
                                                        <ul className="smart-import-warning-list">
                                                            {row.warnings.map(
                                                                (
                                                                    warning,
                                                                    index
                                                                ) => (
                                                                    <li
                                                                        key={`${row.id}-warning-${index}`}
                                                                    >
                                                                        {
                                                                            warning
                                                                        }
                                                                    </li>
                                                                )
                                                            )}
                                                        </ul>
                                                    ) : (
                                                        <span className="smart-import-ok-text">
                                                            Ready
                                                        </span>
                                                    )}
                                                </td>

                                                <td>
                                                    {row.duplicateStatus !==
                                                    "New" ? (
                                                        <select
                                                            className="smart-import-duplicate-action"
                                                            value={
                                                                rowActions[
                                                                    row.id
                                                                ] ||
                                                                "skip"
                                                            }
                                                            onChange={(
                                                                event
                                                            ) =>
                                                                setRowAction(
                                                                    row.id,
                                                                    event
                                                                        .target
                                                                        .value
                                                                )
                                                            }
                                                        >
                                                            <option value="skip">
                                                                Skip Duplicate
                                                            </option>

                                                            {isAdministrator && (
                                                                <>
                                                                    {!["Livestock Production", "Livestock Processing", "Sales"].includes(
                                                                        sheet.targetType
                                                                    ) && (
                                                                        <option value="update">
                                                                            Update Existing
                                                                        </option>
                                                                    )}
                                                                    <option value="new">
                                                                        {sheet.targetType === "Sales"
                                                                            ? "Import as New Sale"
                                                                            : sheet.targetType === "Livestock Processing"
                                                                              ? "Import as New Processing Record"
                                                                              : sheet.targetType === "Livestock Production"
                                                                                ? "Import as New Production Record"
                                                                                : "Keep as New"}
                                                                    </option>
                                                                </>
                                                            )}
                                                        </select>
                                                    ) : (
                                                        <span className="smart-import-new-label">
                                                            New record
                                                        </span>
                                                    )}
                                                </td>
                                            </tr>
                                        )
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {duplicateRows.length >
                        0 &&
                        !isAdministrator && (
                            <p className="smart-import-permission-note">
                                Farm Staff can
                                safely skip duplicate
                                records. Updating or
                                keeping a duplicate as
                                new requires a System
                                Administrator.
                            </p>
                        )}
                </>
            )}
        </article>
    );
}


export function SmartImportModal({
    open,
    onClose,
    onComplete,
    isAdministrator,
}) {
    const fileInputRef =
        useRef(null);

    const [
        selectedFile,
        setSelectedFile,
    ] = useState(null);

    const [
        preview,
        setPreview,
    ] = useState(null);

    const [
        workingSheets,
        setWorkingSheets,
    ] = useState([]);

    const [
        rowActions,
        setRowActions,
    ] = useState({});

    const [
        mappingDirty,
        setMappingDirty,
    ] = useState(false);

    const [
        busy,
        setBusy,
    ] = useState(false);

    const [
        error,
        setError,
    ] = useState("");

    useEffect(() => {
        if (!open) {
            setSelectedFile(null);
            setPreview(null);
            setWorkingSheets([]);
            setRowActions({});
            setMappingDirty(false);
            setBusy(false);
            setError("");
            return undefined;
        }

        document.body.style.overflow =
            "hidden";

        return () => {
            document.body.style.overflow =
                "";
        };
    }, [open]);

    useEffect(() => {
        if (!preview?.sheets) {
            return;
        }

        setWorkingSheets(
            preview.sheets.map(
                (sheet) => ({
                    ...sheet,
                    included:
                        sheet.included !==
                        false,
                })
            )
        );

        const defaultActions = {};

        preview.sheets.forEach(
            (sheet) => {
                (sheet.rows || []).forEach(
                    (row) => {
                        if (
                            row.duplicateStatus !==
                            "New"
                        ) {
                            defaultActions[
                                row.id
                            ] = "skip";
                        }
                    }
                );
            }
        );

        setRowActions(
            defaultActions
        );
        setMappingDirty(false);
    }, [preview]);

    const totals = useMemo(() => {
        const selectedSheets = workingSheets.filter(
            (sheet) => sheet.included !== false
        );

        const sum = (field) =>
            selectedSheets.reduce(
                (total, sheet) =>
                    total + Number(sheet?.[field] || 0),
                0
            );

        return {
            sheetCount: workingSheets.length,
            selectedSheetCount: selectedSheets.length,
            total: sum("rowCount"),
            valid: sum("validRows"),
            invalid: sum("invalidRows"),
            duplicates: sum("duplicateRows"),
            generated: sum("generatedCodeRows"),
        };
    }, [workingSheets]);

    if (!open) {
        return null;
    }

    const setFile = (file) => {
        if (!file) {
            return;
        }

        const extension =
            file.name
                .split(".")
                .pop()
                ?.toLowerCase();

        if (
            ![
                "xlsx",
                "csv",
                "json",
            ].includes(
                extension
            )
        ) {
            setError(
                "Select an XLSX, CSV, or JSON file. PDF and Word files are not imported automatically."
            );
            return;
        }

        setSelectedFile(file);
        setPreview(null);
        setWorkingSheets([]);
        setRowActions({});
        setMappingDirty(false);
        setError("");
    };

    const analyzeFile = async (
        force = false
    ) => {
        if (!selectedFile) {
            setError(
                "Select a file first."
            );
            return;
        }

        try {
            setBusy(true);
            setError("");

            const result =
                await importService.previewFile(
                    selectedFile,
                    force
                );

            setPreview(result);
        } catch (requestError) {
            console.error(
                "Smart import preview failed:",
                requestError
            );

            setError(
                requestError?.message ||
                    "Unable to analyze the selected file."
            );
        } finally {
            setBusy(false);
        }
    };

    const revalidate = async () => {
        if (!preview?.batch?.id) {
            return;
        }

        try {
            setBusy(true);
            setError("");

            const result =
                await importService.reviewBatch(
                    preview.batch.id,
                    workingSheets
                );

            setPreview(result);
        } catch (requestError) {
            console.error(
                "Import revalidation failed:",
                requestError
            );

            setError(
                requestError?.message ||
                    "Unable to revalidate the column mapping."
            );
        } finally {
            setBusy(false);
        }
    };

    const commitImport = async () => {
        if (!preview?.batch?.id) {
            return;
        }

        if (mappingDirty) {
            setError(
                "Column mapping or sheet settings changed. Click Revalidate Mapping before importing."
            );
            return;
        }

        const selectedDuplicateActions =
            Object.values(
                rowActions
            );

        const privilegedDuplicateAction =
            selectedDuplicateActions.some(
                (action) =>
                    action ===
                        "update" ||
                    action === "new"
            );

        if (
            privilegedDuplicateAction &&
            !isAdministrator
        ) {
            setError(
                "Only a System Administrator can update an existing record or keep a duplicate as new."
            );
            return;
        }

        const confirmed =
            await confirmAction({
                title:
                    "Import Farm Data",
                message:
                    `Import ${totals.valid} validated row(s) from ${totals.selectedSheetCount} selected sheet(s) in ${preview.batch.originalFilename}? Invalid rows will not be imported and duplicate rows will follow the selected actions.`,
                type: "warning",
                confirmText:
                    "Import Records",
                cancelText:
                    "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            setBusy(true);
            setError("");

            const result =
                await importService.commitBatch(
                    preview.batch.id,
                    rowActions,
                    false
                );

            const imported =
                Number(
                    result?.batch
                        ?.importedRows ||
                        0
                );
            const updated =
                Number(
                    result?.batch
                        ?.updatedRows ||
                        0
                );
            const skipped =
                Number(
                    result?.batch
                        ?.skippedRows ||
                        0
                );
            const errorRows =
                Number(
                    result?.batch
                        ?.errorRows ||
                        0
                );
            const message =
                result.message ||
                "Farm data import completed.";

            if (
                errorRows > 0 &&
                imported + updated === 0
            ) {
                notifyError(
                    message,
                    "Import Failed"
                );
            } else if (
                errorRows > 0 ||
                skipped > 0
            ) {
                notifyWarning(
                    message,
                    "Import Completed"
                );
            } else {
                notifySuccess(
                    message,
                    "Import Completed"
                );
            }

            onComplete?.(
                result.batch
            );
            onClose();
        } catch (requestError) {
            console.error(
                "Import commit failed:",
                requestError
            );

            if (
                requestError?.code ===
                    "REQUEST_ABORTED" &&
                preview?.batch?.id
            ) {
                try {
                    const latestBatch =
                        await importService.getBatch(
                            preview.batch.id
                        );

                    if (
                        latestBatch?.status ===
                        "Completed"
                    ) {
                        notifySuccess(
                            latestBatch?.notes ||
                                "Farm data import completed.",
                            "Import Completed"
                        );
                        onComplete?.(latestBatch);
                        onClose();
                        return;
                    }

                    if (
                        latestBatch?.status ===
                        "Importing"
                    ) {
                        setError(
                            "The import is still processing on the server. Do not start another import or reset the database. Wait a moment, then check Smart Import History for the final result."
                        );
                        return;
                    }
                } catch (statusError) {
                    console.warn(
                        "Unable to confirm import status after request timeout:",
                        statusError
                    );
                }
            }

            setError(
                requestError?.message ||
                    "Unable to import the validated records."
            );
        } finally {
            setBusy(false);
        }
    };

    const forceReimportPreview =
        async () => {
            if (!isAdministrator) {
                return;
            }

            const confirmed =
                await confirmAction({
                    title:
                        "Force Re-import",
                    message:
                        "This exact file was previously imported. Continue to a new preview anyway? Record-level duplicate checks will still run before anything is written.",
                    type: "warning",
                    confirmText:
                        "Continue",
                    cancelText:
                        "Cancel",
                });

            if (confirmed) {
                await analyzeFile(
                    true
                );
            }
        };

    return (
        <div
            className="smart-import-overlay"
            onMouseDown={onClose}
        >
            <section
                className="smart-import-modal"
                onMouseDown={(
                    event
                ) =>
                    event.stopPropagation()
                }
            >
                <header className="smart-import-modal-header">
                    <div className="smart-import-modal-title">
                        <span className="material-symbols-outlined">
                            upload_file
                        </span>

                        <div>
                            <h2>
                                Smart Farm Data Import
                            </h2>

                            <p>
                                Detect, validate,
                                map, and preview
                                farm records before
                                writing to the
                                database.
                            </p>
                        </div>
                    </div>

                    <button
                        type="button"
                        aria-label="Close Smart Import"
                        onClick={onClose}
                    >
                        <span className="material-symbols-outlined">
                            close
                        </span>
                    </button>
                </header>

                <div className="smart-import-modal-body">
                    {!preview && (
                        <div
                            className={`smart-import-dropzone ${
                                selectedFile
                                    ? "selected"
                                    : ""
                            }`}
                            onDragOver={(
                                event
                            ) => {
                                event.preventDefault();
                            }}
                            onDrop={(
                                event
                            ) => {
                                event.preventDefault();
                                setFile(
                                    event
                                        .dataTransfer
                                        .files?.[0]
                                );
                            }}
                        >
                            <span className="material-symbols-outlined">
                                cloud_upload
                            </span>

                            <h3>
                                {selectedFile
                                    ? selectedFile.name
                                    : "Drop farm data here"}
                            </h3>

                            <p>
                                {selectedFile
                                    ? `${formatBytes(
                                          selectedFile.size
                                      )} • Ready for analysis`
                                    : "Use XLSX, CSV, or JSON. Workbooks can import Crop, Livestock, Inventory, Reproduction, Production, Processing, and Sales tabs in one validated batch."}
                            </p>

                            <button
                                type="button"
                                onClick={() =>
                                    fileInputRef.current?.click()
                                }
                            >
                                {selectedFile
                                    ? "Choose Another File"
                                    : "Browse File"}
                            </button>

                            <input
                                ref={
                                    fileInputRef
                                }
                                type="file"
                                accept=".xlsx,.csv,.json,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv,application/json"
                                hidden
                                onChange={(
                                    event
                                ) =>
                                    setFile(
                                        event
                                            .target
                                            .files?.[0]
                                    )
                                }
                            />

                            <small>
                                PDF and Word are
                                intentionally not
                                auto-imported to
                                prevent unreliable
                                record extraction.
                            </small>
                        </div>
                    )}

                    {preview?.alreadyImported && (
                        <div className="smart-import-exact-duplicate">
                            <span className="material-symbols-outlined">
                                fingerprint
                            </span>

                            <div>
                                <h3>
                                    This exact file
                                    was already
                                    imported
                                </h3>

                                <p>
                                    The filename may
                                    be different, but
                                    the SHA-256 file
                                    fingerprint
                                    matches a previous
                                    completed import.
                                </p>

                                <dl>
                                    <div>
                                        <dt>
                                            Previous
                                            Batch
                                        </dt>
                                        <dd>
                                            {
                                                preview
                                                    .exactDuplicateBatch
                                                    ?.batchCode
                                            }
                                        </dd>
                                    </div>

                                    <div>
                                        <dt>
                                            File
                                        </dt>
                                        <dd>
                                            {
                                                preview
                                                    .exactDuplicateBatch
                                                    ?.originalFilename
                                            }
                                        </dd>
                                    </div>

                                    <div>
                                        <dt>
                                            Imported
                                        </dt>
                                        <dd>
                                            {formatDateTime(
                                                preview
                                                    .exactDuplicateBatch
                                                    ?.completedAt
                                            )}
                                        </dd>
                                    </div>

                                    <div>
                                        <dt>
                                            Records
                                        </dt>
                                        <dd>
                                            {
                                                preview
                                                    .exactDuplicateBatch
                                                    ?.importedRows
                                            }
                                        </dd>
                                    </div>
                                </dl>
                            </div>
                        </div>
                    )}

                    {preview?.batch && (
                        <>
                            <div className="smart-import-file-summary">
                                <div>
                                    <span className="material-symbols-outlined">
                                        draft
                                    </span>

                                    <div>
                                        <strong>
                                            {
                                                preview
                                                    .batch
                                                    .originalFilename
                                            }
                                        </strong>

                                        <small>
                                            {
                                                preview
                                                    .batch
                                                    .batchCode
                                            }
                                            {" • "}
                                            {
                                                preview
                                                    .batch
                                                    .fileType
                                                    .toUpperCase()
                                            }
                                            {" • "}
                                            {formatBytes(
                                                preview
                                                    .batch
                                                    .fileSizeBytes
                                            )}
                                        </small>
                                    </div>
                                </div>

                                <code title="SHA-256 file fingerprint">
                                    {preview.batch.fileHashSha256.slice(
                                        0,
                                        16
                                    )}
                                    …
                                </code>
                            </div>

                            <div className="smart-import-summary-grid">
                                <ImportSummaryCard
                                    icon="table_rows"
                                    label="Total Rows"
                                    value={
                                        totals.total
                                    }
                                />

                                <ImportSummaryCard
                                    icon="check_circle"
                                    label="Valid"
                                    value={
                                        totals.valid
                                    }
                                    className="valid"
                                />

                                <ImportSummaryCard
                                    icon="error"
                                    label="Invalid"
                                    value={
                                        totals.invalid
                                    }
                                    className="invalid"
                                />

                                <ImportSummaryCard
                                    icon="content_copy"
                                    label="Duplicates"
                                    value={
                                        totals.duplicates
                                    }
                                    className="duplicate"
                                />

                                <ImportSummaryCard
                                    icon="badge"
                                    label="Generated IDs"
                                    value={
                                        totals.generated
                                    }
                                    className="generated"
                                />
                            </div>

                            {preview.requiresAdmin &&
                                !isAdministrator && (
                                    <div className="smart-import-admin-warning">
                                        <span className="material-symbols-outlined">
                                            admin_panel_settings
                                        </span>

                                        <div>
                                            <strong>
                                                Administrator
                                                approval may be
                                                required
                                            </strong>

                                            <ul>
                                                {(preview.adminReasons || []).map(
                                                    (
                                                        reason,
                                                        index
                                                    ) => (
                                                        <li
                                                            key={`admin-reason-${index}`}
                                                        >
                                                            {
                                                                reason
                                                            }
                                                        </li>
                                                    )
                                                )}
                                            </ul>
                                        </div>
                                    </div>
                                )}

                            <WorkbookOverview
                                sheets={workingSheets}
                            />

                            <div className="smart-import-sheet-list">
                                {workingSheets.map(
                                    (
                                        sheet,
                                        index
                                    ) => (
                                        <SheetReviewCard
                                            key={
                                                sheet.sheetName
                                            }
                                            sheet={
                                                sheet
                                            }
                                            catalog={
                                                preview.fieldCatalog
                                            }
                                            rowActions={
                                                rowActions
                                            }
                                            setRowAction={(
                                                rowId,
                                                action
                                            ) =>
                                                setRowActions(
                                                    (
                                                        current
                                                    ) => ({
                                                        ...current,
                                                        [rowId]:
                                                            action,
                                                    })
                                                )
                                            }
                                            onChange={(
                                                nextSheet
                                            ) => {
                                                setMappingDirty(
                                                    true
                                                );

                                                setWorkingSheets(
                                                    (
                                                        current
                                                    ) =>
                                                        current.map(
                                                            (
                                                                item,
                                                                itemIndex
                                                            ) =>
                                                                itemIndex ===
                                                                index
                                                                    ? nextSheet
                                                                    : item
                                                        )
                                                );
                                            }}
                                            isAdministrator={
                                                isAdministrator
                                            }
                                        />
                                    )
                                )}
                            </div>
                        </>
                    )}

                    {error && (
                        <div className="smart-import-error-banner">
                            <span className="material-symbols-outlined">
                                error
                            </span>

                            <p>
                                {error}
                            </p>
                        </div>
                    )}
                </div>

                <footer className="smart-import-modal-footer">
                    <button
                        type="button"
                        className="secondary"
                        onClick={onClose}
                        disabled={busy}
                    >
                        Cancel
                    </button>

                    {!preview && (
                        <button
                            type="button"
                            className="primary"
                            disabled={
                                busy ||
                                !selectedFile
                            }
                            onClick={() =>
                                analyzeFile(
                                    false
                                )
                            }
                        >
                            <span className="material-symbols-outlined">
                                manage_search
                            </span>

                            {busy
                                ? "Analyzing..."
                                : "Analyze File"}
                        </button>
                    )}

                    {preview?.alreadyImported && (
                        <>
                            <button
                                type="button"
                                className="secondary"
                                onClick={() => {
                                    setPreview(
                                        null
                                    );
                                }}
                            >
                                Choose Another
                            </button>

                            {isAdministrator && (
                                <button
                                    type="button"
                                    className="warning"
                                    disabled={
                                        busy
                                    }
                                    onClick={
                                        forceReimportPreview
                                    }
                                >
                                    Force Re-import
                                    Preview
                                </button>
                            )}
                        </>
                    )}

                    {preview?.batch && (
                        <>
                            {(totals.invalid >
                                0 ||
                                preview.batch
                                    .errorRows >
                                    0) && (
                                <button
                                    type="button"
                                    className="secondary"
                                    disabled={
                                        busy
                                    }
                                    onClick={() =>
                                        importService.downloadErrors(
                                            preview.batch
                                        )
                                    }
                                >
                                    <span className="material-symbols-outlined">
                                        download
                                    </span>

                                    Error CSV
                                </button>
                            )}

                            <button
                                type="button"
                                className="secondary"
                                disabled={busy}
                                onClick={
                                    revalidate
                                }
                            >
                                <span className="material-symbols-outlined">
                                    fact_check
                                </span>

                                {busy
                                    ? "Checking..."
                                    : "Revalidate Mapping"}
                            </button>

                            <button
                                type="button"
                                className="primary"
                                disabled={
                                    busy ||
                                    totals.valid ===
                                        0 ||
                                    mappingDirty ||
                                    (preview.requiresAdmin &&
                                        !isAdministrator &&
                                        preview.batch
                                            .totalRows >
                                            100)
                                }
                                onClick={
                                    commitImport
                                }
                            >
                                <span className="material-symbols-outlined">
                                    database
                                </span>

                                {busy
                                    ? "Importing..."
                                    : mappingDirty
                                    ? "Revalidate Mapping First"
                                    : `Import ${totals.valid} Valid Record(s)`}
                            </button>
                        </>
                    )}
                </footer>
            </section>
        </div>
    );
}


export function ImportHistoryPanel({
    isAdministrator,
    refreshKey = 0,
}) {
    const [
        history,
        setHistory,
    ] = useState([]);

    const [
        loading,
        setLoading,
    ] = useState(true);

    const [
        error,
        setError,
    ] = useState("");

    const loadHistory = async () => {
        try {
            setLoading(true);
            setError("");

            const records =
                await importService.getHistory(
                    50
                );

            setHistory(
                (records || []).filter(
                    (record) =>
                        [
                            "Completed",
                            "Rolled Back",
                            "Failed",
                        ].includes(
                            record.status
                        )
                )
            );
        } catch (requestError) {
            console.error(
                "Failed to load import history:",
                requestError
            );

            setError(
                requestError?.message ||
                    "Unable to load import history."
            );
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadHistory();
    }, [refreshKey]);

    const rollback = async (
        batch
    ) => {
        if (!isAdministrator) {
            return;
        }

        const confirmed =
            await confirmAction({
                title:
                    "Rollback Import",
                message:
                    `Rollback ${batch.batchCode}? Records created by this import will be removed and records updated by it will be restored to their previous values.`,
                type: "error",
                confirmText:
                    "Rollback Import",
                cancelText:
                    "Cancel",
            });

        if (!confirmed) {
            return;
        }

        try {
            await importService.rollbackBatch(
                batch.id,
                false
            );

            notify(
                `${batch.batchCode} was rolled back successfully.`
            );

            await loadHistory();
        } catch (requestError) {
            console.error(
                "Import rollback failed:",
                requestError
            );

            notify(
                requestError?.message ||
                    "Unable to rollback the import batch."
            );
        }
    };

    return (
        <article className="smart-import-history-card">
            <div className="smart-import-history-heading">
                <div>
                    <h2>
                        Import History
                    </h2>

                    <p>
                        Audited farm-data import
                        batches, duplicate results,
                        and rollback status.
                    </p>
                </div>

                <button
                    type="button"
                    title="Refresh import history"
                    onClick={
                        loadHistory
                    }
                >
                    <span className="material-symbols-outlined">
                        refresh
                    </span>
                </button>
            </div>

            <div className="smart-import-history-table-wrap">
                <table className="smart-import-history-table">
                    <thead>
                        <tr>
                            <th>
                                Batch / File
                            </th>
                            <th>
                                Imported
                            </th>
                            <th>
                                Status
                            </th>
                            <th>
                                New
                            </th>
                            <th>
                                Updated
                            </th>
                            <th>
                                Skipped
                            </th>
                            <th>
                                Errors
                            </th>
                            <th>
                                Imported By
                            </th>
                            <th>
                                Actions
                            </th>
                        </tr>
                    </thead>

                    <tbody>
                        {history.length >
                        0 ? (
                            history.map(
                                (batch) => (
                                    <tr
                                        key={
                                            batch.id
                                        }
                                    >
                                        <td>
                                            <strong>
                                                {
                                                    batch.batchCode
                                                }
                                            </strong>

                                            <small>
                                                {
                                                    batch.originalFilename
                                                }
                                            </small>
                                        </td>

                                        <td>
                                            {formatDateTime(
                                                batch.completedAt ||
                                                    batch.createdAt
                                            )}
                                        </td>

                                        <td>
                                            <span
                                                className={`smart-import-history-status ${batch.status
                                                    .toLowerCase()
                                                    .replaceAll(
                                                        " ",
                                                        "-"
                                                    )}`}
                                            >
                                                {
                                                    batch.status
                                                }
                                            </span>
                                        </td>

                                        <td>
                                            {
                                                batch.importedRows
                                            }
                                        </td>

                                        <td>
                                            {
                                                batch.updatedRows
                                            }
                                        </td>

                                        <td>
                                            {
                                                batch.skippedRows
                                            }
                                        </td>

                                        <td>
                                            {
                                                batch.errorRows
                                            }
                                        </td>

                                        <td>
                                            {batch.importedByName ||
                                                "System User"}
                                        </td>

                                        <td>
                                            <div className="smart-import-history-actions">
                                                {batch.errorRows >
                                                    0 && (
                                                    <button
                                                        type="button"
                                                        title="Download error CSV"
                                                        onClick={() =>
                                                            importService.downloadErrors(
                                                                batch
                                                            )
                                                        }
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            download
                                                        </span>
                                                    </button>
                                                )}

                                                {isAdministrator &&
                                                    batch.canRollback && (
                                                        <button
                                                            type="button"
                                                            className="rollback"
                                                            title="Rollback this import"
                                                            onClick={() =>
                                                                rollback(
                                                                    batch
                                                                )
                                                            }
                                                        >
                                                            <span className="material-symbols-outlined">
                                                                undo
                                                            </span>
                                                        </button>
                                                    )}
                                            </div>
                                        </td>
                                    </tr>
                                )
                            )
                        ) : (
                            <tr>
                                <td
                                    colSpan="9"
                                    className="smart-import-history-empty"
                                >
                                    <span className="material-symbols-outlined">
                                        upload_file
                                    </span>

                                    <p>
                                        {loading
                                            ? "Loading import history..."
                                            : error ||
                                              "No completed farm-data import has been recorded yet."}
                                    </p>
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            <footer>
                {error
                    ? error
                    : `Showing ${history.length} completed import batch(es)`}
            </footer>
        </article>
    );
}
