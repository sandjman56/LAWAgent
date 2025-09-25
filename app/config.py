from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"
    openai_embeddings_model: str = "text-embedding-3-large"
    perplexity_api_key: str | None = None
    perplexity_model: str = "llama-3.1-sonar-large-128k-online"
    max_file_mb: int = 15
    max_pages: int = 100
    allowed_origins: str | None = None  # comma-separated

    class Config:
        env_file = ".env"


settings = Settings()
