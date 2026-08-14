from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["local", "test", "development", "staging", "production"]


class Settings(BaseSettings):
    """Environment-driven application settings. Secrets must come from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "patient-health-platform"
    app_env: AppEnv = "local"
    app_debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    openapi_enabled: bool = True

    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5432/php_dev")
    )
    database_migration_url: SecretStr | None = None
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30

    redis_url: SecretStr = Field(default=SecretStr("redis://localhost:6379/0"))

    object_storage_endpoint: str = "http://localhost:9101"
    object_storage_bucket: str = "php-dev-private"
    object_storage_access_key: SecretStr = Field(default=SecretStr("minio_dev_access"))
    object_storage_secret_key: SecretStr = Field(default=SecretStr("minio_dev_secret"))
    object_storage_region: str = "us-east-1"
    object_storage_use_ssl: bool = False
    object_storage_max_bytes: int = 10 * 1024 * 1024

    auth_issuer: str = "http://localhost:8080/realms/php-dev"
    auth_audience: str = "php-api"
    auth_jwks_url: str = ""
    auth_dev_hs256_secret: SecretStr | None = None

    cors_allowed_origins: str = "http://localhost:3000"
    max_request_bytes: int = 1_048_576
    rate_limit_per_minute: int = 120

    @field_validator("app_env")
    @classmethod
    def normalize_env(cls, value: str) -> str:
        return value.lower()

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_allowed_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def allow_dev_hs256(self) -> bool:
        return self.app_env in {"local", "test", "development"}

    @property
    def expose_openapi(self) -> bool:
        if self.is_production:
            return self.openapi_enabled and self.app_debug
        return self.openapi_enabled


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
