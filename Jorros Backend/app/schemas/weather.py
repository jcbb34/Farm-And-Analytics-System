from datetime import date, datetime

from pydantic import BaseModel, Field


class CurrentWeatherResponse(BaseModel):
    observed_at: datetime
    temperature_c: float
    feels_like_c: float
    humidity_percent: int
    condition: str
    description: str
    weather_code: int
    icon: str | None = None
    wind_speed_kph: float
    wind_gust_kph: float | None = None
    wind_direction_deg: int | None = None
    clouds_percent: int
    rain_1h_mm: float = 0


class WeatherForecastPointResponse(BaseModel):
    forecast_at: datetime
    temperature_c: float
    feels_like_c: float
    humidity_percent: int
    condition: str
    description: str
    weather_code: int
    icon: str | None = None
    wind_speed_kph: float
    wind_gust_kph: float | None = None
    wind_direction_deg: int | None = None
    rain_probability_percent: float = Field(ge=0, le=100)
    rain_3h_mm: float = 0


class Next24HoursWeatherResponse(BaseModel):
    max_temperature_c: float
    min_temperature_c: float
    max_wind_speed_kph: float
    max_wind_gust_kph: float | None = None
    rain_total_mm: float
    max_rain_probability_percent: float = Field(ge=0, le=100)
    thunderstorm_expected: bool


class WeatherOverviewResponse(BaseModel):
    source: str = "OpenWeather"
    fetched_at: datetime | None = None
    data_status: str = "Unknown"
    observation_age_seconds: int | None = None
    last_fetch_error: str | None = None
    official_alerts_status: str = "Not configured"
    official_alerts: list[dict] = Field(default_factory=list)
    location: str
    latitude: float
    longitude: float
    timezone_offset_seconds: int
    current: CurrentWeatherResponse
    next_24_hours: Next24HoursWeatherResponse
    forecast: list[WeatherForecastPointResponse]


class WeatherHistoryResponse(BaseModel):
    id: int
    recorded_date: date
    observed_at: datetime
    location: str
    temperature_c: float
    humidity_percent: int
    rainfall_mm: float
    wind_speed_kph: float
    condition: str
    weather_code: int
    source: str

    model_config = {"from_attributes": True}
