import { httpClient } from "./httpClient.js";


function camelizeKey(value) {
    return String(value).replace(
        /_([a-z])/g,
        (_, character) =>
            character.toUpperCase()
    );
}


function normalizeObject(value) {
    if (Array.isArray(value)) {
        return value.map(
            normalizeObject
        );
    }

    if (
        value &&
        typeof value ===
            "object"
    ) {
        return Object.fromEntries(
            Object.entries(
                value
            ).map(
                ([
                    key,
                    itemValue,
                ]) => [
                    camelizeKey(
                        key
                    ),
                    normalizeObject(
                        itemValue
                    ),
                ]
            )
        );
    }

    return value;
}


function normalizeReport(
    record = {}
) {
    return {
        id:
            record.id,

        reportCode:
            record.reportCode ??
            record.report_code ??
            "",

        title:
            record.title ??
            "",

        category:
            record.category ??
            "Farm",

        reportType:
            record.reportType ??
            record.report_type ??
            "",

        startDate:
            record.startDate ??
            record.start_date ??
            "",

        endDate:
            record.endDate ??
            record.end_date ??
            "",

        generatedDate:
            record.generatedDate ??
            record.generated_date ??
            "",

        preparedBy:
            record.preparedBy ??
            record.prepared_by ??
            "",

        status:
            record.status ??
            "Draft",

        summary:
            record.summary ??
            "",

        snapshot:
            normalizeObject(
                record.snapshot ??
                    {}
            ),

        comparison:
            normalizeObject(
                record.comparison ??
                    {}
            ),

        findings:
            Array.isArray(
                record.findings
            )
                ? record.findings
                : [],

        recommendations:
            Array.isArray(
                record.recommendations
            )
                ? record.recommendations
                : [],

        dataQuality:
            normalizeObject(
                record.dataQuality ??
                    record.data_quality ??
                    []
            ),

        includedSections:
            record.includedSections ??
            record.included_sections ??
            normalizeObject(record.snapshot ?? {}).reportOptions?.includedSections ??
            [],

        executiveKpis:
            normalizeObject(
                record.executiveKpis ??
                record.executive_kpis ??
                record.snapshot?.executive_kpis ??
                []
            ),

        performanceVariance:
            normalizeObject(
                record.performanceVariance ??
                record.performance_variance ??
                record.snapshot?.performance_variance ??
                []
            ),

        riskFlags:
            normalizeObject(
                record.riskFlags ??
                record.risk_flags ??
                record.snapshot?.risk_flags ??
                []
            ),

        generatedByUserId:
            record.generatedByUserId ??
            record.generated_by_user_id ??
            null,

        submittedAt:
            record.submittedAt ??
            record.submitted_at ??
            null,

        reviewedByUserId:
            record.reviewedByUserId ??
            record.reviewed_by_user_id ??
            null,

        reviewedByName:
            record.reviewedByName ??
            record.reviewed_by_name ??
            null,

        approvedAt:
            record.approvedAt ??
            record.approved_at ??
            null,

        revisionGroupCode:
            record.revisionGroupCode ??
            record.revision_group_code ??
            record.reportCode ??
            record.report_code ??
            "",

        revisionNumber:
            Number(
                record.revisionNumber ??
                    record.revision_number ??
                    1
            ),

        revisionOfReportId:
            record.revisionOfReportId ??
            record.revision_of_report_id ??
            null,

        isAutomatic:
            record.isAutomatic ??
            record.is_automatic ??
            false,

        frequency:
            record.frequency ??
            null,

        automationPeriodKey:
            record.automationPeriodKey ??
            record.automation_period_key ??
            null,

        pdfFilename:
            record.pdfFilename ??
            record.pdf_filename ??
            null,

        isLocked:
            record.isLocked ??
            record.is_locked ??
            false,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,

        updatedAt:
            record.updatedAt ??
            record.updated_at ??
            null,
    };
}


function normalizeAutomationSettings(
    record = {}
) {
    return {
        id:
            record.id ??
            null,

        dailyEnabled:
            record.dailyEnabled ??
            record.daily_enabled ??
            true,

        dailyTime:
            record.dailyTime ??
            record.daily_time ??
            "00:05",

        weeklyEnabled:
            record.weeklyEnabled ??
            record.weekly_enabled ??
            true,

        weeklyDay:
            record.weeklyDay ??
            record.weekly_day ??
            0,

        weeklyTime:
            record.weeklyTime ??
            record.weekly_time ??
            "00:10",

        monthlyEnabled:
            record.monthlyEnabled ??
            record.monthly_enabled ??
            true,

        monthlyDay:
            record.monthlyDay ??
            record.monthly_day ??
            1,

        monthlyTime:
            record.monthlyTime ??
            record.monthly_time ??
            "00:15",

        yearlyEnabled:
            record.yearlyEnabled ??
            record.yearly_enabled ??
            true,

        yearlyMonth:
            record.yearlyMonth ??
            record.yearly_month ??
            1,

        yearlyDay:
            record.yearlyDay ??
            record.yearly_day ??
            1,

        yearlyTime:
            record.yearlyTime ??
            record.yearly_time ??
            "00:20",

        preparedBy:
            record.preparedBy ??
            record.prepared_by ??
            "System Generated",

        autoGeneratePdf:
            record.autoGeneratePdf ??
            record.auto_generate_pdf ??
            true,

        lastSchedulerRunAt:
            record.lastSchedulerRunAt ??
            record.last_scheduler_run_at ??
            null,

        createdAt:
            record.createdAt ??
            record.created_at ??
            null,

        updatedAt:
            record.updatedAt ??
            record.updated_at ??
            null,
    };
}


function normalizeAutomationStatus(
    record = {}
) {
    return {
        frequency:
            record.frequency ??
            "",

        enabled:
            Boolean(
                record.enabled
            ),

        lastReportCode:
            record.lastReportCode ??
            record.last_report_code ??
            null,

        lastPeriodStart:
            record.lastPeriodStart ??
            record.last_period_start ??
            null,

        lastPeriodEnd:
            record.lastPeriodEnd ??
            record.last_period_end ??
            null,

        lastStatus:
            record.lastStatus ??
            record.last_status ??
            null,

        nextRunAt:
            record.nextRunAt ??
            record.next_run_at ??
            null,
    };
}


function createReportPayload(
    data = {}
) {
    return {
        title:
            data.title?.trim() ??
            "",

        category:
            data.category ??
            "Farm",

        report_type:
            data.reportType ??
            "",

        start_date:
            data.startDate,

        end_date:
            data.endDate,

        prepared_by:
            data.preparedBy?.trim() ??
            "",

        status:
            data.status ??
            "Draft",

        summary:
            data.summary?.trim() ||
            null,

        included_sections:
            Array.isArray(data.includedSections)
                ? data.includedSections
                : undefined,

        filters:
            data.filters && typeof data.filters === "object"
                ? data.filters
                : {},
    };
}


function createUpdatePayload(
    data = {}
) {
    const payload = {};

    if (
        data.title !==
        undefined
    ) {
        payload.title =
            data.title?.trim() ??
            "";
    }

    if (
        data.preparedBy !==
        undefined
    ) {
        payload.prepared_by =
            data.preparedBy?.trim() ??
            "";
    }

    if (
        data.summary !==
        undefined
    ) {
        payload.summary =
            data.summary?.trim() ||
            null;
    }

    return payload;
}


function createAutomationPayload(
    data = {}
) {
    return {
        daily_enabled:
            Boolean(
                data.dailyEnabled
            ),
        daily_time:
            data.dailyTime,

        weekly_enabled:
            Boolean(
                data.weeklyEnabled
            ),
        weekly_day:
            Number(
                data.weeklyDay
            ),
        weekly_time:
            data.weeklyTime,

        monthly_enabled:
            Boolean(
                data.monthlyEnabled
            ),
        monthly_day:
            Number(
                data.monthlyDay
            ),
        monthly_time:
            data.monthlyTime,

        yearly_enabled:
            Boolean(
                data.yearlyEnabled
            ),
        yearly_month:
            Number(
                data.yearlyMonth
            ),
        yearly_day:
            Number(
                data.yearlyDay
            ),
        yearly_time:
            data.yearlyTime,

        prepared_by:
            data.preparedBy?.trim() ||
            "System Generated",

        auto_generate_pdf:
            Boolean(
                data.autoGeneratePdf
            ),
    };
}


async function getAuthenticatedBlob(path, accept) {
    return httpClient.download(path, { accept });
}


function safeFilename(value) {
    return String(
        value || "report"
    )
        .replace(
            /[^a-z0-9_-]+/gi,
            "-"
        )
        .replace(
            /^-+|-+$/g,
            ""
        );
}


function downloadBlob(
    blob,
    filename
) {
    const objectUrl =
        URL.createObjectURL(
            blob
        );

    const link =
        document.createElement(
            "a"
        );

    link.href =
        objectUrl;

    link.download =
        filename;

    document.body.appendChild(
        link
    );

    link.click();
    link.remove();

    URL.revokeObjectURL(
        objectUrl
    );
}


export const reportService =
    Object.freeze({
        async getReports(
            includeArchived = false,
            options = {}
        ) {
            const response =
                await httpClient.get(
                    "/reports",
                    {
                        query: {
                            include_archived: includeArchived,
                            offset: options.offset ?? 0,
                            limit: options.limit ?? 100,
                            search: options.search || undefined,
                            category: options.category || undefined,
                            status: options.status || undefined,
                            start_date: options.startDate || undefined,
                            end_date: options.endDate || undefined,
                            source: options.source || undefined,
                            tab: options.tab || undefined,
                        },
                    }
                );

            const records =
                Array.isArray(
                    response
                )
                    ? response
                    : response?.data ??
                      [];

            return records.map(
                normalizeReport
            );
        },

        async getReportSummary(options = {}) {
            const response = await httpClient.get("/reports/summary", {
                query: {
                    search: options.search || undefined,
                    category: options.category || undefined,
                    status: options.status || undefined,
                    start_date: options.startDate || undefined,
                    end_date: options.endDate || undefined,
                    source: options.source || undefined,
                    tab: options.tab || undefined,
                },
            });
            return {
                matchingTotal: Number(response.matching_total || 0),
                total: Number(response.total || 0),
                approved: Number(response.approved || 0),
                forReview: Number(response.for_review || 0),
                automatic: Number(response.automatic || 0),
                custom: Number(response.custom || 0),
            };
        },


        async getReport(
            reportId
        ) {
            const response =
                await httpClient.get(
                    `/reports/${reportId}`
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async generateReport(
            data
        ) {
            const response =
                await httpClient.post(
                    "/reports",
                    createReportPayload(
                        data
                    )
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async updateReport(
            reportId,
            data
        ) {
            const response =
                await httpClient.put(
                    `/reports/${reportId}`,
                    createUpdatePayload(
                        data
                    )
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async submitReport(
            reportId
        ) {
            const response =
                await httpClient.post(
                    `/reports/${reportId}/submit`,
                    {}
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async approveReport(
            reportId
        ) {
            const response =
                await httpClient.post(
                    `/reports/${reportId}/approve`,
                    {}
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async createRevision(
            reportId
        ) {
            const response =
                await httpClient.post(
                    `/reports/${reportId}/revision`,
                    {}
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async getVersions(
            reportId
        ) {
            const response =
                await httpClient.get(
                    `/reports/${reportId}/versions`
                );

            return {
                seriesCode:
                    response?.series_code ??
                    response?.seriesCode ??
                    "",

                versions:
                    (
                        response?.versions ??
                        []
                    ).map(
                        normalizeReport
                    ),
            };
        },


        async archiveReport(
            reportId
        ) {
            const response =
                await httpClient.post(
                    `/reports/${reportId}/archive`,
                    {}
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async restoreReport(
            reportId
        ) {
            const response =
                await httpClient.post(
                    `/reports/${reportId}/restore`,
                    {}
                );

            return normalizeReport(
                response?.data ??
                response
            );
        },


        async deleteReportPermanently(reportId) {
            await httpClient.delete(
                `/reports/${reportId}/permanent`
            );

            return true;
        },


        async getAutomationSettings() {
            const response =
                await httpClient.get(
                    "/reports/automation/settings"
                );

            return normalizeAutomationSettings(
                response?.data ??
                response
            );
        },


        async updateAutomationSettings(
            data
        ) {
            const response =
                await httpClient.put(
                    "/reports/automation/settings",
                    createAutomationPayload(
                        data
                    )
                );

            return normalizeAutomationSettings(
                response?.data ??
                response
            );
        },


        async getAutomationStatus() {
            const response =
                await httpClient.get(
                    "/reports/automation/status"
                );

            return (
                response?.items ??
                []
            ).map(
                normalizeAutomationStatus
            );
        },


        async runAutomationNow() {
            const response =
                await httpClient.post(
                    "/reports/automation/run-now",
                    {}
                );

            return {
                generatedCount:
                    response?.generated_count ??
                    response?.generatedCount ??
                    0,

                generatedReports:
                    (
                        response?.generated_reports ??
                        response?.generatedReports ??
                        []
                    ).map(
                        normalizeReport
                    ),

                message:
                    response?.message ??
                    "",
            };
        },


        async previewPdf(report) {
            /*
             * Open immediately while still inside the click event.
             * Browsers may block window.open() when it happens only
             * after an awaited network request.
             */
            const previewWindow =
                window.open(
                    "",
                    "_blank"
                );

            if (!previewWindow) {
                throw new Error(
                    "The browser could not open the report preview tab."
                );
            }

            try {
                previewWindow.document.title =
                    "Loading Report PDF...";

                previewWindow.document.body.innerHTML =
                    `
                    <div style="
                        min-height:100vh;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        font-family:Arial,sans-serif;
                        background:#f8fafc;
                        color:#14532d;
                    ">
                        <div style="text-align:center;">
                            <h2 style="margin:0 0 8px;">
                                Joross Farm
                            </h2>
                            <p style="margin:0;">
                                Preparing report preview...
                            </p>
                        </div>
                    </div>
                    `;

                const blob =
                    await getAuthenticatedBlob(
                        `/reports/${report.id}/pdf?download=false`,
                        "application/pdf"
                    );

                const objectUrl =
                    URL.createObjectURL(
                        blob
                    );

                previewWindow.location.replace(
                    objectUrl
                );

                window.setTimeout(
                    () =>
                        URL.revokeObjectURL(
                            objectUrl
                        ),
                    300000
                );
            } catch (error) {
                try {
                    previewWindow.document.title =
                        "Report Preview Error";

                    previewWindow.document.body.innerHTML =
                        `
                        <div style="
                            min-height:100vh;
                            display:flex;
                            align-items:center;
                            justify-content:center;
                            font-family:Arial,sans-serif;
                            background:#f8fafc;
                            color:#991b1b;
                            padding:24px;
                        ">
                            <div style="
                                max-width:520px;
                                text-align:center;
                            ">
                                <h2 style="margin:0 0 8px;">
                                    Unable to open report
                                </h2>
                                <p style="margin:0;">
                                    ${
                                        error?.message ||
                                        "The PDF could not be loaded."
                                    }
                                </p>
                            </div>
                        </div>
                        `;
                } catch {
                    previewWindow.close();
                }

                throw error;
            }
        },


        async downloadPdf(report) {
            const blob =
                await getAuthenticatedBlob(
                    `/reports/${report.id}/pdf?download=true`,
                    "application/pdf"
                );

            downloadBlob(
                blob,
                report.pdfFilename ||
                    `${safeFilename(
                        report.reportCode
                    )}_REV-${report.revisionNumber}_${safeFilename(
                        report.title
                    )}.pdf`
            );
        },


        async downloadSupportingData(
            report
        ) {
            const blob =
                await getAuthenticatedBlob(
                    `/reports/${report.id}/data.csv`,
                    "text/csv"
                );

            downloadBlob(
                blob,
                `${safeFilename(
                    report.reportCode
                )}_REV-${report.revisionNumber}_supporting-data.csv`
            );
        },
    });
