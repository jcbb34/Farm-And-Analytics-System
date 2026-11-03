from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_server: str
    db_name: str
    db_driver: str

    db_trusted_connection: str = "yes"
    db_trust_server_certificate: str = "yes"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Lightweight database-backed login throttling. Failed attempts are scoped
    # to the same username + client IP so one remote client cannot permanently
    # lock a known farm account.
    login_rate_limit_enabled: bool = True
    login_max_failed_attempts: int = 8
    login_failure_window_minutes: int = 10

    # Optional comma-separated browser origins for deployment, for example:
    # https://farm.example.com,https://admin.example.com
    # Browsers use the same-origin frontend proxy on the local WLAN.
    # The launcher supplies its --port to the authenticated phone QR endpoint.
    farm_frontend_port: int = Field(default=3000, ge=1, le=65535)

    cors_allowed_origins: str = ""
    cors_allow_private_network_origins: bool = False

    # Background schedulers can be disabled for a dedicated API worker or
    # maintenance session. Database locks still protect duplicate work when
    # multiple workers leave these enabled.
    report_scheduler_enabled: bool = True
    farm_automation_scheduler_enabled: bool = True
    farm_automation_scheduler_interval_seconds: int = 60
    farm_automation_scheduler_startup_delay_seconds: int = 5
    farm_automation_scheduler_instance_id: str = ""

    # Single farm-local timezone used for operational calendar dates.
    farm_timezone: str = "Asia/Manila"

    # Workforce task photo evidence. Local filesystem storage is appropriate for
    # the capstone WLAN deployment; the service layer can later be replaced by
    # an object-storage adapter without changing workforce routes or DB records.
    workforce_evidence_storage_backend: str = "local"
    workforce_evidence_local_dir: str = "storage/workforce_evidence"
    workforce_evidence_max_bytes: int = 6 * 1024 * 1024
    workforce_evidence_max_total_bytes_per_submission: int = 16 * 1024 * 1024
    workforce_evidence_max_files_per_submission: int = 4
    workforce_evidence_min_dimension: int = 64
    workforce_evidence_max_dimension: int = 6000
    workforce_evidence_max_pixels: int = 20_000_000
    workforce_evidence_thumbnail_pixels: int = 480
    workforce_evidence_temporary_hours: int = 24

    # OpenWeather configuration
    openweather_api_key: str = ""
    openweather_lat: float = 13.1391
    openweather_lon: float = 123.7438
    openweather_location_name: str = "Joross Farm Area"
    openweather_timeout_seconds: float = 10.0
    openweather_cache_seconds: int = 300
    # Opt in only after configuring eligible One Call 3.0 access.
    openweather_official_alerts_enabled: bool = False

    # Initial administrator account used only by app.seed on a fresh database.
    # Keep the real password in .env, never in source control.
    seed_admin_full_name: str = "System Administrator"
    seed_admin_username: str = "admin"
    seed_admin_email: str = "admin@example.com"
    seed_admin_contact_number: str = "09123456789"
    seed_admin_position: str = "Farm Administrator"
    seed_admin_password: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
