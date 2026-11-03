import { httpClient } from "./httpClient.js";


const IMPORT_PREVIEW_TIMEOUT_MS = 120000;
const IMPORT_COMMIT_TIMEOUT_MS = 300000;


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
        typeof value === "object"
    ) {
        return Object.fromEntries(
            Object.entries(value).map(
                ([key, itemValue]) => [
                    camelizeKey(key),
                    normalizeObject(
                        itemValue
                    ),
                ]
            )
        );
    }

    return value;
}


async function requestJson(path, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const requestOptions = {};

    if (Number.isFinite(options.timeoutMs)) {
        requestOptions.timeoutMs = options.timeoutMs;
    }
    if (options.signal) {
        requestOptions.signal = options.signal;
    }

    let result;

    if (options.body instanceof FormData) {
        result = await httpClient.upload(
            path,
            options.body,
            { ...requestOptions, method }
        );
    } else {
        const body = options.body === undefined
            ? undefined
            : JSON.parse(options.body);

        if (method === "POST") {
            result = await httpClient.post(path, body, requestOptions);
        } else if (method === "PUT") {
            result = await httpClient.put(path, body, requestOptions);
        } else if (method === "PATCH") {
            result = await httpClient.patch(path, body, requestOptions);
        } else if (method === "DELETE") {
            result = await httpClient.delete(path, requestOptions);
        } else {
            result = await httpClient.get(path, requestOptions);
        }
    }

    return normalizeObject(result);
}


function downloadBlob(
    blob,
    filename
) {
    const url =
        URL.createObjectURL(blob);

    const link =
        document.createElement(
            "a"
        );

    link.href = url;
    link.download = filename;

    document.body.appendChild(
        link
    );
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
}


export const importService =
    Object.freeze({
        async previewFile(
            file,
            force = false
        ) {
            const formData =
                new FormData();

            formData.append(
                "file",
                file
            );

            formData.append(
                "force",
                String(force)
            );

            return requestJson(
                "/imports/preview",
                {
                    method: "POST",
                    body: formData,
                    timeoutMs: IMPORT_PREVIEW_TIMEOUT_MS,
                }
            );
        },


        async reviewBatch(
            batchId,
            sheets
        ) {
            return requestJson(
                `/imports/${batchId}/review`,
                {
                    method: "POST",
                    timeoutMs: IMPORT_PREVIEW_TIMEOUT_MS,
                    body: JSON.stringify({
                        sheets:
                            sheets.map(
                                (sheet) => ({
                                    sheet_name:
                                        sheet.sheetName,
                                    target_type:
                                        sheet.targetType,
                                    include:
                                        sheet.included !==
                                        false,
                                    column_mapping:
                                        sheet.columnMapping ||
                                        {},
                                })
                            ),
                    }),
                }
            );
        },


        async commitBatch(
            batchId,
            rowActions = {},
            forceExactDuplicate =
                false
        ) {
            return requestJson(
                `/imports/${batchId}/commit`,
                {
                    method: "POST",
                    body: JSON.stringify({
                        row_actions:
                            Object.fromEntries(
                                Object.entries(
                                    rowActions
                                ).map(
                                    ([
                                        key,
                                        value,
                                    ]) => [
                                        Number(
                                            key
                                        ),
                                        value,
                                    ]
                                )
                            ),
                        force_exact_duplicate:
                            forceExactDuplicate,
                    }),
                    timeoutMs: IMPORT_COMMIT_TIMEOUT_MS,
                }
            );
        },


        async getHistory(
            limit = 50
        ) {
            return requestJson(
                `/imports/history?limit=${encodeURIComponent(
                    limit
                )}`,
                {
                    method: "GET",
                }
            );
        },


        async getBatch(
            batchId
        ) {
            return requestJson(
                `/imports/${batchId}`,
                {
                    method: "GET",
                }
            );
        },


        async rollbackBatch(
            batchId,
            force = false
        ) {
            return requestJson(
                `/imports/${batchId}/rollback`,
                {
                    method: "POST",
                    body: JSON.stringify({
                        force,
                    }),
                }
            );
        },


        async downloadErrors(
            batch
        ) {
            const blob =
                await httpClient.download(
                    `/imports/${batch.id}/errors.csv`,
                    { accept: "text/csv" }
                );

            downloadBlob(
                blob,
                `${batch.batchCode}_import-errors.csv`
            );
        },
    });
