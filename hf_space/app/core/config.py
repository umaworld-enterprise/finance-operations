"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Advance Deposit Tracker"
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = False
    secret_key: str

    # Supabase
    supabase_url: AnyHttpUrl
    supabase_anon_key: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # Database
    database_url: str

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]

    # Analytics defaults (overridden by system_config table at runtime)
    default_etd_grace_days: int = 10
    default_cost_of_fund_rate: float = 0.18
    default_cost_of_fund_grace_days: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value: str | list) -> list[str]:
        if isinstance(value, str):
            import json
            return json.loads(value)
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
