"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Finance Operations"
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

    # Google integrations (Drive — TT-copy uploads)
    google_service_account_json: str = ""
    google_drive_folder_id: str = ""

    # Web Push (VAPID) — empty → push disabled, in-app bell still works
    vapid_private_key: str = ""
    vapid_public_key: str = ""
    vapid_claims_email: str = ""

    # SMTP (HoM / super-admin emails) — empty host → emails disabled
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # Analytics defaults (overridden by system_config table at runtime)
    default_etd_grace_days: int = 10
    default_cost_of_fund_rate: float = 0.12
    default_cost_of_fund_grace_days: int = 30

    # Rate limiting (slowapi "N/period" strings)
    rate_limit_public_default: str = "20/minute"
    rate_limit_public_submit: str = "5/minute"
    rate_limit_ai_query: str = "15/minute"
    rate_limit_auth_default: str = "60/minute"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, value: str | list) -> list[str]:
        if isinstance(value, str):
            import json
            return json.loads(value)
        return value

    @model_validator(mode="after")
    def warn_if_default_cors(self) -> "Settings":
        if self.cors_origins == ["http://localhost:3000"]:
            import logging
            logging.getLogger("app").warning(
                "CORS_ORIGINS is using the localhost default — cross-origin POST requests "
                "will be rejected in production. Set CORS_ORIGINS in Railway to include "
                "the production frontend URL."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
