"use client";

import ArchiveWorkspace from "../../components/Archives/Archives.jsx";

import { useState } from "react";

import Sidebar from "../../components/Sidebar/Sidebar.jsx";
import { useAuth } from "../../context/AuthContext.jsx";
import AutomaticReportsModal from "./components/AutomaticReportsModal.jsx";
import ReportDetailsModal from "./components/ReportDetailsModal.jsx";
import ReportFormModal from "./components/ReportFormModal.jsx";
import ReportsAnalytics from "./components/ReportsAnalytics.jsx";
import ReportsHeader from "./components/ReportsHeader.jsx";
import ReportsOverview from "./components/ReportsOverview.jsx";
import ReportsTable from "./components/ReportsTable.jsx";
import ReportsToolbar from "./components/ReportsToolbar.jsx";
import useReportsData from "./hooks/useReportsData.js";
import useReportsPageState from "./hooks/useReportsPageState.js";

import "./Reports.css";

// Main reports page
function Reports() {
    const { user, hasPermission } = useAuth();
    const canApprove = hasPermission("*");

    const [reportFormOpen, setReportFormOpen] = useState(false);
    const [automationOpen, setAutomationOpen] = useState(false);

    const {
        activeTab, setActiveTab, searchText, setSearchText,
        categoryFilter, setCategoryFilter, statusFilter, setStatusFilter,
        startDateFilter, setStartDateFilter, endDateFilter, setEndDateFilter,
        reportQuery, clearFilters,
    } = useReportsPageState();

    // Report data and actions
    const {
        reports,
        reportSummary,
        selectedReport,
        setSelectedReport,
        reportsLoading,
        reportsError,
        reportsHasMore,
        reportsLoadingMore,
        loadMoreReports,
        automationSettings,
        automationLoading,
        createReport,
        previewReportPdf,
        exportSingleReport,
        downloadSupportingData,
        submitReportForReview,
        approveReport,
        createReportRevision,
        saveAutomationSettings,
        runAutomaticReportsNow,
        archiveReport,
    } = useReportsData(reportQuery);

    const handleSaveReport = async (formData) => {
        const created = await createReport(formData);
        if (created) setReportFormOpen(false);
    };

    const handleSaveAutomationSettings = async (settings) => {
        const saved = await saveAutomationSettings(settings);
        if (saved) setAutomationOpen(false);
        return saved;
    };

    return (
        <div className="reports-page-layout">
            <Sidebar />

            <main className="reports-page-content">
                <ReportsHeader />

                <ReportsOverview summary={reportSummary} />

                <ArchiveWorkspace module="Report" before={<>
                <ReportsToolbar
                    activeTab={activeTab}
                    onTabChange={setActiveTab}
                    searchText={searchText}
                    onSearchChange={setSearchText}
                    categoryFilter={categoryFilter}
                    onCategoryChange={setCategoryFilter}
                    statusFilter={statusFilter}
                    onStatusChange={setStatusFilter}
                    startDate={startDateFilter}
                    onStartDateChange={setStartDateFilter}
                    endDate={endDateFilter}
                    onEndDateChange={setEndDateFilter}
                    onReset={clearFilters}
                />

                </>}>
                {(navigation) => <>
                <ReportsTable
                    navigation={navigation}
                    actions={<>
                        <button type="button" className="reports-page-print-button" onClick={() => setAutomationOpen(true)}><span className="material-symbols-outlined" aria-hidden="true">schedule</span>Automatic Reports</button>
                        <button type="button" className="reports-page-generate-button" onClick={() => setReportFormOpen(true)}><span className="material-symbols-outlined" aria-hidden="true">add</span>Generate Custom Report</button>
                    </>}
                    reports={reports}
                    filteredReports={reports}
                    matchingTotal={reportSummary?.matchingTotal}
                    reportsLoading={reportsLoading}
                    reportsError={reportsError}
                    canApprove={canApprove}
                    onPreview={previewReportPdf}
                    onViewDetails={setSelectedReport}
                    onDownload={exportSingleReport}
                    onSubmitReview={submitReportForReview}
                    onApprove={approveReport}
                    onCreateRevision={createReportRevision}
                    onArchive={archiveReport}
                    hasMore={reportsHasMore}
                    loadingMore={reportsLoadingMore}
                    onLoadMore={loadMoreReports}
                />

                <ReportsAnalytics activeTab={activeTab} reports={reports} />
                </>}
                </ArchiveWorkspace>
            </main>

            <AutomaticReportsModal
                open={automationOpen}
                settings={automationSettings}
                defaultPreparedBy={user?.fullName || user?.name || "Farm Personnel"}
                loading={automationLoading}
                onClose={() => setAutomationOpen(false)}
                onSave={handleSaveAutomationSettings}
                onRunNow={runAutomaticReportsNow}
            />

            <ReportFormModal
                open={reportFormOpen}
                initialTab={activeTab}
                defaultPreparedBy={user?.fullName || user?.name || "Farm Personnel"}
                onClose={() => setReportFormOpen(false)}
                onSave={handleSaveReport}
            />

            <ReportDetailsModal
                report={selectedReport}
                onClose={() => setSelectedReport(null)}
                onExport={exportSingleReport}
                onDataExport={downloadSupportingData}
                onSubmit={submitReportForReview}
                onApprove={approveReport}
                onRevision={createReportRevision}
                canApprove={canApprove}
            />
        </div>
    );
}

export default Reports;
