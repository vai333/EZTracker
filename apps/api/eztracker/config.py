from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "EZTracker"  # single rename point for the backend (frontend: src/lib/brand.ts)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    mongodb_uri: str = ""
    mongodb_db: str = "eztracker"
    auth_jwt_secret: str = ""          # signs EZTracker session tokens (make keygen-jwt)
    session_days: int = 14
    credentials_encryption_key: str = ""

    frontend_origin: str = "http://localhost:5173"
    nexus_base_url: str = "https://students.mesaschool.co.in"
    scheduler_enabled: bool = True
    log_level: str = "INFO"
    timezone: str = "Asia/Kolkata"

    sync_interval_hours: int = 3
    manual_sync_cooldown_minutes: int = 10
    stale_after_hours: int = 7
    run_budget_seconds: int = 300
    delay_ms: tuple[int, int] = Field(default=(400, 1200))
    undo_window_seconds: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
