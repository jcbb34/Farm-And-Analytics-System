from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


ALLOWED_ALERT_CATEGORIES = {
    "Crop",
    "Livestock",
    "Inventory",
    "Production & Sales",
    "Weather",
    "System",
}

ALLOWED_ALERT_PRIORITIES = {
    "Low",
    "Medium",
    "High",
    "Critical",
}

ALLOWED_ALERT_STATUSES = {
    "Active",
    "Disabled",
    "Resolved",
    "Completed",
}

ALLOWED_ALERT_CONDITIONS = {
    "Below",
    "Above",
    "Equals",
    "Within",
    "Every",
    "At least",
    "Scheduled",
}


class FarmAlertCreate(BaseModel):
    alert_name: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=40)
    subject: str = Field(min_length=1, max_length=180)
    alert_type: str = Field(min_length=1, max_length=100)
    condition: str = Field(min_length=1, max_length=30)
    threshold: str = Field(min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    priority: str = Field(default="Medium", max_length=20)
    status: str = Field(default="Active", max_length=20)
    description: str | None = None
    source_type: str | None = Field(default=None, max_length=50)
    source_id: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_values(self):
        if self.category not in ALLOWED_ALERT_CATEGORIES:
            raise ValueError("Invalid alert category.")
        if self.priority not in ALLOWED_ALERT_PRIORITIES:
            raise ValueError("Invalid alert priority.")
        if self.status not in ALLOWED_ALERT_STATUSES:
            raise ValueError("Invalid alert status.")
        if self.condition not in ALLOWED_ALERT_CONDITIONS:
            raise ValueError("Invalid alert condition.")
        return self


class FarmAlertUpdate(BaseModel):
    alert_name: str | None = Field(default=None, min_length=1, max_length=150)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    subject: str | None = Field(default=None, min_length=1, max_length=180)
    alert_type: str | None = Field(default=None, min_length=1, max_length=100)
    condition: str | None = Field(default=None, min_length=1, max_length=30)
    threshold: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, max_length=50)
    priority: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)
    description: str | None = None
    source_type: str | None = Field(default=None, max_length=50)
    source_id: int | None = Field(default=None, ge=1)


class FarmAlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_name: str
    category: str
    subject: str
    alert_type: str
    condition: str
    threshold: str
    unit: str | None = None
    priority: str
    status: str
    description: str | None = None
    last_triggered: datetime | None = None

    # These fields tell the frontend where the alert came from.
    is_automatic: bool = False
    source_type: str | None = None
    source_id: int | None = None

    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime


class CropAlertSettings(BaseModel):
    planting_reminder: bool = True
    growth_check: bool = True
    harvest_reminder: bool = True
    pest_disease_alert: bool = True
    harvest_advance_days: int = Field(default=7, ge=0, le=365)
    growth_check_frequency: int = Field(default=7, ge=1, le=365)
    soil_moisture_threshold: float = Field(default=30, ge=0, le=100)


class LivestockAlertSettings(BaseModel):
    feeding_reminder: bool = True
    vaccination_reminder: bool = True
    health_check: bool = True
    production_check: bool = False
    vaccination_advance_days: int = Field(default=7, ge=0, le=365)
    health_check_frequency: int = Field(default=14, ge=1, le=365)
    feeding_reminder_time: str = Field(
        default="06:00",
        pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
    )


class WeatherAlertSettings(BaseModel):
    heavy_rain_alert: bool = True
    high_temperature_alert: bool = True
    strong_wind_alert: bool = True
    thunderstorm_alert: bool = True
    rainfall_threshold: float = Field(default=80, ge=0)
    temperature_threshold: float = Field(default=32, ge=-100, le=100)
    wind_speed_threshold: float = Field(default=40, ge=0)


class SystemAlertSettings(BaseModel):
    backup_reminder: bool = True
    low_inventory_alert: bool = True
    low_storage_alert: bool = True
    failed_login_alert: bool = True
    backup_frequency: int = Field(default=7, ge=1, le=365)
    storage_threshold: float = Field(default=10, ge=0, le=100)
    failed_login_limit: int = Field(default=5, ge=1, le=1000)


class AlertSettingsPayload(BaseModel):
    crop: CropAlertSettings = Field(default_factory=CropAlertSettings)
    livestock: LivestockAlertSettings = Field(default_factory=LivestockAlertSettings)
    weather: WeatherAlertSettings = Field(default_factory=WeatherAlertSettings)
    system: SystemAlertSettings = Field(default_factory=SystemAlertSettings)


class AlertSettingsResponse(AlertSettingsPayload):
    id: int
    updated_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
