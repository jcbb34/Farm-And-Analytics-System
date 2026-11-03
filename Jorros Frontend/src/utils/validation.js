export const patterns = Object.freeze({
    contactNumber: /^09\d{9}$/,
    username: /^[A-Za-z0-9._-]{4,}$/,
    email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
});

export function required(value, label = "This field") {
    return String(value ?? "").trim()
        ? ""
        : `${label} is required.`;
}

export function validEmail(value) {
    return patterns.email.test(String(value || "").trim())
        ? ""
        : "Enter a valid email address.";
}

export function validGmail(value) {
    const normalized = String(value || "")
        .trim()
        .toLowerCase();

    return normalized.endsWith("@gmail.com") &&
        patterns.email.test(normalized)
        ? ""
        : "Enter a valid Gmail address.";
}

export function validContactNumber(value) {
    return patterns.contactNumber.test(
        String(value || "").trim()
    )
        ? ""
        : "Contact number must contain 11 digits and begin with 09.";
}

export function validUsername(value) {
    return patterns.username.test(
        String(value || "").trim()
    )
        ? ""
        : "Username must contain at least four letters, numbers, dots, underscores, or hyphens.";
}

export function positiveNumber(
    value,
    label = "Value",
    { allowZero = false } = {}
) {
    const number = Number(value);

    if (!Number.isFinite(number)) {
        return `${label} must be a valid number.`;
    }

    if (allowZero ? number < 0 : number <= 0) {
        return allowZero
            ? `${label} cannot be negative.`
            : `${label} must be greater than zero.`;
    }

    return "";
}

export function percentage(value, label = "Percentage") {
    const number = Number(value);

    return Number.isFinite(number) &&
        number >= 0 &&
        number <= 100
        ? ""
        : `${label} must be between 0 and 100.`;
}

export function dateRange(startDate, endDate) {
    if (!startDate || !endDate) {
        return "Start date and end date are required.";
    }

    return endDate >= startDate
        ? ""
        : "End date cannot be earlier than the start date.";
}

export function minimumPasswordLength(
    value,
    minimumLength = 8
) {
    return String(value || "").length >= minimumLength
        ? ""
        : `Password must contain at least ${minimumLength} characters.`;
}

export function uniqueValue(
    value,
    records,
    field,
    currentId = null,
    label = "Value"
) {
    const normalized = String(value || "")
        .trim()
        .toLowerCase();

    const duplicate = records.some(
        (record) =>
            record.id !== currentId &&
            String(record[field] || "")
                .trim()
                .toLowerCase() === normalized
    );

    return duplicate
        ? `${label} is already in use.`
        : "";
}

export function firstValidationError(validations) {
    return validations.find(Boolean) || "";
}
