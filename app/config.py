from __future__ import annotations

from functools import lru_cache
from typing import Iterable, Optional, Union

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    windsor_api_key: Optional[str] = Field(default=None, alias="WINDSOR_API_KEY")
    windsor_base_url: str = Field(
        default="https://connectors.windsor.ai",
        alias="WINDSOR_BASE_URL",
    )
    database_url: str = Field(default="sqlite:///./kfc_app_installs.db", alias="DATABASE_URL")
    allowed_origins: str = Field(
        default="https://grupo-mkp.com,http://localhost:5173",
        alias="ALLOWED_ORIGINS",
    )
    public_base_url: str = Field(default="https://grupo-mkp.com/one", alias="PUBLIC_BASE_URL")
    refresh_cron: str = Field(default="*/30 * * * *", alias="REFRESH_CRON")
    cache_ttl_seconds: int = Field(default=900, alias="CACHE_TTL_SECONDS")

    azure_ad_tenant_id: Optional[str] = Field(default=None, alias="AZURE_AD_TENANT_ID")
    azure_ad_client_id: Optional[str] = Field(default=None, alias="AZURE_AD_CLIENT_ID")
    azure_ad_issuer: Optional[str] = Field(default=None, alias="AZURE_AD_ISSUER")
    allowed_roles: str = Field(default="Planners,admin", alias="ALLOWED_ROLES")
    auth_disabled: bool = Field(default=False, alias="AUTH_DISABLED")
    auth_disabled_token: str = Field(default="local-dev-admin", alias="AUTH_DISABLED_TOKEN")
    auth_jwks_timeout_seconds: float = Field(default=5.0, alias="AUTH_JWKS_TIMEOUT_SECONDS")

    # Reporte KFC · Autorápido y Helados: rol propio (NO Planners/admin como el resto de dashboards KFC).
    kfc_reporte_roles: str = Field(default="kfchiden", alias="KFC_REPORTE_ROLES")

    app_timezone: str = Field(default="America/Guayaquil", alias="APP_TIMEZONE")
    create_db_on_startup: bool = Field(default=True, alias="CREATE_DB_ON_STARTUP")
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    http_timeout_seconds: float = Field(default=60.0, alias="HTTP_TIMEOUT_SECONDS")
    http_retries: int = Field(default=3, alias="HTTP_RETRIES")
    public_rate_limit_requests: int = Field(default=60, alias="PUBLIC_RATE_LIMIT_REQUESTS")
    public_rate_limit_window_seconds: int = Field(
        default=60,
        alias="PUBLIC_RATE_LIMIT_WINDOW_SECONDS",
    )

    @property
    def allowed_origin_list(self) -> list[str]:
        return _csv(self.allowed_origins)

    @property
    def allowed_role_set(self) -> set[str]:
        return {role.lower() for role in _csv(self.allowed_roles)}

    @property
    def kfc_reporte_role_set(self) -> set[str]:
        return {role.lower() for role in _csv(self.kfc_reporte_roles)}

    @property
    def azure_client_ids(self) -> list[str]:
        return _csv(self.azure_ad_client_id or "")

    @property
    def azure_issuer(self) -> Optional[str]:
        if self.azure_ad_issuer:
            return self.azure_ad_issuer.rstrip("/")
        if self.azure_ad_tenant_id:
            return f"https://login.microsoftonline.com/{self.azure_ad_tenant_id}/v2.0"
        return None

    @property
    def azure_jwks_url(self) -> Optional[str]:
        if not self.azure_ad_tenant_id:
            return None
        return (
            f"https://login.microsoftonline.com/{self.azure_ad_tenant_id}"
            "/discovery/v2.0/keys"
        )


def _csv(value: Union[str, Iterable[str]]) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
