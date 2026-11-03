import { httpClient } from "./httpClient.js";


function normalizeBackup(record = {}) {
    return {
        id: record.id,
        recoveryAvailable: Boolean(record.recovery_available ?? record.recoveryAvailable),
        recoverySizeBytes: Number(record.recovery_file_size_bytes ?? record.recoverySizeBytes ?? 0),
        backupCode:
            record.backupCode ??
            record.backup_code ??
            "",
        filename:
            record.filename ??
            "",
        formatVersion:
            record.formatVersion ??
            record.format_version ??
            "1.0",
        status:
            record.status ??
            "Unknown",
        fileSizeBytes:
            Number(
                record.fileSizeBytes ??
                    record.file_size_bytes ??
                    0
            ),
        tableCount:
            Number(
                record.tableCount ??
                    record.table_count ??
                    0
            ),
        rowCount:
            Number(
                record.rowCount ??
                    record.row_count ??
                    0
            ),
        checksumSha256:
            record.checksumSha256 ??
            record.checksum_sha256 ??
            null,
        notes:
            record.notes ??
            "",
        createdByUserId:
            record.createdByUserId ??
            record.created_by_user_id ??
            null,
        createdAt:
            record.createdAt ??
            record.created_at ??
            null,
        completedAt:
            record.completedAt ??
            record.completed_at ??
            null,
    };
}


function normalizeImportBatch(record = {}) {
    return {
        id: record.id,
        fileName:
            record.fileName ??
            record.file_name ??
            record.filename ??
            record.original_filename ??
            record.source_filename ??
            "",
        module:
            record.module ??
            record.moduleName ??
            record.module_name ??
            record.importType ??
            record.import_type ??
            record.targetModule ??
            record.target_module ??
            record.entityType ??
            record.entity_type ??
            "General",
        status:
            record.status ??
            record.importStatus ??
            record.import_status ??
            "Unknown",
        totalRows: Number(
            record.totalRows ??
                record.total_rows ??
                record.rowCount ??
                record.row_count ??
                0
        ),
        successRows: Number(
            record.successRows ??
                record.success_rows ??
                record.successfulRows ??
                record.successful_rows ??
                record.importedRows ??
                record.imported_rows ??
                record.committedRows ??
                record.committed_rows ??
                0
        ),
        skippedRows: Number(
            record.skippedRows ??
                record.skipped_rows ??
                record.duplicateRows ??
                record.duplicate_rows ??
                0
        ),
        failedRows: Number(
            record.failedRows ??
                record.failed_rows ??
                record.invalidRows ??
                record.invalid_rows ??
                record.errorRows ??
                record.error_rows ??
                0
        ),
        checksum:
            record.checksum ??
            record.checksum_sha256 ??
            record.file_hash ??
            record.content_hash ??
            null,
        createdByUserId:
            record.createdByUserId ??
            record.created_by_user_id ??
            record.imported_by_user_id ??
            null,
        createdAt:
            record.createdAt ??
            record.created_at ??
            record.uploaded_at ??
            record.imported_at ??
            record.started_at ??
            null,
        completedAt:
            record.completedAt ??
            record.completed_at ??
            record.committed_at ??
            record.finished_at ??
            record.updated_at ??
            null,
    };
}


function normalizeImportRow(record = {}, index = 0) {
    return {
        id: record.id ?? null,
        rowNumber:
            record.rowNumber ??
            record.row_number ??
            record.source_row_number ??
            record.excel_row ??
            record.row_index ??
            index + 1,
        status:
            record.status ??
            record.row_status ??
            record.result ??
            record.action ??
            "Unknown",
        targetType:
            record.targetType ??
            record.target_type ??
            record.module ??
            record.entity_type ??
            "",
        recordName:
            record.recordName ??
            record.record_name ??
            record.entity_name ??
            record.target_name ??
            record.item_name ??
            record.crop_name ??
            "",
        message:
            record.message ??
            record.error_message ??
            record.validation_message ??
            record.reason ??
            record.notes ??
            "",
    };
}


export const backupService = Object.freeze({
    async getBackups(limit = 50) {
        const response =
            await httpClient.get(
                "/backups",
                {
                    query: {
                        limit,
                    },
                }
            );

        const records =
            Array.isArray(response)
                ? response
                : response?.data ?? [];

        return records.map(
            normalizeBackup
        );
    },


    async createBackup() {
        const response =
            await httpClient.post(
                "/backups",
                {},
                { timeoutMs: 120000 }
            );

        return normalizeBackup(
            response?.data ??
            response
        );
    },


    getRecoveryPackage(backupId) {
        return httpClient.download(`/backups/${backupId}/recovery-package`, { timeoutMs: 120000 });
    },

    async getBackupContent(
        backupId
    ) {
        return httpClient.get(
            `/backups/${backupId}/content`
        );
    },


    async getImportHistory(limit = 50) {
        const response =
            await httpClient.get(
                "/backups/import-history",
                {
                    query: {
                        limit,
                    },
                }
            );

        const records =
            Array.isArray(response)
                ? response
                : response?.data ?? [];

        return records.map(
            normalizeImportBatch
        );
    },


    async getImportHistoryDetails(
        batchId,
        { resultFilter = "all", limit = 1000, offset = 0 } = {}
    ) {
        const response =
            await httpClient.get(
                `/backups/import-history/${batchId}`,
                {
                    query: {
                        result_filter: resultFilter,
                        limit,
                        offset,
                    },
                }
            );

        const payload =
            response?.data ?? response ?? {};

        return {
            batch: normalizeImportBatch(
                payload.batch ?? {}
            ),
            rows: Array.isArray(payload.rows)
                ? payload.rows.map(
                      normalizeImportRow
                  )
                : [],
            rowCount: Number(
                payload.rowCount ??
                    payload.row_count ??
                    payload.rows?.length ??
                    0
            ),
            filteredRowCount: Number(
                payload.filteredRowCount ??
                    payload.filtered_row_count ??
                    payload.rowCount ??
                    payload.row_count ??
                    payload.rows?.length ??
                    0
            ),
            resultFilter:
                payload.resultFilter ??
                payload.result_filter ??
                resultFilter,
            rowsTruncated: Boolean(
                payload.rowsTruncated ??
                    payload.rows_truncated ??
                    false
            ),
            limit: Number(payload.limit ?? limit),
            offset: Number(payload.offset ?? offset),
        };
    },
});
