"use client";

import { useEffect, useState } from "react";

import { reportService } from "../../../services/reportService.js";
import {
    formatDate,
    formatDateTime,
    formatMetricLabel,
    formatMetricValue,
    getCategoryIcon,
    getClassName,
} from "../reportUtils.js";

// Shows the full report details and workflow actions
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

    const defaultSections = [
        "executive_summary",
        "kpi_overview",
        "period_comparison",
        "performance_variance",
        "detailed_analysis",
        "findings",
        "risks",
        "recommendations",
        "data_quality",
        "appendix",
    ];
    const includedSections = new Set(
        report.includedSections?.length ? report.includedSections : defaultSections
    );
    const showSection = (key) => includedSections.has(key);
    const executiveKpis = report.executiveKpis || [];
    const varianceRows = report.performanceVariance || [];
    const riskFlags = report.riskFlags || [];

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

                    {showSection("executive_summary") && (
                        <section className="reports-page-details-section">
                            <h3>Executive Summary</h3>
                            <p>{report.summary}</p>
                        </section>
                    )}

                    {showSection("kpi_overview") && executiveKpis.length > 0 && (
                        <section className="reports-page-details-section">
                            <h3>Executive KPI Overview</h3>
                            <div className="reports-page-detail-kpi-grid">
                                {executiveKpis.map((item) => (
                                    <div className="reports-page-detail-kpi" key={item.label}>
                                        <small>{item.label}</small>
                                        <strong>
                                            {item.unit === "PHP"
                                                ? `₱${Number(item.value || 0).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                                                : `${formatMetricValue(item.value)}${item.unit ? ` ${item.unit}` : ""}`}
                                        </strong>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {showSection("period_comparison") && (
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
                    )}

                    {showSection("performance_variance") && varianceRows.length > 0 && (
                        <section className="reports-page-details-section">
                            <h3>Performance &amp; Variance</h3>
                            <p className="reports-page-muted-copy">
                                Uses only recorded plans, biological capacity, schedule references, or other defensible baselines.
                            </p>
                            <div className="reports-page-comparison-table-wrap">
                                <table className="reports-page-comparison-table">
                                    <thead>
                                        <tr><th>Metric</th><th>Actual</th><th>Reference</th><th>Variance</th><th>Change</th></tr>
                                    </thead>
                                    <tbody>
                                        {varianceRows.map((item) => (
                                            <tr key={item.metric}>
                                                <td>{item.metric}</td>
                                                <td>{formatMetricValue(item.actual)} {item.unit}</td>
                                                <td>{formatMetricValue(item.reference)} {item.unit}</td>
                                                <td className={`reports-page-change ${item.assessment || "neutral"}`}>
                                                    {Number(item.variance || 0) > 0 ? "+" : ""}{formatMetricValue(item.variance)}
                                                </td>
                                                <td>{item.variancePercent == null ? "N/A" : `${Number(item.variancePercent) > 0 ? "+" : ""}${formatMetricValue(item.variancePercent)}%`}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    )}

                    {(showSection("findings") || showSection("recommendations")) && (
                    <section className="reports-page-details-two-column">
                        {showSection("findings") && (
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
                        )}

                        {showSection("recommendations") && (
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
                        )}
                    </section>
                    )}

                    {showSection("risks") && riskFlags.length > 0 && (
                        <section className="reports-page-details-section">
                            <h3>Risks &amp; Issues</h3>
                            <div className="reports-page-risk-list">
                                {riskFlags.map((risk, index) => (
                                    <div className={`reports-page-risk-item ${getClassName(risk.level)}`} key={`${risk.area}-${index}`}>
                                        <span className="material-symbols-outlined">warning</span>
                                        <div>
                                            <strong>{risk.level} • {risk.area}</strong>
                                            <p>{risk.issue}</p>
                                            <small>{risk.action}</small>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </section>
                    )}

                    {showSection("data_quality") && (
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
                    )}

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

                    {["Approved", "Final", "Revised"].includes(report.status) && (
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

export default ReportDetailsModal;
