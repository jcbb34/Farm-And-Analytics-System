// Shared by the dashboard count, farm tip and review banner.
const threshold = (value, fallback) => value !== null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : fallback;
export function weatherSignals(weather, settings = {}) {
    if (!weather || ["Stale", "Unknown", "Unavailable"].includes(weather.dataStatus)) return [];
    const next = weather.next24Hours || {};
    const current = weather.current || {};
    const wind = Math.max(Number(next.maxWindSpeedKph) || 0, Number(next.maxWindGustKph) || 0, Number(current.windSpeedKph) || 0, Number(current.windGustKph) || 0);
    const heat = Math.max(Number(next.maxTemperatureC) || 0, Number(current.temperatureC) || 0);
    return [
        (settings.thunderstormAlert ?? true) && next.thunderstormExpected && "Thunderstorm conditions",
        (settings.heavyRainAlert ?? true) && next.rainTotalMm != null && next.rainTotalMm >= threshold(settings.rainfallThreshold, 80) && "Heavy rainfall",
        (settings.highTemperatureAlert ?? true) && heat >= threshold(settings.temperatureThreshold, 32) && "High temperature",
        (settings.strongWindAlert ?? true) && wind >= threshold(settings.windSpeedThreshold, 40) && "Strong wind or gusts",
    ].filter(Boolean);
}
export function weatherFarmTip(weather, settings = {}) {
    if (!weather || ["Stale", "Unknown", "Unavailable"].includes(weather.dataStatus)) return "Current weather could not be verified. Check official advisories and the farm's approved plan before deciding on work.";
    const signals = weatherSignals(weather, settings);
    if (signals.length) return `${signals.join("; ")} meet the configured alert thresholds. Review official advisories and affected farm work. Owner/Admin decides any suspension.`;
    if ((weather.officialAlerts || []).length) return "An official warning was returned for the configured coordinates. Read its source, validity and instructions before reviewing work.";
    if (!weather.forecast?.length) return "Forecast data is unavailable. Future conditions are unknown; check the official source.";
    return "No configured weather threshold is currently exceeded. Continue monitoring official advisories and farm conditions.";
}
