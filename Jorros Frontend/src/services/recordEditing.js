import { ApiError } from "./httpClient.js";

export function recordEditVersion(record) {
    const version = Number(record?.editVersion ?? record?.edit_version);
    if (!Number.isSafeInteger(version) || version < 1) {
        throw new ApiError("Reload the latest record before saving edits. Its record version is missing.", { status: 428, code: "RECORD_VERSION_REQUIRED" });
    }
    return version;
}

export function isRecordEditConflict(error) {
    return ["RECORD_CONFLICT", "RECORD_VERSION_REQUIRED"].includes(error?.code);
}
