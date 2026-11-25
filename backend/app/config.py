from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from the project root .env file."""

    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/keitaro_wrapper"
    KEITARO_BASE_URL: str = ""
    KEITARO_API_KEY: str = ""
    KEITARO_ADMIN_URL: str = ""
    KEITARO_DEFAULT_DOMAIN_ID: int | None = None
    KEITARO_DEFAULT_GROUP_ID: int | None = None
    KEITARO_DEFAULT_SOURCE_ID: int | None = None
    OFFERS_CACHE_TTL_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
