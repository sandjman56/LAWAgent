from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    max_file_mb: int = 15
    max_pages: int = 100
    allowed_origins: str | None = None  # comma-separated

    class Config:
        env_file = ".env"


settings = Settings()
