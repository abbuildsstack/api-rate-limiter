"""Validated application configuration."""
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings are loaded from environment variables and an optional .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "API Rate Limiter"
    environment: Literal["development", "test", "production"] = "development"
    redis_url: str = "redis://localhost:6379/0"
    limiter_strategy: Literal["fixed_window", "sliding_window_log", "token_bucket"] = "fixed_window"
    rate_limit: int = Field(default=10, ge=1, le=1_000_000)
    window_seconds: int = Field(default=60, ge=1, le=86_400)
    token_bucket_capacity: int = Field(default=10, ge=1, le=1_000_000)
    token_bucket_refill_rate: float = Field(default=1.0, gt=0, le=100_000)
    fail_mode: Literal["open", "closed"] = "closed"
    admin_token: SecretStr = SecretStr("")
    trusted_proxy_headers: bool = False
    allowed_origins: str = "http://localhost:8000,http://127.0.0.1:8000"
    key_prefix: str = "rl:v1"

    @field_validator("key_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:_-" for ch in value):
            raise ValueError("key_prefix may contain only letters, numbers, colon, underscore, and hyphen")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()