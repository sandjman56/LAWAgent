from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment."""

    auth_token: str = Field(..., alias="AUTH_TOKEN")
    frontend_origin: AnyHttpUrl = Field(..., alias="FRONTEND_ORIGIN")
    data_dir: Path = Field(default=Path("./data/uploads"), alias="DATA_DIR")
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")
    max_upload_mb: int = Field(default=20, alias="MAX_UPLOAD_MB")
    max_pages: int = Field(default=500, alias="MAX_PAGES")

    llm_provider: Optional[str] = Field(default=None, alias="LLM_PROVIDER")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, value: Path | str) -> Path:
        path = Path(value).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
