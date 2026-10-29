"""Database settings; read the existing root .env and optional backend overrides."""

import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    demo_session_secret: SecretStr = Field(
        default_factory=lambda: SecretStr(secrets.token_urlsafe(32))
    )
    enable_demo_workspace: bool = True
    ops_admin_email: str | None = None
    ops_admin_password: SecretStr | None = None
    ops_cookie_secure: bool = False
    ops_session_seconds: int = Field(default=28800, ge=60, le=86400)
    ops_login_attempts: int = Field(default=5, ge=1, le=20)
    ops_login_window_seconds: int = Field(default=900, ge=60, le=3600)
    groq_api_key: SecretStr | None = None
    llm_provider: Literal["groq", "amazon"] = "groq"
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.amazon.nova-pro-v1:0"
    bedrock_timeout_seconds: float = Field(default=10, ge=0.1, le=20)
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: float = Field(default=3, ge=0.1, le=15)
    agent_foreground_seconds: float = Field(default=7, ge=0.1, le=7)
    agent_job_seconds: float = Field(default=24, ge=1, le=25)
    agent_max_attempts: int = Field(default=3, ge=1, le=5)
    payswift_base_url: str = "http://localhost:8081"
    payment_poll_seconds: float = Field(default=2, ge=0.1, le=60)
    payment_max_attempts: int = Field(default=8, ge=1, le=20)
    app_env: str = "development"
    app_reference_time: AwareDatetime | None = None
    enable_local_internal_reads: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_url: SecretStr | None = None
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "quickdrop"
    postgres_user: str = "quickdrop"
    postgres_password: SecretStr | None = None
    db_pool_size: int = Field(default=5, ge=1, le=30)
    db_max_overflow: int = Field(default=5, ge=0, le=30)

    @field_validator("app_reference_time", mode="before")
    @classmethod
    def optional_reference_time(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def local_reference_clock(self):
        if self.app_reference_time is not None and self.app_env != "development":
            raise ValueError("APP_REFERENCE_TIME is permitted only in development")
        return self

    @field_validator("demo_session_secret", mode="before")
    @classmethod
    def strong_demo_secret(cls, value):
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw or not str(raw).strip():
            return SecretStr(secrets.token_urlsafe(32))
        if len(raw) < 32:
            raise ValueError("DEMO_SESSION_SECRET must contain at least 32 characters")
        return value

    @field_validator(
        "database_url",
        "groq_api_key",
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
        mode="before",
    )
    @classmethod
    def blank_optional_secrets(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url is not None:
            url = make_url(self.database_url.get_secret_value())
            if url.drivername not in {"postgres", "postgresql", "postgresql+asyncpg"}:
                raise ValueError("DATABASE_URL must be a PostgreSQL URL.")
            return url.set(drivername="postgresql+asyncpg")
        if self.postgres_password is None:
            raise ValueError("Set POSTGRES_PASSWORD or DATABASE_URL in the environment.")
        # URL.create safely handles reserved characters in the actual password.
        return URL.create(
            "postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
