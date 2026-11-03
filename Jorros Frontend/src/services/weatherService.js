import { httpClient } from "./httpClient.js";

function weatherNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}
function normalizeCurrent(record = {}) {
    return {
        windGustKph: weatherNumber(record.windGustKph ?? record.wind_gust_kph),
        observedAt:
            record.observedAt ??
            record.observed_at ??
            null,

        temperatureC: weatherNumber(
            record.temperatureC ??
                record.temperature_c ??
                null
        ),

        feelsLikeC: weatherNumber(
            record.feelsLikeC ??
                record.feels_like_c ??
                null
        ),

        humidityPercent: weatherNumber(
            record.humidityPercent ??
                record.humidity_percent ??
                null
        ),

        condition:
            record.condition ??
            "Unknown",

        description:
            record.description ??
            "Unknown",

        weatherCode: weatherNumber(
            record.weatherCode ??
                record.weather_code ??
                null
        ),

        icon:
            record.icon ??
            null,

        windSpeedKph: weatherNumber(
            record.windSpeedKph ??
                record.wind_speed_kph ??
                null
        ),

        windDirectionDeg:
            record.windDirectionDeg ??
            record.wind_direction_deg ??
            null,

        cloudsPercent: weatherNumber(
            record.cloudsPercent ??
                record.clouds_percent ??
                null
        ),

        rain1hMm: weatherNumber(
            record.rain1hMm ??
                record.rain_1h_mm ??
                null
        ),
    };
}

function normalizeForecastPoint(record = {}) {
    return {
        windGustKph: weatherNumber(record.windGustKph ?? record.wind_gust_kph),
        forecastAt:
            record.forecastAt ??
            record.forecast_at ??
            null,

        temperatureC: weatherNumber(
            record.temperatureC ??
                record.temperature_c ??
                null
        ),

        feelsLikeC: weatherNumber(
            record.feelsLikeC ??
                record.feels_like_c ??
                null
        ),

        humidityPercent: weatherNumber(
            record.humidityPercent ??
                record.humidity_percent ??
                null
        ),

        condition:
            record.condition ??
            "Unknown",

        description:
            record.description ??
            "Unknown",

        weatherCode: weatherNumber(
            record.weatherCode ??
                record.weather_code ??
                null
        ),

        icon:
            record.icon ??
            null,

        windSpeedKph: weatherNumber(
            record.windSpeedKph ??
                record.wind_speed_kph ??
                null
        ),

        windDirectionDeg:
            record.windDirectionDeg ??
            record.wind_direction_deg ??
            null,

        rainProbabilityPercent: weatherNumber(
            record.rainProbabilityPercent ??
                record.rain_probability_percent ??
                null
        ),

        rain3hMm: weatherNumber(
            record.rain3hMm ??
                record.rain_3h_mm ??
                null
        ),
    };
}

function normalizeNext24Hours(record = {}) {
    return {
        maxWindGustKph: weatherNumber(record.maxWindGustKph ?? record.max_wind_gust_kph),
        maxTemperatureC: weatherNumber(
            record.maxTemperatureC ??
                record.max_temperature_c ??
                null
        ),

        minTemperatureC: weatherNumber(
            record.minTemperatureC ??
                record.min_temperature_c ??
                null
        ),

        maxWindSpeedKph: weatherNumber(
            record.maxWindSpeedKph ??
                record.max_wind_speed_kph ??
                null
        ),

        rainTotalMm: weatherNumber(
            record.rainTotalMm ??
                record.rain_total_mm ??
                null
        ),

        maxRainProbabilityPercent: weatherNumber(
            record.maxRainProbabilityPercent ??
                record.max_rain_probability_percent ??
                null
        ),

        thunderstormExpected: Boolean(
            record.thunderstormExpected ??
                record.thunderstorm_expected ??
                false
        ),
    };
}

function normalizeWeatherHistory(record = {}) {
    return {
        id: record.id,
        recordedDate:
            record.recordedDate ??
            record.recorded_date ??
            "",
        observedAt:
            record.observedAt ??
            record.observed_at ??
            null,
        location:
            record.location ??
            "Joross Farm Area",
        temperatureC: weatherNumber(
            record.temperatureC ??
                record.temperature_c ??
                null
        ),
        humidityPercent: weatherNumber(
            record.humidityPercent ??
                record.humidity_percent ??
                null
        ),
        rainfallMm: weatherNumber(
            record.rainfallMm ??
                record.rainfall_mm ??
                null
        ),
        windSpeedKph: weatherNumber(
            record.windSpeedKph ??
                record.wind_speed_kph ??
                null
        ),
        condition:
            record.condition ??
            "Unknown",
        weatherCode: weatherNumber(
            record.weatherCode ??
                record.weather_code ??
                null
        ),
        source:
            record.source ??
            "OpenWeather",
    };
}

function normalizeWeather(response = {}) {
    return {
        source: response.source || "OpenWeather",
        fetchedAt: response.fetchedAt ?? response.fetched_at ?? null,
        dataStatus: response.dataStatus ?? response.data_status ?? "Unknown",
        observationAgeSeconds: response.observationAgeSeconds ?? response.observation_age_seconds ?? null,
        lastFetchError: response.lastFetchError ?? response.last_fetch_error ?? null,
        officialAlertsStatus: response.officialAlertsStatus ?? response.official_alerts_status ?? "Not configured",
        officialAlerts: response.officialAlerts ?? response.official_alerts ?? [],
        location:
            response.location ??
            "Joross Farm Area",

        latitude: weatherNumber(
            response.latitude ??
                null
        ),

        longitude: weatherNumber(
            response.longitude ??
                null
        ),

        timezoneOffsetSeconds: weatherNumber(
            response.timezoneOffsetSeconds ??
                response.timezone_offset_seconds ??
                null
        ),

        current: normalizeCurrent(
            response.current
        ),

        next24Hours:
            normalizeNext24Hours(
                response.next24Hours ??
                    response.next_24_hours
            ),

        forecast: (
            response.forecast ??
            []
        ).map(
            normalizeForecastPoint
        ),
    };
}

export const weatherService =
    Object.freeze({
        async getWeather() {
            const response =
                await httpClient.get(
                    "/weather"
                );

            return normalizeWeather(
                response?.data ??
                    response
            );
        },

        async getHistory(days = 90) {
            const response =
                await httpClient.get(
                    "/weather/history",
                    { query: { days } }
                );

            const records =
                Array.isArray(response)
                    ? response
                    : response?.data ?? [];

            return records.map(
                normalizeWeatherHistory
            );
        },
    });
