export const SUFFIXES = ["Jr.", "Sr.", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"];
export function emptyPersonalDetails() { return { first_name: "", middle_name: "", surname: "", suffix: "", address: null }; }
export function composeFullName(details, fallback = "") {
    return details?.first_name?.trim() && details?.surname?.trim()
        ? [details.first_name, details.middle_name, details.surname, details.suffix].filter(Boolean).map((part) => part.trim()).join(" ") : fallback;
}
export function validatePersonalDetails(details, isNew = false) {
    if ((isNew || [details?.first_name, details?.middle_name, details?.surname, details?.suffix].some((value) => value?.trim())) && (!details?.first_name?.trim() || !details?.surname?.trim())) return "Enter the first name and surname.";
    if (composeFullName(details).length > 120) return "The complete name must be at most 120 characters.";
    const address = details?.address;
    if (address && Object.values(address).some((value) => value?.trim())) {
        if (![address.province, address.city, address.barangay].every((value) => value?.trim())) return "Complete province, city/municipality and barangay, or enter custom locations.";
        if (address.postal_code && !/^\d{4}$/.test(address.postal_code)) return "Enter a four-digit Philippine postal/ZIP code.";
        if ([address.street, address.subdivision, address.barangay, address.city, address.province, address.postal_code].filter(Boolean).join(", ").length > 255) return "The complete address must be at most 255 characters.";
    }
    return "";
}
export function personalDetailsPayload(details) {
    if (!details) return null;
    const clean = (value) => typeof value === "string" ? value.trim().replace(/\s+/g, " ") || null : value;
    return { first_name: clean(details.first_name), middle_name: clean(details.middle_name), surname: clean(details.surname), suffix: clean(details.suffix), address: details.address && Object.values(details.address).some(Boolean) ? Object.fromEntries(Object.entries(details.address).map(([key, value]) => [key, clean(value)])) : null };
}
