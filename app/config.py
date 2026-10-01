from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded exclusively from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Lakshiya Dhotis Ads Agent"
    environment: str = "development"
    log_level: str = "INFO"
    api_admin_key: str | None = None
    database_url: str = "sqlite+pysqlite:///:memory:"
    daily_budget_inr: int = Field(default=150, ge=1)
    weekly_budget_inr: int = Field(default=1050, ge=1)
    weekly_budget_safety_percent: int = Field(default=100, ge=1, le=100)
    timezone: str = "Asia/Kolkata"
    meta_access_token: str | None = None
    meta_api_version: str = Field(default="v22.0", pattern=r"^v\d+\.0$")
    meta_live_writes_enabled: bool = False
    meta_paused_preparation_enabled: bool = False
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = Field(default=60, ge=30, le=300)
    facebook_page_id: str | None = None
    instagram_actor_id: str | None = None
    customer_whatsapp_number: str | None = None
    meta_ad_account_id: str | None = None
    meta_app_secret: str | None = None
    meta_app_id: str | None = None
    meta_business_manager_id: str | None = None
    facebook_page_url: str | None = None
    commerce_business_id: str | None = None
    meta_catalog_id: str | None = None
    storefront_url: str | None = None
    whatsapp_access_token: str | None = None
    whatsapp_notifications_enabled: bool = False
    whatsapp_approval_template: str | None = None
    whatsapp_template_language: str = "en_US"
    public_dashboard_url: str | None = None
    whatsapp_phone_number_id: str | None = None
    whatsapp_business_account_id: str | None = None
    whatsapp_verify_token: str | None = None
    whatsapp_app_secret: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = Field(default=None, repr=False)
    owner_email: str | None = None
    owner_whatsapp_number: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
