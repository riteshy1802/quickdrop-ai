"""Database settings; read the existing root .env and optional backend overrides."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    app_env: str = "development"
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
