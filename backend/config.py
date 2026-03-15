"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    secret_key: str = "dev-secret-key-change-in-production"
    groq_api_key: str | None = None
    tesseract_cmd: str | None = None
    allowed_extensions: set[str] = {".pdf"}
    max_upload_size_mb: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
