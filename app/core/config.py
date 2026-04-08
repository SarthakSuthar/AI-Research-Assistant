from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extras="ignore"
    )

    # Application
    app_name: str = Field(default="AI Research Assistant API", alias="APP_NAME")
    app_env: Literal["development", "production"] = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    # MARK: Google Gemini
    gemini_api_key: str = Field(
        ...,
        description="Google Gemini API key from https://aistudio.google.com/apikey",
    )

    gemini_embedding_model: str = Field(
        default="gemini-embedding-001",
        description="Embedding model name. Changing this requires a DB migration "
        "if output_dimensionality also changes.",
    )

    # 20 texts per API call is a safe default.
    # Free-tier keys: reduce to 5 to avoid 429s on large documents.
    # Paid-tier keys: increase to 50-100 for faster ingestion.
    embedding_batch_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of chunk texts sent per embed_content API call.",
    )

    # MARK: Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", alias="LOG_LEVEL"
    )

    # MARK: CORS
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")

    allowed_origins: list[str] = ["*"]

    # MARK: DATABASE
    database_url: str = Field(
        alias="DATABASE_URL",
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_research_db",
    )

    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")

    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")

    db_pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")

    @field_validator("database_url")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
