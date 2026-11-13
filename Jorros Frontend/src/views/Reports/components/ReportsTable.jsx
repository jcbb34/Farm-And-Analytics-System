import { RecordHeader, RecordTableSurface } from "../../../components/Records/RecordsLayout.jsx";

import {
    formatDate,
    getCategoryIcon,
    getClassName,
} from "../reportUtils.js";

// Main table for generated report records
export default function ReportsTable({
    navigation,
    actions,
    reports,
    pdfJobs = {},
    filteredReports,
    matchingTotal,
    reportsLoading,
    reportsError,
    canApprove,
    onPreview,
    onViewDetails,
    onDownload,
    onSubmitReview,
    onApprove,
    onCreateRevision,
    onArchive,
    hasMore = false,
    loadingMore = false,
    onLoadMore,
}) {
    return (
        <>
        <RecordHeader title="Generated Reports" navigation={navigation} actions={actions}
            summary={reportsLoading ? "Loading report records..." : matchingTotal == null ? `${filteredReports.length} report records loaded · total unavailable` : `${matchingTotal} report records found`}/>
        <RecordTableSurface className="reports-page-table-card" scrollClassName="reports-page-table-wrapper" busy={reportsLoading} footer={<div className="reports-page-table-footer records-footer">
                <span>{reportsLoading ? "Loading report records..." : matchingTotal == null ? `Showing ${reports.length} loaded report records` : `Showing ${reports.length} of ${matchingTotal} matching report records`}</span>
                {hasMore && (
                    <button
                        type="button"
                        className="reports-page-load-more-button"
                        onClick={onLoadMore}
                        disabled={loadingMore || reportsLoading}
                    >
                        {loadingMore ? "Loading…" : "Load More Reports"}
                    </button>
                )}
                {reportsError && reports.length > 0 && <span role="alert">{reportsError}</span>}
            </div>}>

                <table className="reports-page-table">
                    <thead>
                        <tr>
                            <th>Report</th>
                            <th>Category</th>
                            <th>Report Type</th>
                            <th>Period</th>
                            <th>Generated</th>
                            <th>Prepared By</th>
                            <th>Status</th>
                            <th>Actions</th>
                        </tr>
                    </thead>

                    <tbody>
                        {filteredReports.length > 0 ? (
                            filteredReports.map((report) => (
                                <tr key={report.id}>
                                    <td>
                                        <div className="reports-page-name-cell">
                                            <span
                                                className={`reports-page-category-icon ${getClassName(
                                                    report.category
                                                )}`}
                                            >
                                                <span className="material-symbols-outlined">
                                                    {getCategoryIcon(report.category)}
                                                </span>
                                            </span>

                                            <div>
                                                <strong>{report.title}</strong>
                                                <small className={`report-pdf-status ${pdfJobs[report.id]?.status === "Failed" ? "failed" : ""}`} title={pdfJobs[report.id]?.error || undefined}>PDF: {pdfJobs[report.id]?.status || "…"}</small>
                                                <small>
                                                    {report.reportCode}
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
                                            {report.category}
                                        </span>
                                    </td>

                                    <td>{report.reportType}</td>

                                    <td>
                                        <strong className="reports-page-period">
                                            {formatDate(report.startDate)}
                                        </strong>
                                        <small className="reports-page-period-end">
                                            to {formatDate(report.endDate)}
                                        </small>
                                    </td>

                                    <td>{formatDate(report.generatedDate)}</td>
                                    <td>{report.preparedBy}</td>

                                    <td>
                                        <span
                                            className={`reports-page-status ${getClassName(
                                                report.status
                                            )}`}
                                        >
                                            {report.status}
                                        </span>
                                    </td>

                                    <td>
                                        <div className="reports-page-row-actions records-row-actions">
                                            <button
                                                type="button"
                                                title="Preview professional PDF"
                                                disabled={["Queued", "Generating"].includes(pdfJobs[report.id]?.status)}
                                                onClick={() => onPreview(report)}
                                            >
                                                <span className="material-symbols-outlined">
                                                    visibility
                                                </span>
                                            </button>

                                            <button
                                                type="button"
                                                title="View report details"
                                                onClick={() => onViewDetails(report)}
                                            >
                                                <span className="material-symbols-outlined">
                                                    info
                                                </span>
                                            </button>

                                            <button
                                                type="button"
                                                title={pdfJobs[report.id]?.status === "Failed" ? "Retry PDF" : "Download PDF"}
                                                disabled={["Queued", "Generating"].includes(pdfJobs[report.id]?.status)}
                                                onClick={() => onDownload(report)}
                                            >
                                                <span className="material-symbols-outlined">
                                                    picture_as_pdf
                                                </span>
                                            </button>

                                            {report.status === "Draft" && (
                                                <button
                                                    type="button"
                                                    className="workflow"
                                                    title="Submit for review"
                                                    onClick={() => onSubmitReview(report)}
                                                >
                                                    <span className="material-symbols-outlined">
                                                        send
                                                    </span>
                                                </button>
                                            )}

                                            {report.status === "For Review" &&
                                                canApprove && (
                                                    <button
                                                        type="button"
                                                        className="workflow approve"
                                                        title="Approve report"
                                                        onClick={() => onApprove(report)}
                                                    >
                                                        <span className="material-symbols-outlined">
                                                            verified
                                                        </span>
                                                    </button>
                                                )}

                                            {["Approved", "Final", "Revised"].includes(report.status) && (
                                                <button
                                                    type="button"
                                                    className="workflow revision"
                                                    title="Create revision"
                                                    onClick={() => onCreateRevision(report)}
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
                                                onClick={() => onArchive(report)}
                                            >
                                                <span className="material-symbols-outlined">
                                                    archive
                                                </span>
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))
                        ) : (
                            <tr>
                                <td colSpan="8" className="reports-page-empty-table">
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


        </RecordTableSurface>
        </>
    );
}
