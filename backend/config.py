"""Application configuration."""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    secret_key: str = "dev-secret-key-change-in-production"
    database_url: str | None = None
    groq_api_key: str | None = None
    paddleocr_lang: str = "en"
    paddleocr_use_angle_cls: bool = True
    paddle_pdx_cache_home: str | None = None
    paddle_pdx_disable_model_source_check: bool = True
    allowed_extensions: set[str] = {".pdf"}
    max_upload_size_mb: int = 10
    rag_embedding_model: str = "BAAI/bge-small-en"
    rag_collection_name: str = "document_chunks"
    rag_chunk_size_words: int = 220
    rag_chunk_overlap_words: int = 40
    rag_top_k: int = 4
    rag_min_chunk_chars: int = 120
    rag_vector_db_path: str | None = None
    rag_embedding_cache_dir: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
