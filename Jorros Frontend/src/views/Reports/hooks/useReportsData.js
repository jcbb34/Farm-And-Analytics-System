import useReportPdfJobs from "./useReportPdfJobs.js";
import { requestArchive } from "../../../services/archiveService.js";
import { notify } from "../../../context/NotificationContext.jsx";
import { useCallback, useEffect, useRef, useState } from "react";

import { confirmAction } from "../../../context/NotificationContext.jsx";
import {
    addTimelineEntry,
    logAudit,
} from "../../../services/farmIntelligenceService.js";
import { reportService } from "../../../services/reportService.js";
import useFarmModuleUpdates from "../../../hooks/useFarmModuleUpdates.js";

// Loads report data and keeps report actions in one place
export default function useReportsData(reportQuery) {
    const [reports, setReports] = useState([]);
    const { pdfJobs, pdfJobsError, refreshPdfJobs } = useReportPdfJobs(reports);
    const [reportSummary, setReportSummary] = useState(null);
    const [selectedReport, setSelectedReport] = useState(null);
    const [reportsLoading, setReportsLoading] = useState(true);
    const [reportsError, setReportsError] = useState("");
    const [summaryLoading, setSummaryLoading] = useState(true);
    const [summaryError, setSummaryError] = useState("");
    const [automationSettings, setAutomationSettings] = useState(null);
    const [automationLoading, setAutomationLoading] = useState(false);
    const [reportsHasMore, setReportsHasMore] = useState(false);
    const [reportsLoadingMore, setReportsLoadingMore] = useState(false);
    const reportsPageSize = 25;
    const requestSequence = useRef(0), rowsRequest = useRef(null);
    const summarySequence = useRef(0), summaryRequest = useRef(null);
    const loadedQuery = useRef(""), summaryState = useRef({ key: "", value: null });
    const nextOffset = useRef(0);
    const loadingMoreRef = useRef(false);
    const queryKey = JSON.stringify(reportQuery);

    // A failed summary must not prevent otherwise successful report rows from appearing.
    const loadReportRows = useCallback(async () => {
        const requestId = ++requestSequence.current;
        rowsRequest.current?.abort();
        const controller = new AbortController(); rowsRequest.current = controller;
        loadingMoreRef.current = false;
        setReportsLoading(true); setReportsLoadingMore(false); setReportsError("");
        if (loadedQuery.current !== queryKey) { setReports([]); nextOffset.current = 0; setReportsHasMore(false); }
        loadedQuery.current = queryKey;
        try {
            const records = await reportService.getReports(false, { ...JSON.parse(queryKey), offset: 0, limit: reportsPageSize, signal: controller.signal });
            if (requestId !== requestSequence.current || controller.signal.aborted) return;
            setReports(records); nextOffset.current = records.length;
            const summary = summaryState.current.key === queryKey ? summaryState.current.value : null;
            setReportsHasMore(summary ? records.length < summary.matchingTotal : records.length === reportsPageSize);
        } catch (error) {
            if (requestId === requestSequence.current && !controller.signal.aborted) setReportsError(error?.message || "Unable to load report records.");
        } finally {
            if (requestId === requestSequence.current) { setReportsLoading(false); rowsRequest.current = null; }
        }
    }, [queryKey]);

    const loadReportSummary = useCallback(async () => {
        const requestId = ++summarySequence.current;
        summaryRequest.current?.abort();
        const controller = new AbortController(); summaryRequest.current = controller;
        setSummaryLoading(true); setSummaryError("");
        if (summaryState.current.key !== queryKey) { setReportSummary(null); summaryState.current = { key: queryKey, value: null }; }
        try {
            const summary = await reportService.getReportSummary({ ...JSON.parse(queryKey), signal: controller.signal });
            if (requestId !== summarySequence.current || controller.signal.aborted) return;
            summaryState.current = { key: queryKey, value: summary }; setReportSummary(summary);
            if (loadedQuery.current === queryKey) setReportsHasMore(nextOffset.current < summary.matchingTotal);
        } catch (error) {
            if (requestId === summarySequence.current && !controller.signal.aborted) setSummaryError(error?.message || "Unable to load report totals.");
        } finally {
            if (requestId === summarySequence.current) { setSummaryLoading(false); summaryRequest.current = null; }
        }
    }, [queryKey]);

    const loadReports = useCallback(() => Promise.all([loadReportRows(), loadReportSummary()]), [loadReportRows, loadReportSummary]);
    const loadMoreReports = useCallback(async () => {
        if (loadingMoreRef.current || reportsLoading || !reportsHasMore) return;
        loadingMoreRef.current = true;
        const requestId = requestSequence.current;
        const controller = new AbortController(); rowsRequest.current = controller;
        try {
            setReportsLoadingMore(true);
            const records = await reportService.getReports(false, {
                ...JSON.parse(queryKey), offset: nextOffset.current, limit: reportsPageSize, signal: controller.signal,
            });
            if (requestId !== requestSequence.current || controller.signal.aborted) return;
            nextOffset.current += records.length;
            setReports(current => {
                const existing = new Set(current.map(item => item.id));
                return [...current, ...records.filter(item => !existing.has(item.id))];
            });
            const summary = summaryState.current.key === queryKey ? summaryState.current.value : null;
            setReportsHasMore(records.length > 0 && (summary ? nextOffset.current < summary.matchingTotal : records.length === reportsPageSize));
        } catch (error) {
            if (requestId === requestSequence.current && !controller.signal.aborted) setReportsError(error?.message || "Unable to load more report records.");
        } finally {
            if (requestId === requestSequence.current) { loadingMoreRef.current = false; setReportsLoadingMore(false); rowsRequest.current = null; }
        }
    }, [queryKey, reportsHasMore, reportsLoading]);

    // Load automatic report settings
    const loadAutomationSettings = useCallback(async () => {
        try {
            setAutomationLoading(true);
            const settings = await reportService.getAutomationSettings();
            setAutomationSettings(settings);
        } catch (error) {
            console.error("Failed to load automatic report settings:", error);
        } finally {
            setAutomationLoading(false);
        }
    }, []);

    useEffect(() => {
        loadReports();
        return () => { ++requestSequence.current; ++summarySequence.current; rowsRequest.current?.abort(); summaryRequest.current?.abort(); };
    }, [loadReports]);
    useEffect(() => { loadAutomationSettings(); }, [loadAutomationSettings]);
    useFarmModuleUpdates(["reports"], loadReports);

    const replaceReportInState = useCallback((updatedReport) => {
        setReports((currentReports) =>
            currentReports.map((item) =>
                item.id === updatedReport.id ? updatedReport : item
            )
        );

        setSelectedReport((current) =>
            current?.id === updatedReport.id ? updatedReport : current
        );
    }, []);

    // Generate a custom report
    const createReport = useCallback(async (formData) => {
        try {
            const newReport = await reportService.generateReport(formData);

            await loadReports();

            logAudit({
                action: "Generated farm report",
                module: "Report",
                recordName: newReport.title,
                entityId: newReport.reportCode,
                details: `${newReport.category} • ${newReport.reportType}`,
            });

            addTimelineEntry({
                module: "Report",
                recordName: newReport.title,
                entityId: newReport.reportCode,
                title: "Report generated",
                details: `${newReport.startDate} to ${newReport.endDate}`,
                icon: "description",
            });

            notify("Report generated successfully.");
            return newReport;
        } catch (error) {
            console.error("Failed to generate report:", error);
            notify(error?.message || "Unable to generate the report.");
            return null;
        }
    }, [loadReports]);

    // PDF and supporting data actions
    const previewReportPdf = useCallback(async (report) => {
        try {
            const job = await reportService.previewPdf(report);
            if (job && job.status !== "Ready") notify(job.status === "Failed" ? job.error || "PDF generation failed. Retry the PDF." : "PDF queued. Preview it when its status is Ready.");
        } catch (error) {
            if (!error?.pdfJob) console.error("Failed to preview report PDF:", error);
            notify(error?.message || "Unable to open the report PDF.");
        } finally { void refreshPdfJobs({ force: true }); }
    }, [refreshPdfJobs]);

    const exportSingleReport = useCallback(async (report) => {
        try {
            const job = await reportService.downloadPdf(report);
            if (job && job.status !== "Ready") notify(job.status === "Failed" ? job.error || "PDF generation failed. Retry the PDF." : "PDF queued. Download it when its status is Ready.");
        } catch (error) {
            if (!error?.pdfJob) console.error("Failed to download report PDF:", error);
            notify(error?.message || "Unable to download the report PDF.");
        } finally { void refreshPdfJobs({ force: true }); }
    }, [refreshPdfJobs]);

    const downloadSupportingData = useCallback(async (report) => {
        try {
            await reportService.downloadSupportingData(report);
        } catch (error) {
            console.error("Failed to download supporting report data:", error);
            notify(
                error?.message || "Unable to download the supporting report data."
            );
        }
    }, []);

    // Report workflow actions
    const submitReportForReview = useCallback(
        async (report) => {
            try {
                const updated = await reportService.submitReport(report.id);
                replaceReportInState(updated);
                await loadReports();
                notify(`${updated.title} was submitted for review.`);
            } catch (error) {
                console.error("Failed to submit report:", error);
                notify(
                    error?.message || "Unable to submit the report for review."
                );
            }
        },
        [loadReports, replaceReportInState]
    );

    const approveReport = useCallback(
        async (report) => {
            const confirmed = await confirmAction({
                title: "Approve Report",
                message: `Approve "${report.title}" as an official locked report?`,
                type: "success",
                confirmText: "Approve",
                cancelText: "Cancel",
            });

            if (!confirmed) return;

            try {
                const updated = await reportService.approveReport(report.id);
                replaceReportInState(updated);
                await loadReports();
                notify(`${updated.title} was approved successfully.`);
            } catch (error) {
                console.error("Failed to approve report:", error);
                notify(error?.message || "Unable to approve the report.");
            }
        },
        [loadReports, replaceReportInState]
    );

    const createReportRevision = useCallback(async (report) => {
        const confirmed = await confirmAction({
            title: "Create Report Revision",
            message: `Create a new editable revision of "${report.title}"? The approved version will remain unchanged.`,
            type: "info",
            confirmText: "Create Revision",
            cancelText: "Cancel",
        });

        if (!confirmed) return;

        try {
            const revision = await reportService.createRevision(report.id);
            setSelectedReport(revision);
            await loadReports();
            notify(
                `Revision ${revision.revisionNumber} was created and preserved as a separate report version.`
            );
        } catch (error) {
            console.error("Failed to create report revision:", error);
            notify(
                error?.message || "Unable to create the report revision."
            );
        }
    }, [loadReports]);

    // Automatic report schedule
    const saveAutomationSettings = useCallback(async (settings) => {
        try {
            setAutomationLoading(true);
            const saved = await reportService.updateAutomationSettings(settings);
            setAutomationSettings(saved);
            return saved;
        } catch (error) {
            console.error("Failed to save automatic report settings:", error);
            notify(
                error?.message || "Unable to save automatic report settings."
            );
            return null;
        } finally {
            setAutomationLoading(false);
        }
    }, []);

    const runAutomaticReportsNow = useCallback(
        async (settings) => {
            const saved = await saveAutomationSettings(settings);
            if (!saved) return;

            try {
                setAutomationLoading(true);
                const result = await reportService.runAutomationNow();

                await Promise.all([loadReports(), loadAutomationSettings()]);

                notify(
                    result.message ||
                        `${result.generatedCount} automatic report(s) generated.`
                );
            } catch (error) {
                console.error("Failed to run automatic reports:", error);
                notify(
                    error?.message || "Unable to run automatic reports."
                );
            } finally {
                setAutomationLoading(false);
            }
        },
        [loadAutomationSettings, loadReports, saveAutomationSettings]
    );

    // Archive a report
    const archiveReport = useCallback(async (report) => {
        const confirmed = await requestArchive("Report", report.id, report.title);

        if (!confirmed) return;

        try {
            const archivedReport = confirmed;

            setSelectedReport((current) =>
                current?.id === archivedReport.id ? null : current
            );
            await loadReports();

            logAudit({
                action: "Archived farm report",
                module: "Report",
                recordName: report.title,
                entityId: report.reportCode,
                details: report.reportType,
            });

            addTimelineEntry({
                module: "Report",
                recordName: report.title,
                entityId: report.reportCode,
                title: "Report archived",
                details: report.reportType,
                icon: "archive",
            });

            notify(`${report.title} was archived successfully.`);
        } catch (error) {
            console.error("Failed to archive report:", error);
            notify(error?.message || "Unable to archive the report.");
        }
    }, [loadReports]);

    return {
        reports,
        pdfJobs, pdfJobsError, refreshPdfJobs,
        reportSummary,
        selectedReport,
        setSelectedReport,
        reportsLoading,
        reportsError, summaryLoading, summaryError, loadReportSummary, loadReportRows,
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
    };
}
