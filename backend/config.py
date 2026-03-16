"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    secret_key: str = "dev-secret-key-change-in-production"
    groq_api_key: str | None = None
    paddleocr_lang: str = "en"
    paddleocr_use_angle_cls: bool = True
    paddle_pdx_cache_home: str | None = None
    paddle_pdx_disable_model_source_check: bool = True
    allowed_extensions: set[str] = {".pdf"}
    max_upload_size_mb: int = 10

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
